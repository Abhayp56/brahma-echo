package com.brahma.connect.call

import android.content.Context
import android.content.Intent
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.core.CallOfferPayload
import com.brahma.connect.core.CallState
import com.brahma.connect.ui.CallActivity

class CallManager private constructor(private val context: Context) {
    companion object {
        private const val TAG = "CallManager"

        @Volatile
        private var instance: CallManager? = null

        fun getInstance(context: Context): CallManager {
            return instance ?: synchronized(this) {
                instance ?: CallManager(context.applicationContext).also { instance = it }
            }
        }
    }

    private var currentOffer: CallOfferPayload? = null
    private var ringtone: Ringtone? = null
    private var audioEngine: VoiceCallAudioEngine? = null

    // Outbound callback to WebSocket client
    var onSendCallAnswer: ((callId: String) -> Unit)? = null
    var onSendCallReject: ((callId: String) -> Unit)? = null
    var onSendCallEnd: ((callId: String) -> Unit)? = null
    var onSendCallAudio: ((callId: String, base64Chunk: String) -> Unit)? = null

    init {
        audioEngine = VoiceCallAudioEngine(context) { chunkBase64 ->
            currentOffer?.let { offer ->
                onSendCallAudio?.invoke(offer.callId, chunkBase64)
            }
        }
    }

    fun handleIncomingCallOffer(offer: CallOfferPayload) {
        if (AgentStateStore.callState.value == CallState.ACTIVE) {
            Log.w(TAG, "Already in an active call. Rejecting call: ${offer.callId}")
            onSendCallReject?.invoke(offer.callId)
            return
        }

        currentOffer = offer
        AgentStateStore.setCallState(CallState.RINGING, offer)
        startRinging()

        // Launch CallActivity with full-screen intent
        val intent = Intent(context, CallActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(CallActivity.EXTRA_CALL_ID, offer.callId)
            putExtra(CallActivity.EXTRA_CALLER_NAME, offer.callerName)
            putExtra(CallActivity.EXTRA_REASON, offer.reason)
        }
        context.startActivity(intent)
        Log.i(TAG, "Incoming call offer received from ${offer.callerName}: ${offer.reason}")
    }

    fun acceptCall() {
        val offer = currentOffer ?: return
        stopRinging()
        AgentStateStore.setCallState(CallState.ACTIVE, offer)
        audioEngine?.start()
        onSendCallAnswer?.invoke(offer.callId)
        Log.i(TAG, "Call accepted: ${offer.callId}")
    }

    fun rejectCall() {
        val offer = currentOffer ?: return
        stopRinging()
        audioEngine?.stop()
        AgentStateStore.setCallState(CallState.ENDED, offer)
        onSendCallReject?.invoke(offer.callId)
        currentOffer = null
        AgentStateStore.setCallState(CallState.IDLE)
        Log.i(TAG, "Call rejected: ${offer.callId}")
    }

    fun endCall() {
        val offer = currentOffer
        stopRinging()
        audioEngine?.stop()
        if (offer != null) {
            onSendCallEnd?.invoke(offer.callId)
        }
        currentOffer = null
        AgentStateStore.setCallState(CallState.ENDED)
        AgentStateStore.setCallState(CallState.IDLE)
        Log.i(TAG, "Call ended.")
    }

    fun onCallEndedByRemote(callId: String) {
        if (currentOffer?.callId == callId || currentOffer == null) {
            stopRinging()
            audioEngine?.stop()
            currentOffer = null
            AgentStateStore.setCallState(CallState.ENDED)
            AgentStateStore.setCallState(CallState.IDLE)
            Log.i(TAG, "Call terminated by remote: $callId")
        }
    }

    fun handleIncomingAudioChunk(chunkBase64: String) {
        if (AgentStateStore.callState.value == CallState.ACTIVE) {
            audioEngine?.playAudioChunkBase64(chunkBase64)
        }
    }

    fun setMuted(muted: Boolean) {
        audioEngine?.setMuted(muted)
    }

    fun setSpeakerphoneOn(speakerOn: Boolean) {
        audioEngine?.setSpeakerphoneOn(speakerOn)
    }

    private fun startRinging() {
        try {
            val alertUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            ringtone = RingtoneManager.getRingtone(context, alertUri)?.apply {
                play()
            }

            val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vm?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(
                    VibrationEffect.createWaveform(
                        longArrayOf(0, 1000, 1000),
                        0 // repeat
                    )
                )
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(longArrayOf(0, 1000, 1000), 0)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to start ringtone/vibration: ${e.message}")
        }
    }

    private fun stopRinging() {
        try {
            ringtone?.stop()
            ringtone = null

            val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vm?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
            }
            vibrator?.cancel()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to stop ringtone/vibration: ${e.message}")
        }
    }
}
