package com.brahma.connect.notifications

import android.app.Notification
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log

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
            val componentName = ComponentName(context, BrahmaNotificationListenerService::class.java)
            val flat = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners")
            return flat != null && flat.contains(componentName.flattenToString())
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
        Log.i(TAG, "Brahma Notification Listener connected successfully.")
        // Sync currently active notifications on connect
        syncActiveNotifications()
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
        processStatusBarNotification(sbn)
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        super.onNotificationRemoved(sbn)
        if (sbn == null) return
        val key = sbn.key ?: "${sbn.packageName}_${sbn.id}"
        NotificationStore.remove(key)
    }

    fun syncActiveNotifications() {
        try {
            val active = activeNotifications ?: return
            for (sbn in active) {
                processStatusBarNotification(sbn)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error syncing active notifications: ${e.message}")
        }
    }

    private fun processStatusBarNotification(sbn: StatusBarNotification) {
        val pkg = sbn.packageName ?: return

        // Skip our own app notifications to prevent self-looping
        if (pkg == packageName) return

        val notification = sbn.notification ?: return
        val extras = notification.extras ?: return

        // Extract titles and messages
        val titleCharSeq = extras.getCharSequence(Notification.EXTRA_TITLE)
            ?: extras.getCharSequence(Notification.EXTRA_TITLE_BIG)
        val textCharSeq = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_MESSAGES)
        val subTextCharSeq = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_SUMMARY_TEXT)

        val title = titleCharSeq?.toString()?.trim().orEmpty()
        val text = textCharSeq?.toString()?.trim().orEmpty()
        val subText = subTextCharSeq?.toString()?.trim()

        // Skip empty or purely blank noise notifications
        if (title.isBlank() && text.isBlank()) return

        val isOngoing = sbn.isOngoing || (notification.flags and Notification.FLAG_ONGOING_EVENT) != 0

        val appName = try {
            val appInfo = packageManager.getApplicationInfo(pkg, 0)
            packageManager.getApplicationLabel(appInfo).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            pkg.substringAfterLast('.')
        }

        val key = sbn.key ?: "${pkg}_${sbn.id}"
        val category = notification.category

        val deviceNotification = DeviceNotification(
            key = key,
            packageName = pkg,
            appName = appName,
            title = title,
            text = text,
            subText = subText,
            timestamp = sbn.postTime,
            isOngoing = isOngoing,
            category = category,
        )

        NotificationStore.add(deviceNotification)
        Log.d(TAG, "Captured notification from $appName: \"$title\" - \"$text\"")
    }
}
