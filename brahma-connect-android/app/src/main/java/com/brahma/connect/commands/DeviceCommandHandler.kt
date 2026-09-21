package com.brahma.connect.commands

import android.Manifest
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.location.Location
import android.location.LocationManager
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.Settings
import android.telephony.SmsManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.brahma.connect.accessibility.BrahmaAccessibilityService
import com.brahma.connect.contacts.ContactsHelper
import com.brahma.connect.core.BrahmaConnectCapabilities
import com.brahma.connect.core.CommandResult
import com.brahma.connect.device.AndroidDeviceInfoProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File
import java.net.URLEncoder
import com.brahma.connect.media.UniversalMediaController
import com.brahma.connect.notifications.BrahmaNotificationListenerService
import com.brahma.connect.notifications.NotificationStore
import com.brahma.connect.telephony.CallLogReader

class DeviceCommandHandler(private val context: Context) {
    private val infoProvider = AndroidDeviceInfoProvider(context)
    private val mediaController = UniversalMediaController(context)
    private val callLogReader = CallLogReader(context)
    private val scope = CoroutineScope(Dispatchers.IO)

    fun handle(action: String, parameters: Map<String, Any?>): CommandResult {
        return when (action.lowercase().trim()) {
            // Screen Vision & UI Control
            "see_screen", "inspect_screen" -> seeScreen()
            "smart_ui_click", "click_element" -> smartUiClick(parameters)
            "smart_ui_type", "type_text" -> smartUiType(parameters)
            "smart_ui_scroll", "scroll_screen" -> smartUiScroll(parameters)
            "get_screen_text" -> getScreenText()
            "tap_coordinates" -> tapCoordinates(parameters)
            "press_key" -> pressKey(parameters)

            // Notifications Intelligence
            "get_notifications", "summarize_notifications", "read_notifications" -> getNotifications(parameters)
            "clear_notifications" -> clearNotifications()

            // App Automation
            "send_whatsapp", "send_whatsapp_message" -> sendWhatsApp(parameters)
            "play_media", "play_music", "play_youtube" -> playMedia(parameters)
            "media_control" -> mediaControl(parameters)
            "now_playing", "get_now_playing" -> getNowPlaying()
            "stop_everything", "emergency_stop" -> stopEverything()

            // Phone Telephony & Comms
            "make_call", "make_phone_call", "dial" -> makeCall(parameters)
            "get_missed_calls", "missed_calls" -> getMissedCalls(parameters)
            "get_call_log", "read_call_log", "recent_calls" -> getCallLog(parameters)
            "send_sms" -> sendSms(parameters)
            "read_sms", "audit_sms_inbox" -> readSms(parameters)
            "read_contacts", "search_contacts", "get_contacts" -> readContacts(parameters)

            // Hardware, Sensors & Device Control
            "get_location", "get_gps" -> getLocation()
            "vibrate", "vibrate_device" -> vibrateDevice(parameters)
            "set_brightness" -> setBrightness(parameters)
            "get_clipboard" -> getClipboard()
            "set_clipboard" -> setClipboard(parameters)
            "list_apps", "list_installed_apps" -> listApps(parameters)
            "control_system" -> controlSystem(parameters)
            "take_screenshot" -> takeScreenshot()

            // Core Device Controls
            "get_device_info" -> getDeviceInfo()
            "get_battery" -> getBattery()
            "flashlight_on" -> flashlight(true)
            "flashlight_off" -> flashlight(false)
            "launch_app" -> launchApp(parameters)
            "open_url" -> openUrl(parameters)
            "volume_get" -> volumeGet()
            "volume_set" -> volumeSet(parameters)
            "unlock_phone" -> unlockPhone(parameters)
            "lock_phone", "lock_screen" -> lockPhone()
            "set_dnd", "toggle_dnd" -> setDnd(parameters)

            // Storage & Files
            "file_list" -> fileList(parameters)
            "file_read" -> fileRead(parameters)
            "file_write" -> fileWrite(parameters)
            "file_delete" -> fileDelete(parameters)

            else -> CommandResult(false, errorCode = "UNKNOWN_COMMAND", error = "Unsupported command: $action")
        }
    }

    // ==========================================================
    // SCREEN VISION & ACCESSIBILITY AUTOMATION
    // ==========================================================

    private fun seeScreen(): CommandResult {
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(
                false,
                errorCode = "ACCESSIBILITY_DISABLED",
                error = "Brahma Accessibility Service is not enabled. Please enable it in Android Settings -> Accessibility."
            )
        val data = service.inspectScreen()
        val success = data["success"] as? Boolean ?: false
        return if (success) {
            CommandResult(true, data = data)
        } else {
            CommandResult(false, errorCode = "SCREEN_READ_FAILED", error = data["error"]?.toString() ?: "Screen unavailable")
        }
    }

