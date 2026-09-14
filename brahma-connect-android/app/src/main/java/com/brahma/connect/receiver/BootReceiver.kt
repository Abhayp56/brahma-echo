package com.brahma.connect.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.brahma.connect.BrahmaConnectForegroundService
import com.brahma.connect.pairing.PairingStorage

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            val storage = PairingStorage(context)
            val credential = storage.loadCredential()
            val hint = storage.loadGatewayHint()

            // Only auto-start if the user previously paired with Brahma or ARYA Cloud
            if (credential != null || hint != null) {
                android.util.Log.i("BootReceiver", "Device booted or updated. Auto-starting BrahmaConnectForegroundService...")
                val serviceIntent = Intent(context, BrahmaConnectForegroundService::class.java)
                try {
                    ContextCompat.startForegroundService(context, serviceIntent)
                } catch (e: Exception) {
                    android.util.Log.e("BootReceiver", "Could not start foreground service on boot: ${e.message}", e)
                }
            }
        }
    }
}
