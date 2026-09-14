package com.brahma.connect

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.brahma.connect.commands.DeviceCommandHandler
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.core.ConnectionState
import com.brahma.connect.core.GatewayEndpoint
import com.brahma.connect.network.BrahmaWebSocketClient
import com.brahma.connect.pairing.PairingStorage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.collect

class BrahmaConnectForegroundService : Service() {
    private val scope = CoroutineScope(Job() + Dispatchers.IO)
    private lateinit var storage: PairingStorage
    private lateinit var client: BrahmaWebSocketClient
    private var started = false
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        storage = PairingStorage(this)
        client = BrahmaWebSocketClient(this, storage, DeviceCommandHandler(this))
        createNotificationChannel()
        try {
            val notification = buildNotification("Brahma Connect", "Starting connection")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (security: SecurityException) {
            stopSelf()
            return
        } catch (t: Throwable) {
            stopSelf()
            return
        }

        acquireWakeLock()
        registerNetworkCallback()

        scope.launch {
            AgentStateStore.connectionState.collect {
                updateNotification()
                if (it == ConnectionState.CONNECTED) {
                    acquireWakeLock()
                }
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                client.disconnect()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_SEND_CHAT -> {
                val text = intent.getStringExtra(EXTRA_CHAT_TEXT)
                if (!text.isNullOrBlank()) {
                    client.sendChatMessage(text)
                }
                return START_STICKY
            }
        }
        connectIfPossible()
        return START_STICKY
    }

    private fun connectIfPossible() {
        var endpoint = AgentStateStore.gateway.value
        val credential = storage.loadCredential()
        val offer = AgentStateStore.pairingOffer.value ?: storage.loadGatewayHint()

        // If in-memory endpoint is null, reconstruct from persisted storage
        if (endpoint == null) {
            if (credential != null && (credential.gatewayHost.isNotBlank() || credential.gatewayUrl.isNotBlank())) {
                val isCloud = credential.ssl || credential.gatewayUrl.contains("onrender.com")
                endpoint = GatewayEndpoint(
                    name = if (isCloud) "ARYA Cloud AI" else "Brahma PC",
                    host = credential.gatewayHost,
                    port = credential.gatewayPort,
                    ssl = credential.ssl,
                    url = credential.gatewayUrl,
                )
                AgentStateStore.setGateway(endpoint)
            } else if (offer != null && (offer.host.isNotBlank() || offer.url.isNotBlank())) {
                val isCloud = offer.ssl || offer.url.contains("onrender.com")
                endpoint = GatewayEndpoint(
                    name = if (isCloud) "ARYA Cloud AI" else "Brahma PC",
                    host = offer.host,
                    port = offer.port,
                    ssl = offer.ssl,
                    path = offer.path,
                    url = offer.url,
                )
                AgentStateStore.setGateway(endpoint)
            }
        }

        if (endpoint == null) {
            android.util.Log.w("BrahmaService", "No gateway endpoint available to connect.")
            return
        }

        if (!started) {
            started = true
        }
        client.connect(endpoint, credential, offer)
        AgentStateStore.setConnectionState(ConnectionState.CONNECTING)
    }

    private fun registerNetworkCallback() {
        try {
            val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return
            val builder = NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            networkCallback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    android.util.Log.i("BrahmaService", "Network became available! Re-evaluating connection...")
                    if (AgentStateStore.connectionState.value != ConnectionState.CONNECTED) {
                        scope.launch {
                            connectIfPossible()
                        }
                    }
                }

                override fun onLost(network: Network) {
                    android.util.Log.w("BrahmaService", "Network lost.")
                }
            }
            cm.registerNetworkCallback(builder.build(), networkCallback!!)
        } catch (e: Exception) {
            android.util.Log.e("BrahmaService", "Failed to register network callback: ${e.message}")
        }
    }

    private fun unregisterNetworkCallback() {
        try {
            val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return
            networkCallback?.let { cm.unregisterNetworkCallback(it) }
        } catch (_: Exception) {}
        networkCallback = null
    }

    private fun acquireWakeLock() {
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return
            if (wakeLock == null) {
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "BrahmaConnect:ServiceWakeLock").apply {
                    setReferenceCounted(false)
                }
            }
            wakeLock?.let {
                if (!it.isHeld) {
                    it.acquire(60 * 60 * 1000L) // 1 hour max lease, renewed on reconnect
                }
            }
        } catch (e: Exception) {
            android.util.Log.w("BrahmaService", "Could not acquire WakeLock: ${e.message}")
        }
    }

    private fun releaseWakeLock() {
        try {
            wakeLock?.let {
                if (it.isHeld) it.release()
            }
        } catch (_: Exception) {}
        wakeLock = null
    }

    private fun updateNotification() {
        val state = AgentStateStore.connectionState.value
        val text = when (state) {
            ConnectionState.CONNECTED -> "Connected to Brahma"
            ConnectionState.CONNECTING -> "Connecting to Brahma"
            ConnectionState.RECONNECTING -> "Reconnecting"
            ConnectionState.DISCONNECTED -> "Disconnected"
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification("Brahma Connect", text))
    }

    private fun buildNotification(title: String, text: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_brahma_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(CHANNEL_ID, "Brahma Connect", NotificationManager.IMPORTANCE_LOW)
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        unregisterNetworkCallback()
        releaseWakeLock()
        client.disconnect()
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.brahma.connect.action.STOP"
        const val ACTION_SEND_CHAT = "com.brahma.connect.action.SEND_CHAT"
        const val EXTRA_CHAT_TEXT = "com.brahma.connect.extra.CHAT_TEXT"
        private const val CHANNEL_ID = "brahma_connect"
        private const val NOTIFICATION_ID = 4201
    }
}