    private fun smartUiClick(parameters: Map<String, Any?>): CommandResult {
        val target = parameters["target"]?.toString()
            ?: parameters["text"]?.toString()
            ?: parameters["id"]?.toString()
            ?: return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Target element or index required.")
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val data = service.clickElement(target)
        val success = data["success"] as? Boolean ?: false
        return if (success) {
            CommandResult(true, data = data)
        } else {
            CommandResult(false, errorCode = "CLICK_FAILED", error = data["error"]?.toString() ?: "Failed to click $target")
        }
    }

    private fun smartUiType(parameters: Map<String, Any?>): CommandResult {
        val text = parameters["text"]?.toString()
            ?: return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Text to type is required.")
        val target = parameters["target"]?.toString()
        val pressEnter = parameters["press_enter"] as? Boolean ?: false
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val data = service.typeText(target, text, pressEnter)
        val success = data["success"] as? Boolean ?: false
        return if (success) {
            CommandResult(true, data = data)
        } else {
            CommandResult(false, errorCode = "TYPE_FAILED", error = data["error"]?.toString() ?: "Failed to type text")
        }
    }

    private fun smartUiScroll(parameters: Map<String, Any?>): CommandResult {
        val direction = parameters["direction"]?.toString() ?: "down"
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val data = service.scrollScreen(direction)
        return CommandResult(data["success"] as? Boolean ?: false, data = data)
    }

    private fun getScreenText(): CommandResult {
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val text = service.getScreenText()
        return CommandResult(true, data = mapOf("screen_text" to text))
    }

