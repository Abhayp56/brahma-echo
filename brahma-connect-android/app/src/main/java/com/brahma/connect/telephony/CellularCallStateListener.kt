package com.brahma.connect.telephony

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.provider.ContactsContract
import android.telephony.PhoneStateListener
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

/**
 * Listens for incoming cellular (GSM) phone calls to support call screening and caller announcements.
 */
class CellularCallStateListener(
    private val context: Context,
    private val onIncomingCall: (callerName: String, phoneNumber: String) -> Unit,
    private val onCallEnded: () -> Unit,
) {
    companion object {
        private const val TAG = "CellularCallListener"
    }

    private val telephonyManager = context.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager
    private val executor = Executors.newSingleThreadExecutor()
    private var legacyListener: PhoneStateListener? = null
    private var modernCallback: Any? = null // TelephonyCallback on API 31+
    private var isListening = false

    fun startListening() {
        if (isListening || telephonyManager == null) return

        val hasPhoneState = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.READ_PHONE_STATE
        ) == PackageManager.PERMISSION_GRANTED

        if (!hasPhoneState) {
            Log.w(TAG, "READ_PHONE_STATE permission not granted. Cannot screen cellular calls.")
            return
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val callback = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
                    override fun onCallStateChanged(state: Int) {
                        handleCallState(state, null)
                    }
                }
                telephonyManager.registerTelephonyCallback(executor, callback)
                modernCallback = callback
            } else {
                @Suppress("DEPRECATION")
                val listener = object : PhoneStateListener() {
                    @Deprecated("Deprecated in Java")
                    override fun onCallStateChanged(state: Int, phoneNumber: String?) {
                        handleCallState(state, phoneNumber)
                    }
                }
                @Suppress("DEPRECATION")
                telephonyManager.listen(listener, PhoneStateListener.LISTEN_CALL_STATE)
                legacyListener = listener
            }
            isListening = true
            Log.i(TAG, "Cellular call state listener started.")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start cellular call state listener: ${e.message}")
        }
    }

    fun stopListening() {
        if (!isListening || telephonyManager == null) return
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (modernCallback as? TelephonyCallback)?.let {
                    telephonyManager.unregisterTelephonyCallback(it)
                }
                modernCallback = null
            } else {
                @Suppress("DEPRECATION")
                legacyListener?.let {
                    telephonyManager.listen(it, PhoneStateListener.LISTEN_NONE)
                }
                legacyListener = null
            }
            isListening = false
            Log.i(TAG, "Cellular call state listener stopped.")
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping cellular call state listener: ${e.message}")
        }
    }

    private fun handleCallState(state: Int, phoneNumber: String?) {
        when (state) {
            TelephonyManager.CALL_STATE_RINGING -> {
                val number = phoneNumber ?: "Unknown"
                val name = resolveContactName(number) ?: "Unknown Caller"
                Log.i(TAG, "Incoming cellular call: $name ($number)")
                onIncomingCall(name, number)
            }
            TelephonyManager.CALL_STATE_IDLE -> {
                onCallEnded()
            }
            TelephonyManager.CALL_STATE_OFFHOOK -> {
                Log.d(TAG, "Call off-hook (answered or dialing)")
            }
        }
    }

    private fun resolveContactName(phoneNumber: String): String? {
        if (phoneNumber.isBlank() || phoneNumber == "Unknown") return null
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            return null
        }
        return try {
            val uri = Uri.withAppendedPath(
                ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
                Uri.encode(phoneNumber)
            )
            val projection = arrayOf(ContactsContract.PhoneLookup.DISPLAY_NAME)
            context.contentResolver.query(uri, projection, null, null, null)?.use { cursor: Cursor ->
                if (cursor.moveToFirst()) {
                    val nameIdx = cursor.getColumnIndex(ContactsContract.PhoneLookup.DISPLAY_NAME)
                    if (nameIdx != -1) cursor.getString(nameIdx) else null
                } else null
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error resolving contact for $phoneNumber: ${e.message}")
            null
        }
    }
}
