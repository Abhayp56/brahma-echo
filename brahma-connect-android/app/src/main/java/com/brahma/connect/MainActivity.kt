package com.brahma.connect

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.pairing.PairingStorage
import com.brahma.connect.ui.BrahmaConnectApp
import com.brahma.connect.ui.theme.BrahmaConnectTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var storage: PairingStorage
    private var pendingServiceStart = false

    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { _ ->
        // Reaction handled by compose state
    }

    private val multiPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { perms ->
        perms.forEach { (perm, granted) ->
            if (granted) {
                val shortName = perm.substringAfterLast('.')
                AgentStateStore.addLog("Permission granted: $shortName")
            }
        }
        if (pendingServiceStart) {
            pendingServiceStart = false
            startGatewayService()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        storage = PairingStorage(this)
        val cred = storage.loadCredential()
        AgentStateStore.setCredential(cred)
        storage.loadGatewayHint()?.let {
            AgentStateStore.setPairingOffer(it)
            val isCloud = it.ssl || it.url.contains("onrender.com")
            AgentStateStore.setGateway(
                com.brahma.connect.core.GatewayEndpoint(
                    name = if (isCloud) "JARVIS Cloud AI" else "Brahma PC",
                    host = it.host,
                    port = it.port,
                    ssl = it.ssl,
                    path = it.path,
                    url = it.url,
                )
            )
        }
        if (AgentStateStore.gateway.value == null && cred != null) {
            val isCloud = cred.ssl || cred.gatewayUrl.contains("onrender.com")
            AgentStateStore.setGateway(
                com.brahma.connect.core.GatewayEndpoint(
                    name = if (isCloud) "JARVIS Cloud AI" else "Brahma PC",
                    host = cred.gatewayHost,
                    port = cred.gatewayPort,
                    ssl = cred.ssl,
                    url = cred.gatewayUrl,
                )
            )
        }

        setContent {
            BrahmaConnectTheme {
                BrahmaConnectApp(
                    onRequestCameraPermission = {
                        cameraPermission.launch(Manifest.permission.CAMERA)
                    },
                    onRequestNotificationPermission = {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            multiPermissionLauncher.launch(arrayOf(Manifest.permission.POST_NOTIFICATIONS))
                        }
                    },
                    onRequestCallLogPermission = {
                        multiPermissionLauncher.launch(arrayOf(Manifest.permission.READ_CALL_LOG))
                    },
                    onOpenNotificationListenerSettings = {
                        try {
                            val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).apply {
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            }
                            startActivity(intent)
                        } catch (e: Exception) {
                            android.util.Log.w("MainActivity", "Failed to open notification listener settings: ${e.message}")
                        }
                    },
                    onStartService = { maybeStartService() },
                )
            }
        }

        // Request missing permissions safely in a single batch dialog
        requestCorePermissions()
        maybeStartService()

        lifecycleScope.launch {
            delay(1500)
            ensureBatteryOptimizationExemption()
        }
    }

    private fun maybeStartService() {
        val endpoint = AgentStateStore.gateway.value
        if (endpoint != null || AgentStateStore.credential.value != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) {
                pendingServiceStart = true
                multiPermissionLauncher.launch(arrayOf(Manifest.permission.POST_NOTIFICATIONS))
                return
            }
            startGatewayService()
        }
    }

    private fun requestCorePermissions() {
        val permissionsToRequest = mutableListOf<String>()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.RECORD_AUDIO)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.READ_CONTACTS)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.READ_CALL_LOG)
        }
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!fine && !coarse) {
            permissionsToRequest.add(Manifest.permission.ACCESS_FINE_LOCATION)
            permissionsToRequest.add(Manifest.permission.ACCESS_COARSE_LOCATION)
        }

        if (permissionsToRequest.isNotEmpty()) {
            multiPermissionLauncher.launch(permissionsToRequest.toTypedArray())
        }
    }

    private fun ensureBatteryOptimizationExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return
                if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                    val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                        data = Uri.parse("package:$packageName")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    startActivity(intent)
                }
            } catch (e: Exception) {
                android.util.Log.w("MainActivity", "Could not request ignore battery optimizations: ${e.message}")
            }
        }
    }

    private fun startGatewayService() {
        val endpoint = AgentStateStore.gateway.value
        if (endpoint != null || AgentStateStore.credential.value != null) {
            try {
                val intent = Intent(this, BrahmaConnectForegroundService::class.java)
                ContextCompat.startForegroundService(this, intent)
            } catch (e: Exception) {
                android.util.Log.e("MainActivity", "Error starting BrahmaConnectForegroundService: ${e.message}")
            }
        }
    }
}