    private fun tapCoordinates(parameters: Map<String, Any?>): CommandResult {
        val x = (parameters["x"] as? Number)?.toInt()
        val y = (parameters["y"] as? Number)?.toInt()
        if (x == null || y == null) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Both x and y coordinates are required.")
        }
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val ok = service.tapCoordinates(x, y)
        return CommandResult(ok, data = mapOf("x" to x, "y" to y))
    }

    private fun pressKey(parameters: Map<String, Any?>): CommandResult {
        val key = parameters["key"]?.toString() ?: "back"
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val data = service.pressKey(key)
        return CommandResult(data["success"] as? Boolean ?: false, data = data)
    }

    private fun takeScreenshot(): CommandResult {
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val data = service.pressKey("screenshot")
        return CommandResult(data["success"] as? Boolean ?: false, data = mapOf("message" to "Screenshot requested"))
    }

    // ==========================================================
    // AUTONOMOUS APP AUTOMATION (WHATSAPP, YOUTUBE, SPOTIFY)
    // ==========================================================

    private fun sendWhatsApp(parameters: Map<String, Any?>): CommandResult {
        val contactOrNumber = (parameters["contact"] ?: parameters["phone"] ?: parameters["number"])?.toString()?.trim().orEmpty()
        val message = (parameters["message"] ?: parameters["text"])?.toString()?.trim().orEmpty()
        val autoSend = parameters["auto_send"] as? Boolean ?: true

        if (contactOrNumber.isBlank()) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Contact name or phone number is required.")
        }

        var phoneNumber = contactOrNumber.replace(Regex("[^0-9+]"), "")
        var resolvedName = contactOrNumber

        // If not a raw phone number, look up in contacts
        if (phoneNumber.length < 7) {
            val contacts = ContactsHelper.fetchContacts(context)
            val matched = contacts.firstOrNull {
                it["name"]?.lowercase()?.contains(contactOrNumber.lowercase()) == true
            }
            if (matched != null) {
                phoneNumber = matched["phone"]?.replace(Regex("[^0-9+]"), "").orEmpty()
                resolvedName = matched["name"] ?: contactOrNumber
            }
        }

        if (phoneNumber.length < 7) {
            return CommandResult(false, errorCode = "CONTACT_NOT_FOUND", error = "Could not find a valid phone number for '$contactOrNumber'.")
        }

        val cleanDigits = phoneNumber.trimStart('+')
        val encodedMessage = runCatching { URLEncoder.encode(message, "UTF-8") }.getOrDefault(message)
        val intentUri = "https://api.whatsapp.com/send?phone=$cleanDigits&text=$encodedMessage"

        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(intentUri)).apply {
                setPackage("com.whatsapp")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)

            if (autoSend) {
                // Background coroutine to auto-click the Send button once WhatsApp opens
                scope.launch {
                    delay(2000)
                    val service = BrahmaAccessibilityService.instance
                    if (service != null) {
                        for (btn in listOf("Send", "send", "com.whatsapp:id/send")) {
                            val res = service.clickElement(btn)
                            if (res["success"] == true) break
                        }
                    }
                }
            }

            return CommandResult(
                true,
                data = mapOf(
                    "status" to if (autoSend) "Message sent" else "Draft opened",
                    "contact" to resolvedName,
                    "phone" to phoneNumber,
                    "message" to message,
                )
            )
        } catch (exc: Exception) {
            return CommandResult(false, errorCode = "WHATSAPP_LAUNCH_FAILED", error = exc.message ?: "Failed to open WhatsApp.")
        }
    }

    private fun playMedia(parameters: Map<String, Any?>): CommandResult {
        val query = (parameters["query"] ?: parameters["search"] ?: parameters["song"])?.toString()?.trim().orEmpty()
        val app = parameters["app"]?.toString()?.lowercase()?.trim() ?: "youtube"

        if (query.isBlank()) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Search query or song name is required.")
        }

        val encodedQuery = runCatching { URLEncoder.encode(query, "UTF-8") }.getOrDefault(query)

        return try {
            if (app.contains("spotify")) {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse("spotify:search:$encodedQuery")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                CommandResult(true, data = mapOf("app" to "Spotify", "query" to query, "status" to "Opened Spotify search"))
            } else {
                // YouTube by default
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse("vnd.youtube://www.youtube.com/results?search_query=$encodedQuery")).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                try {
                    context.startActivity(intent)
                } catch (e: Exception) {
                    val fallback = Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com/results?search_query=$encodedQuery")).apply {
                        setPackage("com.google.android.youtube")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    context.startActivity(fallback)
                }

                // Auto-tap first video result if accessibility active
                scope.launch {
                    delay(3000)
                    val service = BrahmaAccessibilityService.instance
                    if (service != null) {
                        service.inspectScreen()
                        delay(500)
                        // Click element 1 or 2
                        service.clickElement("[1]")
                    }
                }

                CommandResult(true, data = mapOf("app" to "YouTube", "query" to query, "status" to "Playing on YouTube"))
            }
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "MEDIA_PLAY_FAILED", error = exc.message ?: "Failed to play media.")
        }
    }

    // ==========================================================
    // TELEPHONY, SMS & CONTACTS
    // ==========================================================

    private fun makeCall(parameters: Map<String, Any?>): CommandResult {
        val target = (parameters["phone"] ?: parameters["number"] ?: parameters["contact"])?.toString()?.trim().orEmpty()
        if (target.isBlank()) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Phone number or contact is required.")
        }

        var number = target.replace(Regex("[^0-9+]"), "")
        if (number.length < 7) {
            val contacts = ContactsHelper.fetchContacts(context)
            val matched = contacts.firstOrNull { it["name"]?.lowercase()?.contains(target.lowercase()) == true }
            if (matched != null) {
                number = matched["phone"]?.replace(Regex("[^0-9+]"), "").orEmpty()
            }
        }

        if (number.length < 7) {
            return CommandResult(false, errorCode = "CONTACT_NOT_FOUND", error = "Could not find phone number for '$target'.")
        }

        return try {
            val hasCallPerm = ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE) == PackageManager.PERMISSION_GRANTED
            val action = if (hasCallPerm) Intent.ACTION_CALL else Intent.ACTION_DIAL
            val intent = Intent(action, Uri.parse("tel:$number")).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            CommandResult(true, data = mapOf("action" to if (hasCallPerm) "placed_call" else "opened_dialer", "number" to number))
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "CALL_FAILED", error = exc.message ?: "Failed to initiate call.")
        }
    }

    private fun sendSms(parameters: Map<String, Any?>): CommandResult {
        val target = (parameters["phone"] ?: parameters["number"] ?: parameters["contact"])?.toString()?.trim().orEmpty()
        val message = (parameters["message"] ?: parameters["text"])?.toString()?.trim().orEmpty()

        if (target.isBlank() || message.isBlank()) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Both phone number and message are required.")
        }

        var number = target.replace(Regex("[^0-9+]"), "")
        if (number.length < 7) {
            val contacts = ContactsHelper.fetchContacts(context)
            val matched = contacts.firstOrNull { it["name"]?.lowercase()?.contains(target.lowercase()) == true }
            if (matched != null) {
                number = matched["phone"]?.replace(Regex("[^0-9+]"), "").orEmpty()
            }
        }

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) != PackageManager.PERMISSION_GRANTED) {
            // Fallback: Open SMS app with draft
            val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:$number")).apply {
                putExtra("sms_body", message)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            return CommandResult(true, data = mapOf("status" to "drafted", "note" to "SMS drafted in app. Send permission not granted."))
        }

        return try {
            val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                context.getSystemService(SmsManager::class.java)
            } else {
                @Suppress("DEPRECATION")
                SmsManager.getDefault()
            }
            smsManager.sendTextMessage(number, null, message, null, null)
            CommandResult(true, data = mapOf("status" to "sent", "to" to number, "message" to message))
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "SMS_SEND_FAILED", error = exc.message ?: "Failed to send SMS.")
        }
    }

    private fun readSms(parameters: Map<String, Any?>): CommandResult {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED) {
            return CommandResult(false, errorCode = "PERMISSION_DENIED", error = "READ_SMS permission is not granted.")
        }
        val limit = (parameters["limit"] as? Number)?.toInt() ?: 5
        val messages = mutableListOf<Map<String, Any?>>()

        return try {
            val cursor = context.contentResolver.query(
                Uri.parse("content://sms/inbox"),
                arrayOf("address", "body", "date"),
                null,
                null,
                "date DESC LIMIT $limit"
            )
            cursor?.use {
                val addrIdx = it.getColumnIndex("address")
                val bodyIdx = it.getColumnIndex("body")
                val dateIdx = it.getColumnIndex("date")
                while (it.moveToNext()) {
                    messages.add(
                        mapOf(
                            "from" to (if (addrIdx != -1) it.getString(addrIdx) else "Unknown"),
                            "body" to (if (bodyIdx != -1) it.getString(bodyIdx) else ""),
                            "timestamp" to (if (dateIdx != -1) it.getLong(dateIdx) else 0L)
                        )
                    )
                }
            }
            CommandResult(true, data = mapOf("messages" to messages))
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "READ_SMS_FAILED", error = exc.message ?: "Failed to read SMS.")
        }
    }

    private fun readContacts(parameters: Map<String, Any?>): CommandResult {
        val query = parameters["query"]?.toString()?.trim().orEmpty()
        val all = ContactsHelper.fetchContacts(context)
        val filtered = if (query.isBlank()) {
            all.take(50)
        } else {
            all.filter {
                it["name"]?.contains(query, ignoreCase = true) == true ||
                        it["phone"]?.contains(query) == true
            }
        }
        return CommandResult(true, data = mapOf("count" to filtered.size, "contacts" to filtered))
    }

    // ==========================================================
    // HARDWARE, SENSORS & SYSTEM CONTROLS
    // ==========================================================

    private fun getLocation(): CommandResult {
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

        if (!fine && !coarse) {
            return CommandResult(false, errorCode = "PERMISSION_DENIED", error = "Location permissions are not granted.")
        }

        val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
            ?: return CommandResult(false, errorCode = "LOCATION_UNAVAILABLE", error = "Location service unavailable.")

        var bestLocation: Location? = null
        for (provider in lm.getProviders(true)) {
            try {
                val loc = lm.getLastKnownLocation(provider) ?: continue
                if (bestLocation == null || loc.accuracy < bestLocation.accuracy) {
                    bestLocation = loc
                }
            } catch (ignored: SecurityException) {}
        }

        return if (bestLocation != null) {
            CommandResult(
                true,
                data = mapOf(
                    "latitude" to bestLocation.latitude,
                    "longitude" to bestLocation.longitude,
                    "accuracy" to bestLocation.accuracy,
                    "altitude" to bestLocation.altitude,
                    "provider" to bestLocation.provider,
                )
            )
        } else {
            CommandResult(false, errorCode = "NO_FIX", error = "No recent GPS/Network location fix available.")
        }
    }

    private fun vibrateDevice(parameters: Map<String, Any?>): CommandResult {
        val duration = (parameters["duration_ms"] as? Number)?.toLong() ?: 500L
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
            vm?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        } ?: return CommandResult(false, errorCode = "VIBRATOR_UNAVAILABLE", error = "Vibrator unavailable.")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(duration, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(duration)
        }
        return CommandResult(true, data = mapOf("vibrated_ms" to duration))
    }

    private fun setBrightness(parameters: Map<String, Any?>): CommandResult {
        val level = (parameters["level"] as? Number)?.toInt()?.coerceIn(0, 255)
            ?: return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Brightness level (0-255) required.")

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.System.canWrite(context)) {
            val intent = Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS).apply {
                data = Uri.parse("package:${context.packageName}")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            CommandResult(false, errorCode = "WRITE_SETTINGS_REQUIRED", error = "Write settings permission required. Opened settings.")
        } else {
            try {
                Settings.System.putInt(context.contentResolver, Settings.System.SCREEN_BRIGHTNESS, level)
                CommandResult(true, data = mapOf("brightness" to level))
            } catch (exc: Exception) {
                CommandResult(false, errorCode = "BRIGHTNESS_FAILED", error = exc.message ?: "Failed to set brightness.")
            }
        }
    }

    private fun getClipboard(): CommandResult {
        val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            ?: return CommandResult(false, errorCode = "CLIPBOARD_UNAVAILABLE", error = "Clipboard unavailable.")
        val clip = cm.primaryClip
        val text = if (clip != null && clip.itemCount > 0) clip.getItemAt(0).text?.toString().orEmpty() else ""
        return CommandResult(true, data = mapOf("clipboard" to text))
    }

    private fun setClipboard(parameters: Map<String, Any?>): CommandResult {
        val text = parameters["text"]?.toString().orEmpty()
        val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            ?: return CommandResult(false, errorCode = "CLIPBOARD_UNAVAILABLE", error = "Clipboard unavailable.")
        val clip = ClipData.newPlainText("JARVIS", text)
        cm.setPrimaryClip(clip)
        return CommandResult(true, data = mapOf("copied" to text))
    }

    private fun listApps(parameters: Map<String, Any?>): CommandResult {
        val userOnly = parameters["user_only"] as? Boolean ?: true
        val pm = context.packageManager
        val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
        val result = apps.filter {
            if (userOnly) (it.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) == 0 else true
        }.map {
            mapOf(
                "name" to pm.getApplicationLabel(it).toString(),
                "package" to it.packageName,
            )
        }.sortedBy { it["name"] }
        return CommandResult(true, data = mapOf("count" to result.size, "apps" to result))
    }

    private fun controlSystem(parameters: Map<String, Any?>): CommandResult {
        val action = parameters["action"]?.toString()?.lowercase()?.trim().orEmpty()
        val intent = when (action) {
            "wifi" -> Intent(Settings.ACTION_WIFI_SETTINGS)
            "bluetooth" -> Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
            "dnd", "do_not_disturb" -> Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS)
            "display", "dark_mode" -> Intent(Settings.ACTION_DISPLAY_SETTINGS)
            else -> Intent(Settings.ACTION_SETTINGS)
        }.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
        return CommandResult(true, data = mapOf("opened_settings" to action))
    }

    // ==========================================================
    // CORE DEVICE CONTROLS (EXISTING)
    // ==========================================================

    private fun getDeviceInfo(): CommandResult {
        val battery = infoProvider.batterySnapshot()
        return CommandResult(
            success = true,
            data = mapOf(
                "device_id" to null,
                "device_name" to (Build.MODEL ?: "Android"),
                "platform" to "android",
                "android_version" to (Build.VERSION.RELEASE ?: "Unknown"),
                "agent_version" to "1.1.0",
                "model" to (Build.MODEL ?: "Android"),
                "battery" to battery.first,
                "charging" to battery.second,
                "wifi_state" to if (infoProvider.wifiEnabled()) "connected" else "disconnected",
                "accessibility_active" to BrahmaAccessibilityService.isRunning,
                "capabilities" to BrahmaConnectCapabilities.INITIAL,
            ),
        )
    }

    private fun getBattery(): CommandResult {
        val battery = infoProvider.batterySnapshot()
        return CommandResult(true, data = mapOf("percentage" to battery.first, "charging" to battery.second))
    }

    private fun flashlight(enabled: Boolean): CommandResult {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            return CommandResult(
                false,
                errorCode = "CAMERA_PERMISSION_REQUIRED",
                error = "Camera permission is required to control the flashlight.",
            )
        }
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as? CameraManager
            ?: return CommandResult(false, errorCode = "FLASHLIGHT_UNAVAILABLE", error = "Camera service unavailable.")
        val cameraId = manager.cameraIdList.firstOrNull { id ->
            runCatching {
                val chars = manager.getCameraCharacteristics(id)
                val flash = chars.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
                val facing = chars.get(CameraCharacteristics.LENS_FACING)
                flash && (facing == CameraCharacteristics.LENS_FACING_BACK || facing == CameraCharacteristics.LENS_FACING_EXTERNAL)
            }.getOrDefault(false)
        } ?: return CommandResult(false, errorCode = "FLASHLIGHT_UNAVAILABLE", error = "No flashlight on this device.")
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val maxStrength = runCatching {
                    manager.getCameraCharacteristics(cameraId).get(CameraCharacteristics.FLASH_INFO_STRENGTH_MAXIMUM_LEVEL) ?: 1
                }.getOrDefault(1)
                if (enabled && maxStrength > 1) {
                    manager.turnOnTorchWithStrengthLevel(cameraId, maxStrength)
                } else {
                    manager.setTorchMode(cameraId, enabled)
                }
            } else {
                manager.setTorchMode(cameraId, enabled)
            }
            CommandResult(true, data = mapOf("flashlight" to if (enabled) "on" else "off"))
        } catch (security: SecurityException) {
            CommandResult(false, errorCode = "FLASHLIGHT_UNAVAILABLE", error = security.message ?: "Flashlight permission denied.")
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "FLASHLIGHT_UNAVAILABLE", error = exc.message ?: "Flashlight unavailable.")
        }
    }

    private fun launchApp(parameters: Map<String, Any?>): CommandResult {
        val requested = listOf("package", "package_name", "app_name", "app", "name")
            .firstNotNullOfOrNull { key -> parameters[key]?.toString()?.trim() }
            .orEmpty()
        if (requested.isBlank()) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "App name or package name is required.")
        }

        val packageName = resolveLaunchablePackage(requested)
            ?: requested.takeIf { context.packageManager.getLaunchIntentForPackage(it) != null }
            ?: return CommandResult(false, errorCode = "APP_NOT_FOUND", error = "Package not found: $requested")

        val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            ?: return CommandResult(false, errorCode = "APP_NOT_FOUND", error = "Package not found: $packageName")
        return try {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            CommandResult(true, data = mapOf("package" to packageName, "app_name" to requested))
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "APP_NOT_FOUND", error = exc.message ?: "Unable to launch app.")
        }
    }

    private fun resolveLaunchablePackage(requested: String): String? {
        val normalizedRequested = normalizeAppQuery(requested)
        if (normalizedRequested.isBlank()) return null

        val launcherIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val launchableApps = runCatching {
            context.packageManager.queryIntentActivities(launcherIntent, 0)
        }.getOrDefault(emptyList())

        fun labelOf(info: ResolveInfo): String {
            return info.loadLabel(context.packageManager)?.toString().orEmpty()
        }

        val exactMatch = launchableApps.firstOrNull { info ->
            val label = normalizeAppQuery(labelOf(info))
            val packageId = normalizeAppQuery(info.activityInfo.packageName)
            normalizedRequested == label || normalizedRequested == packageId
        }
        if (exactMatch != null) return exactMatch.activityInfo.packageName

        val containsMatch = launchableApps.firstOrNull { info ->
            val label = normalizeAppQuery(labelOf(info))
            val packageId = normalizeAppQuery(info.activityInfo.packageName)
            label.contains(normalizedRequested) ||
                    normalizedRequested.contains(label) ||
                    packageId.contains(normalizedRequested) ||
                    normalizedRequested.contains(packageId)
        }
        return containsMatch?.activityInfo?.packageName
    }

    private fun normalizeAppQuery(value: String): String {
        return value.lowercase().replace(Regex("[^a-z0-9]+"), "")
    }

    private fun openUrl(parameters: Map<String, Any?>): CommandResult {
        val url = (parameters["url"] ?: parameters["link"])?.toString()?.trim().orEmpty()
        if (url.isBlank()) {
            return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "URL is required.")
        }
        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            CommandResult(true, data = mapOf("url" to url))
        } catch (exc: Exception) {
            CommandResult(false, errorCode = "OPEN_URL_FAILED", error = exc.message ?: "Unable to open URL.")
        }
    }

    private fun volumeGet(): CommandResult {
        val audio = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return CommandResult(false, errorCode = "AUDIO_UNAVAILABLE", error = "Audio service unavailable.")
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val current = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
        val percentage = ((current * 100f) / max).toInt().coerceIn(0, 100)
        return CommandResult(true, data = mapOf("stream" to "music", "percentage" to percentage, "current" to current, "max" to max))
    }

    private fun volumeSet(parameters: Map<String, Any?>): CommandResult {
        val audio = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return CommandResult(false, errorCode = "AUDIO_UNAVAILABLE", error = "Audio service unavailable.")
        val targetRaw = parameters["value"] ?: parameters["percentage"]
        ?: return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Volume value is required.")
        val target = when (targetRaw) {
            is Number -> targetRaw.toInt()
            else -> targetRaw.toString().toIntOrNull()
        } ?: return CommandResult(false, errorCode = "INVALID_ARGUMENT", error = "Volume value must be numeric.")
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val clamped = target.coerceIn(0, 100)
        val level = ((clamped / 100f) * max).toInt().coerceIn(0, max)
        audio.setStreamVolume(AudioManager.STREAM_MUSIC, level, 0)
        return CommandResult(true, data = mapOf("stream" to "music", "percentage" to clamped, "current" to level, "max" to max))
    }

    private fun unlockPhone(parameters: Map<String, Any?>): CommandResult {
        val pin = parameters["pin"]?.toString().orEmpty()
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Brahma Accessibility Service is not enabled.")
        val success = service.unlockPhone(pin)
        return if (success) {
            CommandResult(true, data = mapOf("message" to "Unlock sequence executed."))
        } else {
            CommandResult(false, errorCode = "UNLOCK_FAILED", error = "Failed to unlock.")
        }
    }

    // ==========================================================
    // STORAGE & FILES
    // ==========================================================

    private fun resolveFileTarget(path: String?): File {
        val storage = android.os.Environment.getExternalStorageDirectory()
        if (path.isNullOrBlank() || path.equals("home", ignoreCase = true)) {
            return storage
        }
        val lower = path.lowercase().trim()
        val baseDir = when (lower) {
            "downloads" -> android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
            "documents" -> android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOCUMENTS)
            "pictures" -> android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_PICTURES)
            "music" -> android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_MUSIC)
            "movies", "videos" -> android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_MOVIES)
            else -> File(storage, path)
        }
        return baseDir
    }

    private fun fileList(parameters: Map<String, Any?>): CommandResult {
        val path = parameters["path"]?.toString()
        val dir = resolveFileTarget(path)
        if (!dir.exists() || !dir.isDirectory) {
            return CommandResult(false, errorCode = "NOT_FOUND", error = "Directory not found: ${dir.absolutePath}")
        }
        val items = dir.listFiles()?.map { file ->
            mapOf(
                "name" to file.name,
                "is_dir" to file.isDirectory,
                "size" to file.length(),
                "path" to file.absolutePath
            )
        } ?: emptyList()
        return CommandResult(true, data = mapOf("items" to items, "path" to dir.absolutePath))
    }

    private fun fileRead(parameters: Map<String, Any?>): CommandResult {
        val path = parameters["path"]?.toString()
        val file = resolveFileTarget(path)
        if (!file.exists() || !file.isFile) {
            return CommandResult(false, errorCode = "NOT_FOUND", error = "File not found: ${file.absolutePath}")
        }
        return try {
            val content = file.readText()
            CommandResult(true, data = mapOf("content" to content, "path" to file.absolutePath))
        } catch (e: Exception) {
            CommandResult(false, errorCode = "READ_ERROR", error = e.message ?: "Failed to read file.")
        }
    }

    private fun fileWrite(parameters: Map<String, Any?>): CommandResult {
        val path = parameters["path"]?.toString()
        val content = parameters["content"]?.toString() ?: ""
        val append = parameters["append"] as? Boolean ?: false
        val file = resolveFileTarget(path)
        return try {
            file.parentFile?.mkdirs()
            if (append) {
                file.appendText(content)
            } else {
                file.writeText(content)
            }
            CommandResult(true, data = mapOf("message" to "File written successfully.", "path" to file.absolutePath))
        } catch (e: Exception) {
            CommandResult(false, errorCode = "WRITE_ERROR", error = e.message ?: "Failed to write file.")
        }
    }

    private fun fileDelete(parameters: Map<String, Any?>): CommandResult {
        val path = parameters["path"]?.toString()
        val file = resolveFileTarget(path)
        if (!file.exists()) {
            return CommandResult(false, errorCode = "NOT_FOUND", error = "File or directory not found: ${file.absolutePath}")
        }
        return try {
            val success = if (file.isDirectory) file.deleteRecursively() else file.delete()
            if (success) {
                CommandResult(true, data = mapOf("message" to "Deleted successfully.", "path" to file.absolutePath))
            } else {
                CommandResult(false, errorCode = "DELETE_FAILED", error = "Failed to delete.")
            }
        } catch (e: Exception) {
            CommandResult(false, errorCode = "DELETE_ERROR", error = e.message ?: "Failed to delete file.")
        }
    }

    // ==========================================================
    // NOTIFICATION INTELLIGENCE
    // ==========================================================

    private fun getNotifications(parameters: Map<String, Any?>): CommandResult {
        val limit = (parameters["limit"] as? Number)?.toInt() ?: 20
        val packageFilter = parameters["package"]?.toString() ?: parameters["app"]?.toString()
        val includeOngoing = parameters["include_ongoing"] as? Boolean ?: false

        val listenerActive = BrahmaNotificationListenerService.instance != null
        val permissionGranted = BrahmaNotificationListenerService.isPermissionGranted(context)

        if (!permissionGranted && !listenerActive) {
            return CommandResult(
                false,
                errorCode = "NOTIFICATION_ACCESS_DISABLED",
                error = "Notification access is not enabled. Please enable Brahma Connect in Android Settings -> Notification Access."
            )
        }

        // Sync active notifications if listener is bound
        BrahmaNotificationListenerService.instance?.syncActiveNotifications()

        val recent = NotificationStore.getRecent(
            limit = limit,
            packageFilter = packageFilter,
            excludeOngoing = !includeOngoing
        ).map { it.toMap() }

        return CommandResult(
            true,
            data = mapOf(
                "count" to recent.size,
                "notifications" to recent,
                "listener_active" to listenerActive
            )
        )
    }

    private fun clearNotifications(): CommandResult {
        NotificationStore.clear()
        return CommandResult(true, data = mapOf("message" to "Notification history cleared."))
    }

    // ==========================================================
    // CALL LOG & TELEPHONY
    // ==========================================================

    private fun getMissedCalls(parameters: Map<String, Any?>): CommandResult {
        if (!callLogReader.hasPermission()) {
            return CommandResult(
                false,
                errorCode = "PERMISSION_DENIED",
                error = "Call Log permission (READ_CALL_LOG) is required to check missed calls."
            )
        }
        val limit = (parameters["limit"] as? Number)?.toInt() ?: 10
        val missed = callLogReader.getMissedCalls(limit)
        return CommandResult(
            true,
            data = mapOf(
                "count" to missed.size,
                "missed_calls" to missed
            )
        )
    }

    private fun getCallLog(parameters: Map<String, Any?>): CommandResult {
        if (!callLogReader.hasPermission()) {
            return CommandResult(
                false,
                errorCode = "PERMISSION_DENIED",
                error = "Call Log permission (READ_CALL_LOG) is required to view call history."
            )
        }
        val limit = (parameters["limit"] as? Number)?.toInt() ?: 15
        val type = parameters["type"]?.toString()
        val calls = callLogReader.getRecentCalls(limit, type)
        return CommandResult(
            true,
            data = mapOf(
                "count" to calls.size,
                "calls" to calls
            )
        )
    }

    // ==========================================================
    // UNIVERSAL MEDIA CONTROLLER & STOP EVERYTHING
    // ==========================================================

    private fun mediaControl(parameters: Map<String, Any?>): CommandResult {
        val mediaAction = (parameters["media_action"] ?: parameters["sub_action"] ?: parameters["action"])?.toString() ?: "toggle"
        val success = mediaController.executeAction(mediaAction)
        val nowPlaying = mediaController.getNowPlaying()
        return CommandResult(
            success,
            data = mapOf(
                "action" to mediaAction,
                "now_playing" to nowPlaying
            )
        )
    }

    private fun getNowPlaying(): CommandResult {
        val info = mediaController.getNowPlaying()
        return CommandResult(true, data = info)
    }

    private fun stopEverything(): CommandResult {
        val res = mediaController.stopEverything()
        return CommandResult(true, data = res)
    }

    private fun lockPhone(): CommandResult {
        val service = BrahmaAccessibilityService.instance
            ?: return CommandResult(false, errorCode = "ACCESSIBILITY_DISABLED", error = "Accessibility service is disabled.")
        val res = service.pressKey("lock")
        return CommandResult(res["success"] as? Boolean ?: false, data = mapOf("message" to "Phone locked."))
    }

    private fun setDnd(parameters: Map<String, Any?>): CommandResult {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            ?: return CommandResult(false, errorCode = "DND_UNAVAILABLE", error = "Notification manager unavailable.")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !nm.isNotificationPolicyAccessGranted) {
            val intent = Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            return CommandResult(
                false,
                errorCode = "DND_ACCESS_REQUIRED",
                error = "DND policy access is required. Settings screen has been opened."
            )
        }

        val enable = when (val v = parameters["enable"] ?: parameters["enabled"] ?: parameters["state"]) {
            is Boolean -> v
            is String -> v.lowercase().trim() in listOf("true", "on", "yes", "enable", "1", "silent")
            else -> true
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val filter = if (enable) NotificationManager.INTERRUPTION_FILTER_PRIORITY else NotificationManager.INTERRUPTION_FILTER_ALL
            nm.setInterruptionFilter(filter)
        }
        return CommandResult(true, data = mapOf("dnd_enabled" to enable))
    }
}
