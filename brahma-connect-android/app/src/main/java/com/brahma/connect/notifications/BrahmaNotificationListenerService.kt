package com.brahma.connect.notifications

import android.app.Notification
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationManagerCompat

/**
 * BrahmaNotificationListenerService
 * Captures incoming notifications across apps (WhatsApp, Instagram, Gmail, SMS, Banking, etc.)
 * and caches them in NotificationStore for JARVIS queries and summarization.
 */
class BrahmaNotificationListenerService : NotificationListenerService() {

    companion object {
        private const val TAG = "BrahmaNotificationSvc"

        @Volatile
        var instance: BrahmaNotificationListenerService? = null
            private set

        fun isPermissionGranted(context: Context): Boolean {
            return try {
                val enabled = NotificationManagerCompat.getEnabledListenerPackages(context)
                if (enabled.contains(context.packageName)) return true

                val componentName = ComponentName(context, BrahmaNotificationListenerService::class.java)
                val flat = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners")
                flat != null && flat.contains(componentName.flattenToString())
            } catch (e: Throwable) {
                false
            }
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
        Log.i(TAG, "Brahma Notification Listener connected successfully.")
        try {
            syncActiveNotifications()
        } catch (e: Throwable) {
            Log.w(TAG, "Error in onListenerConnected sync: ${e.message}")
        }
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        instance = null
        Log.i(TAG, "Brahma Notification Listener disconnected.")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        if (sbn == null) return
        try {
            processStatusBarNotification(sbn)
        } catch (e: Throwable) {
            Log.e(TAG, "Error processing onNotificationPosted: ${e.message}")
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        super.onNotificationRemoved(sbn)
        if (sbn == null) return
        try {
            val key = sbn.key ?: "${sbn.packageName}_${sbn.id}"
            NotificationStore.remove(key)
        } catch (e: Throwable) {
            Log.w(TAG, "Error in onNotificationRemoved: ${e.message}")
        }
    }

    fun syncActiveNotifications() {
        try {
            val active = activeNotifications ?: return
            for (sbn in active) {
                try {
                    processStatusBarNotification(sbn)
                } catch (e: Throwable) {
                    Log.w(TAG, "Error syncing individual notification: ${e.message}")
                }
            }
        } catch (e: Throwable) {
            Log.w(TAG, "Error syncing active notifications: ${e.message}")
        }
    }

    private fun processStatusBarNotification(sbn: StatusBarNotification) {
        val pkg = sbn.packageName ?: return

        // Skip our own app notifications to prevent self-looping
        if (pkg == packageName) return

        val notification = sbn.notification ?: return
        val extras = notification.extras ?: return

        try {
            // Safely extract titles without ClassCastException
            val title = try {
                extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()
                    ?: extras.getCharSequence(Notification.EXTRA_TITLE_BIG)?.toString()
                    ?: ""
            } catch (e: Throwable) {
                ""
            }

            // Safely extract text
            var text = try {
                extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()
                    ?: extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()
                    ?: ""
            } catch (e: Throwable) {
                ""
            }

            val subText = try {
                extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString()
                    ?: extras.getCharSequence(Notification.EXTRA_SUMMARY_TEXT)?.toString()
            } catch (e: Throwable) {
                null
            }

            // Handle MessagingStyle (WhatsApp, Telegram, Signal) safely
            if (text.isBlank()) {
                try {
                    val messages = extras.get(Notification.EXTRA_MESSAGES) as? Array<*>
                    if (messages != null && messages.isNotEmpty()) {
                        val lastBundle = messages.lastOrNull() as? Bundle
                        val msgText = lastBundle?.getCharSequence("text")?.toString()
                        if (!msgText.isNullOrBlank()) {
                            text = msgText
                        }
                    }
                } catch (ignored: Throwable) {}
            }

            // Skip empty or purely blank noise notifications
            if (title.isBlank() && text.isBlank()) return

            val isOngoing = sbn.isOngoing || (notification.flags and Notification.FLAG_ONGOING_EVENT) != 0

            val appName = try {
                val appInfo = packageManager.getApplicationInfo(pkg, 0)
                packageManager.getApplicationLabel(appInfo).toString()
            } catch (e: Throwable) {
                pkg.substringAfterLast('.')
            }

            val key = sbn.key ?: "${pkg}_${sbn.id}"
            val category = notification.category

            val deviceNotification = DeviceNotification(
                key = key,
                packageName = pkg,
                appName = appName,
                title = title.trim(),
                text = text.trim(),
                subText = subText?.trim(),
                timestamp = sbn.postTime,
                isOngoing = isOngoing,
                category = category,
            )

            NotificationStore.add(deviceNotification)
            Log.d(TAG, "Captured notification from $appName: \"$title\" - \"$text\"")
        } catch (e: Throwable) {
            Log.e(TAG, "Unexpected error in processStatusBarNotification: ${e.message}")
        }
    }
}
