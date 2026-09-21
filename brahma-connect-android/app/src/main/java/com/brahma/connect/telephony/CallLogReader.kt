package com.brahma.connect.telephony

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.util.Log
import androidx.core.content.ContextCompat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Reads call logs (missed calls, incoming calls, dialed calls) from Android CallLog provider.
 * Requires Manifest.permission.READ_CALL_LOG.
 */
class CallLogReader(private val context: Context) {

    companion object {
        private const val TAG = "CallLogReader"
    }

    fun hasPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.READ_CALL_LOG
        ) == PackageManager.PERMISSION_GRANTED
    }

    fun getMissedCalls(limit: Int = 10): List<Map<String, Any?>> {
        return getCalls(
            selection = "${CallLog.Calls.TYPE} = ?",
            selectionArgs = arrayOf(CallLog.Calls.MISSED_TYPE.toString()),
            limit = limit
        )
    }

    fun getRecentCalls(limit: Int = 15, typeFilter: String? = null): List<Map<String, Any?>> {
        val (selection, selectionArgs) = when (typeFilter?.lowercase()?.trim()) {
            "missed" -> "${CallLog.Calls.TYPE} = ?" to arrayOf(CallLog.Calls.MISSED_TYPE.toString())
            "incoming" -> "${CallLog.Calls.TYPE} = ?" to arrayOf(CallLog.Calls.INCOMING_TYPE.toString())
            "outgoing", "dialed" -> "${CallLog.Calls.TYPE} = ?" to arrayOf(CallLog.Calls.OUTGOING_TYPE.toString())
            "rejected" -> "${CallLog.Calls.TYPE} = ?" to arrayOf(CallLog.Calls.REJECTED_TYPE.toString())
            else -> null to null
        }
        return getCalls(selection, selectionArgs, limit)
    }

    private fun getCalls(selection: String?, selectionArgs: Array<String>?, limit: Int): List<Map<String, Any?>> {
        if (!hasPermission()) {
            Log.w(TAG, "READ_CALL_LOG permission not granted.")
            return emptyList()
        }

        val results = mutableListOf<Map<String, Any?>>()
        val projection = arrayOf(
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.NUMBER,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION
        )
        val sortOrder = "${CallLog.Calls.DATE} DESC LIMIT ${limit.coerceIn(1, 50)}"
        val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())

        try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                projection,
                selection,
                selectionArgs,
                sortOrder
            )?.use { cursor ->
                val nameIdx = cursor.getColumnIndex(CallLog.Calls.CACHED_NAME)
                val numIdx = cursor.getColumnIndex(CallLog.Calls.NUMBER)
                val typeIdx = cursor.getColumnIndex(CallLog.Calls.TYPE)
                val dateIdx = cursor.getColumnIndex(CallLog.Calls.DATE)
                val durIdx = cursor.getColumnIndex(CallLog.Calls.DURATION)

                while (cursor.moveToNext()) {
                    val name = if (nameIdx != -1) cursor.getString(nameIdx) else null
                    val number = if (numIdx != -1) cursor.getString(numIdx) ?: "Unknown" else "Unknown"
                    val typeCode = if (typeIdx != -1) cursor.getInt(typeIdx) else -1
                    val dateMillis = if (dateIdx != -1) cursor.getLong(dateIdx) else 0L
                    val durationSec = if (durIdx != -1) cursor.getLong(durIdx) else 0L

                    val typeStr = when (typeCode) {
                        CallLog.Calls.INCOMING_TYPE -> "incoming"
                        CallLog.Calls.OUTGOING_TYPE -> "outgoing"
                        CallLog.Calls.MISSED_TYPE -> "missed"
                        CallLog.Calls.VOICEMAIL_TYPE -> "voicemail"
                        CallLog.Calls.REJECTED_TYPE -> "rejected"
                        CallLog.Calls.BLOCKED_TYPE -> "blocked"
                        else -> "other"
                    }

                    results.add(
                        mapOf(
                            "name" to (name ?: number),
                            "number" to number,
                            "type" to typeStr,
                            "date" to dateFormat.format(Date(dateMillis)),
                            "timestamp" to dateMillis,
                            "duration_seconds" to durationSec,
                            "is_missed" to (typeCode == CallLog.Calls.MISSED_TYPE)
                        )
                    )
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error querying call log: ${e.message}", e)
        }

        return results
    }
}
