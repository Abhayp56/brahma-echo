package com.brahma.connect

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import android.content.Context
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.pairing.PairingStorage
import com.brahma.connect.ui.BrahmaConnectApp
import com.brahma.connect.ui.theme.BrahmaConnectTheme

class MainActivity : ComponentActivity() {
    private lateinit var storage: PairingStorage
    private var pendingServiceStart = false

    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { _ ->
        // The UI will react by showing the scanner if permission is granted.
    }

    private val contactsPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            AgentStateStore.addLog("Contacts permission granted")
        }
    }

    private val locationPermission = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { perms ->
        val granted = perms[Manifest.permission.ACCESS_FINE_LOCATION] == true || perms[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (granted) {
            AgentStateStore.addLog("Location permission granted for weather & briefing")
        }
    }

    private val audioPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            AgentStateStore.addLog("Microphone permission granted for voice calls")
        }
    }

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted || Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            if (pendingServiceStart) {
                pendingServiceStart = false
                startGatewayService()
            }
        } else {
            pendingServiceStart = false
            AgentStateStore.setError("Notification permission is required for Brahma Connect.")
            AgentStateStore.setStatus("Notification permission denied")
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
        maybeStartService()
        ensureCameraPermission()
        ensureAudioPermission()
        ensureContactsPermission()
        ensureLocationPermission()
        ensureBatteryOptimizationExemption()
        setContent {
            BrahmaConnectTheme {
                BrahmaConnectApp(
                    onRequestCameraPermission = {
                        cameraPermission.launch(Manifest.permission.CAMERA)
                    },
                    onRequestNotificationPermission = {
                        notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    },
                    onStartService = { maybeStartService() },
                )
            }
        }
    }

    private fun maybeStartService() {
        val endpoint = AgentStateStore.gateway.value
        if (endpoint != null || AgentStateStore.credential.value != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) {
                pendingServiceStart = true
                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                return
            }
            startGatewayService()
        }
    }

    private fun ensureCameraPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun ensureAudioPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            audioPermission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun ensureContactsPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            contactsPermission.launch(Manifest.permission.READ_CONTACTS)
        }
    }

    private fun ensureLocationPermission() {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!fine && !coarse) {
            locationPermission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
        }
    }

    private fun ensureBatteryOptimizationExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return
                if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                    val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                        data = Uri.parse("package:$packageName")
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
            val intent = Intent(this, BrahmaConnectForegroundService::class.java)
            ContextCompat.startForegroundService(this, intent)
        }
    }
}
