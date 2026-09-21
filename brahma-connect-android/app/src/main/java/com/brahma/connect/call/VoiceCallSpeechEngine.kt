package com.brahma.connect.call

import android.content.Context
import android.util.Log

/**
 * Decommissioned in favor of native full-duplex VoIP AudioEngine (VoiceCallAudioEngine).
 * Kept as a safe no-op stub for backward compatibility without Google SpeechRecognizer
 * binder calls, earcon chimes, or main thread blocking.
 */
class VoiceCallSpeechEngine(
    private val context: Context,
    private val onSpeechRecognized: (text: String) -> Unit,
    private val onPartialSpeech: ((partialText: String) -> Unit)? = null,
) {
    companion object {
        private const val TAG = "VoiceCallSpeechEngine"
    }

    fun start() {
        Log.i(TAG, "VoiceCallSpeechEngine decommissioned. Native VoIP mic streaming is active in VoiceCallAudioEngine.")
    }

    fun stop() {
        Log.i(TAG, "VoiceCallSpeechEngine stop called (no-op).")
    }

    fun pauseListening() {}
    fun resumeListening() {}
}

