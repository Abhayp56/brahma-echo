package com.brahma.connect.network

import android.content.Context
import android.os.SystemClock
import com.brahma.connect.commands.DeviceCommandHandler
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.core.BrahmaProtocol
import com.brahma.connect.core.ChatMessage
import com.brahma.connect.core.ConnectionState
import com.brahma.connect.core.DeviceCredential
import com.brahma.connect.core.DeviceSnapshot
import com.brahma.connect.core.GatewayEndpoint
import com.brahma.connect.core.PairingOffer
import com.brahma.connect.pairing.PairingStorage
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.min
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class BrahmaWebSocketClient(
    private val context: Context,
    private val storage: PairingStorage,
    private val commandHandler: DeviceCommandHandler,
) {
    private val callManager = com.brahma.connect.call.CallManager.getInstance(context)

    init {
        callManager.onSendCallRequest = { reason ->
            syncLocationIfPermitted()
            send(BrahmaProtocol.callRequest(reason))
        }
        callManager.onSendCallAnswer = { callId ->
            send(BrahmaProtocol.callAnswer(callId))
        }
        callManager.onSendCallReject = { callId ->
            send(BrahmaProtocol.callReject(callId))
        }
        callManager.onSendCallEnd = { callId ->
            send(BrahmaProtocol.callEnd(callId))
        }
        callManager.onSendCallAudio = { callId, base64Chunk ->
            send(BrahmaProtocol.callAudio(callId, base64Chunk))
        }
        callManager.onSendCallSpeechText = { callId, text ->
            send(BrahmaProtocol.callSpeechText(callId, text))
        }
    }

    private val client = OkHttpClient.Builder()
        .retryOnConnectionFailure(true)
        .pingInterval(30, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var socket: WebSocket? = null
    private var currentEndpoint: GatewayEndpoint? = null
    private var currentOffer: PairingOffer? = null
    private var currentCredential: DeviceCredential? = null
    private var manualDisconnect = false
    private var reconnectAttempt = 0
    private var lastConnectUptime = 0L
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var reconnectJob: Job? = null
    private var lastContactsSyncTime = 0L

    fun connect(endpoint: GatewayEndpoint, credential: DeviceCredential? = storage.loadCredential(), offer: PairingOffer? = null) {
        val state = AgentStateStore.connectionState.value
        val isSameTarget = currentEndpoint != null && (
            (endpoint.url.isNotBlank() && currentEndpoint?.url == endpoint.url) ||
            (endpoint.host.isNotBlank() && currentEndpoint?.host == endpoint.host)
        )

        if (socket != null && isSameTarget && (state == ConnectionState.CONNECTED || state == ConnectionState.CONNECTING)) {
            android.util.Log.d("BrahmaWebSocketClient", "Already connected/connecting to ${endpoint.name}, preserving active session.")
            currentCredential = credential ?: currentCredential
            currentOffer = offer ?: currentOffer
            return
        }

        currentEndpoint = endpoint
        currentCredential = credential
        currentOffer = offer
        manualDisconnect = false
        reconnectAttempt = 0
        lastConnectUptime = SystemClock.elapsedRealtime()
        AgentStateStore.setGateway(endpoint)
        AgentStateStore.setConnectionState(ConnectionState.CONNECTING)
        AgentStateStore.setStatus("Connecting to ${endpoint.name}")

        socket?.close(1000, "Reconnecting")
        val wsUrl = when {
            endpoint.url.isNotBlank() -> endpoint.url
            offer?.url?.isNotBlank() == true -> offer.url
            credential?.gatewayUrl?.isNotBlank() == true -> credential.gatewayUrl
            endpoint.ssl || endpoint.port == 443 || endpoint.host.contains("onrender.com") -> {
                val p = endpoint.path.ifBlank { "/ws/phone" }
                "wss://${endpoint.host}$p"
            }
            else -> {
                val p = endpoint.path.ifBlank { "/ws" }
                "ws://${endpoint.host}:${endpoint.port}$p"
            }
        }
        android.util.Log.i("BrahmaWebSocketClient", "Connecting WebSocket to: $wsUrl")
        socket = client.newWebSocket(
            Request.Builder().url(wsUrl).build(),
            BrahmaSocketListener(),
        )
    }

    fun disconnect() {
        manualDisconnect = true
        reconnectJob?.cancel()
        socket?.close(1000, "Disconnected by user")
        socket = null
        AgentStateStore.setConnectionState(ConnectionState.DISCONNECTED)
        AgentStateStore.setStatus("Disconnected")
    }

    private fun reconnectLater() {
        if (manualDisconnect) return
        val endpoint = currentEndpoint ?: run {
            val cred = storage.loadCredential()
            if (cred != null && (cred.gatewayHost.isNotBlank() || cred.gatewayUrl.isNotBlank())) {
                val isCloud = cred.ssl || cred.gatewayUrl.contains("onrender.com")
                GatewayEndpoint(
                    name = if (isCloud) "JARVIS Cloud AI" else "Brahma PC",
                    host = cred.gatewayHost,
                    port = cred.gatewayPort,
                    ssl = cred.ssl,
                    url = cred.gatewayUrl,
                )
            } else null
        } ?: return

        reconnectAttempt += 1
        AgentStateStore.setConnectionState(ConnectionState.RECONNECTING)
        val baseDelay = min(15_000L, 1_000L * (1 shl min(reconnectAttempt, 4)))
        val jitter = (Math.random() * 1500).toLong()
        val delayMs = baseDelay + jitter
        AgentStateStore.setStatus("Reconnecting in ${delayMs / 1000}s")
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(delayMs)
            if (!manualDisconnect) {
                val cred = currentCredential ?: storage.loadCredential()
                connect(endpoint, cred, currentOffer)
            }
        }
    }

    private fun send(json: JSONObject) {
        socket?.send(json.toString())
    }

    private fun batterySnapshot(): Pair<Int, Boolean> {
        val battery = commandHandler.handle("get_battery", emptyMap()).data
        val percentage = (battery["percentage"] as? Int) ?: -1
        val charging = (battery["charging"] as? Boolean) ?: false
        return percentage to charging
    }

    private fun buildSnapshot(): DeviceSnapshot {
        val credential = currentCredential
        val (percentage, charging) = batterySnapshot()
        return DeviceSnapshot(
            deviceId = credential?.deviceId,
            deviceName = credential?.deviceName ?: android.os.Build.MODEL ?: "Android",
            androidVersion = android.os.Build.VERSION.RELEASE ?: "Unknown",
            agentVersion = "1.0.0",
            batteryPercentage = percentage,
            charging = charging,
            wifiEnabled = true,
            capabilities = listOf(
                "device_info",
                "battery",
                "flashlight",
                "volume",
                "media",
                "launch_app",
                "apps",
                "open_url",
                "wifi_state",
            ),
        )
    }

    private fun sendHello() {
        send(BrahmaProtocol.hello(buildSnapshot()))
        AgentStateStore.setStatus("Awaiting approval")
    }

    private fun sendPairRequest() {
        val offer = currentOffer ?: run {
            sendHello()
            return
        }
        val snapshot = buildSnapshot().toJson()
            .put("pairing_token", offer.pairingToken)
            .put("pairing_code", offer.pairingCode)
        send(BrahmaProtocol.envelope(BrahmaProtocol.PAIR_REQUEST, snapshot))
        AgentStateStore.setStatus("Pairing request sent")
    }

    private fun sendAuthenticate() {
        val credential = currentCredential ?: storage.loadCredential()
        if (credential == null) {
            sendHello()
            return
        }
        currentCredential = credential
        send(BrahmaProtocol.authenticate(credential))
        AgentStateStore.setStatus("Authenticating")
    }

    private fun handleCommandMessage(root: JSONObject) {
        val requestId = root.optString("request_id")
        val payload = root.optJSONObject("payload") ?: JSONObject()
        val action = payload.optString("action")
        val params = payload.optJSONObject("parameters") ?: JSONObject()
        val parameterMap = buildMap<String, Any?> {
            params.keys().forEach { key ->
                put(key, params.opt(key))
            }
        }
        val result = commandHandler.handle(action, parameterMap)
        val response = BrahmaProtocol.envelope(
            BrahmaProtocol.RESULT,
            result.toJson(),
            requestId = requestId,
        )
        send(response)
    }

    private fun handlePairApproved(root: JSONObject) {
        val payload = root.optJSONObject("payload") ?: JSONObject()
        val device = payload.optJSONObject("device") ?: JSONObject()
        val secret = payload.optString("device_secret")
        val deviceId = device.optString("device_id")
        val deviceName = device.optString("name", android.os.Build.MODEL ?: "Android")
        val isCloud = currentEndpoint?.ssl == true || currentOffer?.ssl == true || currentEndpoint?.host?.contains("onrender.com") == true || currentOffer?.url?.contains("onrender.com") == true
        val credUrl = currentOffer?.url?.ifBlank { null } ?: currentEndpoint?.url?.ifBlank { null } ?: if (isCloud) "wss://${currentEndpoint?.host}/ws/phone" else ""
        val credential = DeviceCredential(
            deviceId = deviceId,
            deviceSecret = secret,
            deviceName = deviceName,
            gatewayHost = currentEndpoint?.host.orEmpty(),
            gatewayPort = currentEndpoint?.port ?: (if (isCloud) 443 else 8765),
            gatewayUrl = credUrl,
            ssl = isCloud,
        )
        storage.saveCredential(credential)
        currentCredential = credential
        AgentStateStore.setCredential(credential)
        AgentStateStore.setStatus("Pair approved")
        sendAuthenticate()
    }

    private inner class BrahmaSocketListener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
            socket = webSocket
            reconnectAttempt = 0
            AgentStateStore.setConnectionState(ConnectionState.CONNECTING)
            if (currentCredential != null || storage.loadCredential() != null) {
                sendAuthenticate()
            } else if (currentOffer != null) {
                sendPairRequest()
            } else {
                sendHello()
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            runCatching {
                val root = JSONObject(text)
                val type = root.optString("type")
                when (type) {
                    BrahmaProtocol.PAIR_REQUEST -> {
                        AgentStateStore.setStatus("Waiting for approval")
                    }
                    BrahmaProtocol.PAIR_APPROVED -> handlePairApproved(root)
                    BrahmaProtocol.DEVICE_ONLINE -> {
                        AgentStateStore.setConnectionState(ConnectionState.CONNECTED)
                        AgentStateStore.setStatus("Connected")
                        syncContactsIfPermitted()
                        syncLocationIfPermitted()
                    }
                    BrahmaProtocol.CAPABILITIES -> {
                        AgentStateStore.addLog("Capabilities synced")
                    }
                    BrahmaProtocol.EXECUTE, "command_request", "command" -> handleCommandMessage(root)
                    BrahmaProtocol.PING -> {
                        send(BrahmaProtocol.envelope(BrahmaProtocol.PONG, JSONObject().put("status", "ok"), requestId = root.optString("request_id")))
                    }
                    BrahmaProtocol.ERROR -> {
                        AgentStateStore.setError(root.optJSONObject("payload")?.optString("error"))
                    }
                    BrahmaProtocol.CHAT_MESSAGE -> {
                        val payload = root.optJSONObject("payload") ?: return
                        val role = payload.optString("role", "system")
                        val text = payload.optString("text", "")
                        val msgId = root.optString("request_id")
                        val timestamp = System.currentTimeMillis()
                        val msg = ChatMessage(msgId, role, text, timestamp, "Sent")
                        AgentStateStore.addChatMessage(msg)
                    }
                    BrahmaProtocol.CALL_ANSWER -> {
                        val payload = root.optJSONObject("payload")
                        val callId = payload?.optString("call_id")
                        if (!callId.isNullOrEmpty()) {
                            callManager.updateCallId(callId)
                        }
                    }
                    BrahmaProtocol.CALL_OFFER -> {
                        val payload = root.optJSONObject("payload") ?: return
                        val offer = com.brahma.connect.core.CallOfferPayload(
                            callId = payload.optString("call_id", root.optString("request_id")),
                            callerName = payload.optString("caller_name", "JARVIS"),
                            reason = payload.optString("reason", "Voice Call"),
                            timestamp = payload.optLong("timestamp", System.currentTimeMillis())
                        )
                        callManager.handleIncomingCallOffer(offer)
                    }
                    BrahmaProtocol.CALL_END -> {
                        val payload = root.optJSONObject("payload")
                        val callId = payload?.optString("call_id") ?: ""
                        callManager.onCallEndedByRemote(callId)
                    }
                    BrahmaProtocol.CALL_AUDIO -> {
                        val payload = root.optJSONObject("payload") ?: return
                        val audioData = payload.optString("data", "")
                        if (audioData.isNotEmpty()) {
                            callManager.handleIncomingAudioChunk(audioData)
                        }
                    }
                    BrahmaProtocol.CALL_TURN_COMPLETE -> {
                        callManager.handleTurnComplete()
                    }
                }
            }.onFailure {
                AgentStateStore.setError(it.message)
            }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            onMessage(webSocket, bytes.utf8())
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            socket = null
            AgentStateStore.addLog("Socket closed: $code $reason")
            AgentStateStore.setConnectionState(ConnectionState.DISCONNECTED)
            AgentStateStore.setStatus("Disconnected")
            reconnectLater()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
            socket = null
            AgentStateStore.addLog("Socket failure: ${t.message}")
            AgentStateStore.setConnectionState(ConnectionState.DISCONNECTED)
            AgentStateStore.setStatus("Connection failed")
            reconnectLater()
        }
    }

    fun sendChatMessage(text: String) {
        val payload = BrahmaProtocol.chatMessage(text)
        val msgId = payload.getString("request_id")
        val timestamp = System.currentTimeMillis()
        val pending = ChatMessage(msgId, "user", text, timestamp, "Sending...")
        AgentStateStore.addChatMessage(pending)
        send(payload)
        val sent = pending.copy(status = "Sent")
        AgentStateStore.addChatMessage(sent)
    }

    fun syncContactsIfPermitted(force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (!force && now - lastContactsSyncTime < 30 * 60 * 1000L) {
            return
        }

        val hasPermission = androidx.core.content.ContextCompat.checkSelfPermission(
            context,
            android.Manifest.permission.READ_CONTACTS
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED

        if (hasPermission) {
            lastContactsSyncTime = now
            Thread {
                try {
                    val contacts = com.brahma.connect.contacts.ContactsHelper.fetchContacts(context)
                    if (contacts.isNotEmpty()) {
                        send(BrahmaProtocol.contactsSync(contacts))
                        AgentStateStore.addLog("Synced ${contacts.size} phone contacts")
                        android.util.Log.i("BrahmaWebSocketClient", "Synced ${contacts.size} contacts to JARVIS")
                    }
                } catch (e: Exception) {
                    android.util.Log.e("BrahmaWebSocketClient", "Error syncing contacts: ${e.message}", e)
                }
            }.start()
        }
    }

    fun syncLocationIfPermitted() {
        val finePerm = androidx.core.content.ContextCompat.checkSelfPermission(
            context,
            android.Manifest.permission.ACCESS_FINE_LOCATION
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED
        val coarsePerm = androidx.core.content.ContextCompat.checkSelfPermission(
            context,
            android.Manifest.permission.ACCESS_COARSE_LOCATION
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED

        if (finePerm || coarsePerm) {
            Thread {
                try {
                    val lm = context.getSystemService(android.content.Context.LOCATION_SERVICE) as? android.location.LocationManager
                    if (lm != null) {
                        var bestLocation: android.location.Location? = null
                        val providers = lm.getProviders(true)
                        for (provider in providers) {
                            val l = try { lm.getLastKnownLocation(provider) } catch (e: SecurityException) { null }
                            if (l != null) {
                                if (bestLocation == null || l.accuracy < bestLocation.accuracy) {
                                    bestLocation = l
                                }
                            }
                        }

                        if (bestLocation != null) {
                            var cityName = ""
                            var stateName = ""
                            var countryName = "India"
                            var fullAddr = ""

                            try {
                                val geocoder = android.location.Geocoder(context, java.util.Locale.getDefault())
                                val addresses = geocoder.getFromLocation(bestLocation.latitude, bestLocation.longitude, 1)
                                if (!addresses.isNullOrEmpty()) {
                                    val addr = addresses[0]
                                    cityName = addr.locality ?: addr.subAdminArea ?: addr.adminArea ?: ""
                                    stateName = addr.adminArea ?: ""
                                    countryName = addr.countryName ?: "India"
                                    fullAddr = addr.getAddressLine(0) ?: ""
                                }
                            } catch (e: Exception) {
                                android.util.Log.w("BrahmaWebSocketClient", "Geocoder lookup failed: ${e.message}")
                            }

                            send(BrahmaProtocol.locationSync(
                                lat = bestLocation.latitude,
                                lon = bestLocation.longitude,
                                city = cityName,
                                state = stateName,
                                country = countryName,
                                address = fullAddr
                            ))
                            AgentStateStore.addLog("Synced location: ${cityName.ifEmpty { "GPS coordinates" }}")
                            android.util.Log.i("BrahmaWebSocketClient", "📍 Synced location: city='$cityName', lat=${bestLocation.latitude}, lon=${bestLocation.longitude}")
                        }
                    }
                } catch (e: Exception) {
                    android.util.Log.e("BrahmaWebSocketClient", "Error syncing location: ${e.message}", e)
                }
            }.start()
        }
    }
}
