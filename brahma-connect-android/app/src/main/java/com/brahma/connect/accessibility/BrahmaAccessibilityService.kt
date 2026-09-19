package com.brahma.connect.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.brahma.connect.core.AgentStateStore

data class UiElementInfo(
    val index: Int,
    val text: String,
    val contentDesc: String,
    val viewId: String,
    val className: String,
    val isClickable: Boolean,
    val isEditable: Boolean,
    val bounds: Rect,
    val center: Pair<Int, Int>,
)

class BrahmaAccessibilityService : AccessibilityService() {

    private val cachedElements = mutableListOf<UiElementInfo>()

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Active event monitoring
    }

    override fun onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted.")
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        AgentStateStore.addLog("Accessibility Bridge connected and active.")
        instance = this
    }

    override fun onDestroy() {
        super.onDestroy()
        if (instance == this) {
            instance = null
        }
    }

    // ==========================================
    // 1. SCREEN VISION & INSPECTION (see_screen)
    // ==========================================
    fun inspectScreen(): Map<String, Any?> {
        val root = rootInActiveWindow ?: return mapOf(
            "success" to false,
            "error" to "No active window available. Ensure phone screen is on and unlocked."
        )

        cachedElements.clear()
        val activePkg = root.packageName?.toString() ?: "unknown"
        val elements = mutableListOf<Map<String, Any?>>()
        val displayMetrics = resources.displayMetrics
        val screenWidth = displayMetrics.widthPixels
        val screenHeight = displayMetrics.heightPixels

        var counter = 1

        fun traverse(node: AccessibilityNodeInfo?) {
            if (node == null) return

            val rect = Rect()
            node.getBoundsInScreen(rect)

            val text = node.text?.toString()?.trim().orEmpty()
            val desc = node.contentDescription?.toString()?.trim().orEmpty()
            val viewId = node.viewIdResourceName?.toString()?.trim().orEmpty()
            val cls = node.className?.toString()?.trim().orEmpty()
            val isClickable = node.isClickable || node.isCheckable
            val isEditable = node.isEditable

            val isVisible = rect.width() > 0 && rect.height() > 0 &&
                    rect.bottom >= 0 && rect.right >= 0 &&
                    rect.top <= screenHeight && rect.left <= screenWidth

            if (isVisible && (text.isNotBlank() || desc.isNotBlank() || isClickable || isEditable)) {
                val center = Pair(rect.centerX(), rect.centerY())
                val el = UiElementInfo(
                    index = counter,
                    text = text,
                    contentDesc = desc,
                    viewId = viewId,
                    className = cls,
                    isClickable = isClickable,
                    isEditable = isEditable,
                    bounds = rect,
                    center = center,
                )
                cachedElements.add(el)

                val label = when {
                    text.isNotBlank() && desc.isNotBlank() -> "$text ($desc)"
                    text.isNotBlank() -> text
                    desc.isNotBlank() -> desc
                    viewId.isNotBlank() -> viewId.substringAfterLast("/")
                    else -> cls.substringAfterLast(".")
                }

                elements.add(
                    mapOf(
                        "index" to counter,
                        "label" to label,
                        "text" to text,
                        "desc" to desc,
                        "id" to viewId,
                        "clickable" to isClickable,
                        "editable" to isEditable,
                        "center" to listOf(center.first, center.second),
                    )
                )
                counter++
            }

            for (i in 0 until node.childCount) {
                traverse(node.getChild(i))
            }
        }

        try {
            traverse(root)
        } catch (exc: Exception) {
            Log.e(TAG, "Error traversing accessibility tree: ${exc.message}")
        }

        return mapOf(
            "success" to true,
            "active_package" to activePkg,
            "element_count" to cachedElements.size,
            "elements" to elements,
            "screen_size" to listOf(screenWidth, screenHeight),
        )
    }

    // ==========================================
    // 2. TEXT DUMP (get_screen_text)
    // ==========================================
    fun getScreenText(): String {
        val root = rootInActiveWindow ?: return "Unable to read screen text. Screen may be locked or off."
        val textLines = mutableListOf<String>()
        val seen = mutableSetOf<String>()

        fun extractText(node: AccessibilityNodeInfo?) {
            if (node == null) return
            val text = node.text?.toString()?.trim().orEmpty()
            val desc = node.contentDescription?.toString()?.trim().orEmpty()
            if (text.isNotBlank() && seen.add(text)) {
                textLines.add(text)
            } else if (desc.isNotBlank() && seen.add(desc)) {
                textLines.add(desc)
            }
            for (i in 0 until node.childCount) {
                extractText(node.getChild(i))
            }
        }

        extractText(root)
        return if (textLines.isEmpty()) "No readable text found on current screen." else textLines.joinToString("\n")
    }

    // ==========================================
    // 3. SMART UI CLICK (smart_ui_click)
    // ==========================================
    fun clickElement(target: String): Map<String, Any?> {
        val cleanTarget = target.trim()
        if (cleanTarget.isBlank()) {
            return mapOf("success" to false, "error" to "Click target cannot be blank.")
        }

        // 1. Check if target is an index: "[1]" or "1"
        val indexMatch = Regex("\\[?(\\d+)\\]?").matchEntire(cleanTarget)
        if (indexMatch != null) {
            val idx = indexMatch.groupValues[1].toIntOrNull()
            val matched = cachedElements.firstOrNull { it.index == idx }
            if (matched != null) {
                tapCoordinates(matched.center.first, matched.center.second)
                return mapOf(
                    "success" to true,
                    "target" to cleanTarget,
                    "matched_label" to (matched.text.ifBlank { matched.contentDesc }),
                    "tapped_coords" to listOf(matched.center.first, matched.center.second),
                )
            }
        }

        // 2. Try searching by text or description in cachedElements
        val lower = cleanTarget.lowercase()
        val cachedMatch = cachedElements.firstOrNull {
            it.text.lowercase().contains(lower) ||
                    it.contentDesc.lowercase().contains(lower) ||
                    it.viewId.lowercase().contains(lower)
        }
        if (cachedMatch != null) {
            tapCoordinates(cachedMatch.center.first, cachedMatch.center.second)
            return mapOf(
                "success" to true,
                "target" to cleanTarget,
                "matched_label" to (cachedMatch.text.ifBlank { cachedMatch.contentDesc }),
                "tapped_coords" to listOf(cachedMatch.center.first, cachedMatch.center.second),
            )
        }

        // 3. Try searching active window nodes directly
        val root = rootInActiveWindow ?: return mapOf(
            "success" to false,
            "error" to "Could not find '$cleanTarget' and active window unavailable."
        )

        var foundNode: AccessibilityNodeInfo? = null
        val rect = Rect()

        fun searchNode(node: AccessibilityNodeInfo?) {
            if (node == null || foundNode != null) return
            val t = node.text?.toString()?.lowercase().orEmpty()
            val d = node.contentDescription?.toString()?.lowercase().orEmpty()
            val id = node.viewIdResourceName?.toString()?.lowercase().orEmpty()

            if (t.contains(lower) || d.contains(lower) || id.contains(lower)) {
                foundNode = node
                return
            }
            for (i in 0 until node.childCount) {
                searchNode(node.getChild(i))
            }
        }

        searchNode(root)
        if (foundNode != null) {
            foundNode!!.getBoundsInScreen(rect)
            val cx = rect.centerX()
            val cy = rect.centerY()
            tapCoordinates(cx, cy)
            return mapOf(
                "success" to true,
                "target" to cleanTarget,
                "tapped_coords" to listOf(cx, cy),
            )
        }

        return mapOf(
            "success" to false,
            "error" to "Element matching '$cleanTarget' not found on current screen."
        )
    }

    // ==========================================
    // 4. TAP EXACT COORDINATES (tap_coordinates)
    // ==========================================
    fun tapCoordinates(x: Int, y: Int): Boolean {
        val path = Path().apply {
            moveTo(x.toFloat(), y.toFloat())
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 50)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        return dispatchGesture(gesture, null, null)
    }

    // ==========================================
    // 5. TYPE TEXT (smart_ui_type)
    // ==========================================
    fun typeText(target: String?, text: String, pressEnter: Boolean = false): Map<String, Any?> {
        val root = rootInActiveWindow ?: return mapOf("success" to false, "error" to "Screen not accessible.")

        var targetNode: AccessibilityNodeInfo? = null

        if (!target.isNullOrBlank()) {
            val lower = target.trim().lowercase()
            fun findEditable(node: AccessibilityNodeInfo?) {
                if (node == null || targetNode != null) return
                val t = node.text?.toString()?.lowercase().orEmpty()
                val d = node.contentDescription?.toString()?.lowercase().orEmpty()
                val id = node.viewIdResourceName?.toString()?.lowercase().orEmpty()
                if (node.isEditable || t.contains(lower) || d.contains(lower) || id.contains(lower)) {
                    if (t.contains(lower) || d.contains(lower) || id.contains(lower) || node.isEditable) {
                        targetNode = node
                        return
                    }
                }
                for (i in 0 until node.childCount) {
                    findEditable(node.getChild(i))
                }
            }
            findEditable(root)
        } else {
            // Find currently focused or first editable element
            targetNode = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            if (targetNode == null) {
                fun findFirstEditable(node: AccessibilityNodeInfo?) {
                    if (node == null || targetNode != null) return
                    if (node.isEditable) {
                        targetNode = node
                        return
                    }
                    for (i in 0 until node.childCount) {
                        findFirstEditable(node.getChild(i))
                    }
                }
                findFirstEditable(root)
            }
        }

        if (targetNode != null) {
            targetNode!!.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            val arguments = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
            }
            val setResult = targetNode!!.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
            return mapOf(
                "success" to setResult,
                "text" to text,
                "entered_in" to (targetNode?.viewIdResourceName ?: "focused_field")
            )
        }

        // Fallback: Click target coordinate then paste
        if (!target.isNullOrBlank()) {
            clickElement(target)
        }
        return mapOf(
            "success" to false,
            "error" to "No editable text field located on screen."
        )
    }

    // ==========================================
    // 6. SCROLL GESTURE (smart_ui_scroll)
    // ==========================================
    fun scrollScreen(direction: String): Map<String, Any?> {
        val displayMetrics = resources.displayMetrics
        val width = displayMetrics.widthPixels
        val height = displayMetrics.heightPixels
        val cx = (width / 2).toFloat()
        val cy = (height / 2).toFloat()

        val path = Path()
        when (direction.lowercase().trim()) {
            "down" -> {
                // Swipe up to scroll down
                path.moveTo(cx, cy + (height * 0.25f))
                path.lineTo(cx, cy - (height * 0.25f))
            }
            "up" -> {
                // Swipe down to scroll up
                path.moveTo(cx, cy - (height * 0.25f))
                path.lineTo(cx, cy + (height * 0.25f))
            }
            "left" -> {
                path.moveTo(cx + (width * 0.3f), cy)
                path.lineTo(cx - (width * 0.3f), cy)
            }
            "right" -> {
                path.moveTo(cx - (width * 0.3f), cy)
                path.lineTo(cx + (width * 0.3f), cy)
            }
            else -> {
                path.moveTo(cx, cy + (height * 0.25f))
                path.lineTo(cx, cy - (height * 0.25f))
            }
        }

        val stroke = GestureDescription.StrokeDescription(path, 0, 300)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val ok = dispatchGesture(gesture, null, null)
        return mapOf("success" to ok, "direction" to direction)
    }

    // ==========================================
    // 7. GLOBAL KEYS (press_key)
    // ==========================================
    fun pressKey(key: String): Map<String, Any?> {
        val action = when (key.lowercase().trim()) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents" -> GLOBAL_ACTION_RECENTS
            "notifications" -> GLOBAL_ACTION_NOTIFICATIONS
            "lock" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) GLOBAL_ACTION_LOCK_SCREEN else GLOBAL_ACTION_BACK
            "screenshot" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) GLOBAL_ACTION_TAKE_SCREENSHOT else GLOBAL_ACTION_BACK
            else -> return mapOf("success" to false, "error" to "Unsupported key: $key")
        }
        val ok = performGlobalAction(action)
        return mapOf("success" to ok, "key" to key)
    }

    // ==========================================
    // 8. UNLOCK PHONE (unlock_phone)
    // ==========================================
    fun unlockPhone(pin: String): Boolean {
        AgentStateStore.addLog("Unlocking phone...")
        val displayMetrics = resources.displayMetrics
        val cx = (displayMetrics.widthPixels / 2).toFloat()
        val bottomY = (displayMetrics.heightPixels * 0.85f)
        val topY = (displayMetrics.heightPixels * 0.2f)

        val path = Path().apply {
            moveTo(cx, bottomY)
            lineTo(cx, topY)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 200)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        dispatchGesture(gesture, null, null)

        if (pin.isNotBlank()) {
            // Type the pin after short delay
            Thread.sleep(600)
            for (digit in pin) {
                clickElement(digit.toString())
                Thread.sleep(200)
            }
        }
        return true
    }

    companion object {
        private const val TAG = "BrahmaAccessibility"
        var instance: BrahmaAccessibilityService? = null
        val isRunning: Boolean get() = instance != null
    }
}
