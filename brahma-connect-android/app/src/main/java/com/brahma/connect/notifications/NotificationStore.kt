package com.brahma.connect.notifications

import java.util.concurrent.CopyOnWriteArrayList

/**
 * Data representation of a captured system notification.
 */
data class DeviceNotification(
    val key: String,
    val packageName: String,
    val appName: String,
    val title: String,
    val text: String,
    val subText: String? = null,
    val timestamp: Long = System.currentTimeMillis(),
    val isOngoing: Boolean = false,
    val category: String? = null,
) {
    fun toMap(): Map<String, Any?> {
        return mapOf(
            "key" to key,
            "package" to packageName,
            "app_name" to appName,
            "title" to title,
            "text" to text,
            "sub_text" to subText,
            "timestamp" to timestamp,
            "is_ongoing" to isOngoing,
            "category" to category,
        )
    }
}

/**
 * Thread-safe in-memory ring buffer holding recent notifications.
 * Preserves privacy by keeping notifications in RAM only (not persistent on disk).
 */
object NotificationStore {
    private const val MAX_CAPACITY = 60
    private val notifications = CopyOnWriteArrayList<DeviceNotification>()

    fun add(notification: DeviceNotification) {
        // Remove duplicate if key already exists (e.g. notification update)
        notifications.removeIf { it.key == notification.key }
        notifications.add(0, notification)

        // Trim to capacity
        while (notifications.size > MAX_CAPACITY) {
            notifications.removeAt(notifications.size - 1)
        }
    }

    fun remove(key: String) {
        notifications.removeIf { it.key == key }
    }

    fun getRecent(
        limit: Int = 20,
        packageFilter: String? = null,
        excludeOngoing: Boolean = true
    ): List<DeviceNotification> {
        return notifications.asSequence()
            .filter { if (excludeOngoing) !it.isOngoing else true }
            .filter { if (!packageFilter.isNullOrBlank()) it.packageName.contains(packageFilter, ignoreCase = true) else true }
            .take(limit.coerceIn(1, MAX_CAPACITY))
            .toList()
    }

    fun clear() {
        notifications.clear()
    }

    fun count(): Int = notifications.size
}
