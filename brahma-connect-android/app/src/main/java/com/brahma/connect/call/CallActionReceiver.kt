package com.brahma.connect.call

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.brahma.connect.ui.CallActivity

class CallActionReceiver : BroadcastReceiver() {
    companion object {
        const val ACTION_DECLINE_CALL = "com.brahma.connect.action.DECLINE_CALL"
        const val ACTION_ANSWER_CALL = "com.brahma.connect.action.ANSWER_CALL"
        const val EXTRA_CALL_ID = "extra_call_id"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        val callManager = CallManager.getInstance(context)

        when (action) {
            ACTION_DECLINE_CALL -> {
                android.util.Log.i("CallActionReceiver", "Decline action received from notification.")
                callManager.rejectCall()
            }
            ACTION_ANSWER_CALL -> {
                android.util.Log.i("CallActionReceiver", "Answer action received from notification.")
                val callId = intent.getStringExtra(EXTRA_CALL_ID) ?: ""
                val callerName = intent.getStringExtra(CallActivity.EXTRA_CALLER_NAME) ?: "JARVIS"
                val reason = intent.getStringExtra(CallActivity.EXTRA_REASON) ?: "Voice Call"

                val activityIntent = Intent(context, CallActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                    putExtra(CallActivity.EXTRA_CALL_ID, callId)
                    putExtra(CallActivity.EXTRA_CALLER_NAME, callerName)
                    putExtra(CallActivity.EXTRA_REASON, reason)
                    putExtra(CallActivity.EXTRA_AUTO_ANSWER, true)
                }
                context.startActivity(activityIntent)
            }
        }
    }
}
