package com.brahma.connect.call

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log

class VoiceCallSpeechEngine(
    private val context: Context,
    private val onSpeechRecognized: (text: String) -> Unit,
    private val onPartialSpeech: ((partialText: String) -> Unit)? = null,
) {
    companion object {
        private const val TAG = "VoiceCallSpeechEngine"
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private var speechRecognizer: SpeechRecognizer? = null
    private var isRunning = false
    private var isPausedForPlayback = false
    private var isListeningNow = false
    private var retryCount = 0

    fun start() {
        mainHandler.post {
            if (isRunning) return@post
            isRunning = true
            isPausedForPlayback = false
            retryCount = 0
            initRecognizer()
            startListeningInternal()
            Log.i(TAG, "VoiceCallSpeechEngine started (On-Device Fast Turn Mode).")
        }
    }

    fun stop() {
        mainHandler.post {
            if (!isRunning) return@post
            isRunning = false
            isPausedForPlayback = false
            isListeningNow = false
            mainHandler.removeCallbacksAndMessages(null)
            try {
                speechRecognizer?.stopListening()
                speechRecognizer?.cancel()
                speechRecognizer?.destroy()
            } catch (e: Exception) {
                Log.w(TAG, "Error destroying SpeechRecognizer: ${e.message}")
            }
            speechRecognizer = null
            Log.i(TAG, "VoiceCallSpeechEngine stopped.")
        }
    }

    fun pauseListening() {
        mainHandler.post {
            if (!isRunning) return@post
            isPausedForPlayback = true
            isListeningNow = false
            mainHandler.removeCallbacksAndMessages(null)
            try {
                speechRecognizer?.cancel()
            } catch (e: Exception) {
                Log.w(TAG, "Error pausing SpeechRecognizer: ${e.message}")
            }
            Log.d(TAG, "SpeechRecognizer paused (ARYA is speaking).")
        }
    }

    fun resumeListening() {
        mainHandler.post {
            if (!isRunning) return@post
            isPausedForPlayback = false
            mainHandler.removeCallbacksAndMessages(null)
            // Tiny delay to ensure speaker echo has fully cleared the room
            mainHandler.postDelayed({
                if (isRunning && !isPausedForPlayback) {
                    startListeningInternal()
                    Log.d(TAG, "SpeechRecognizer resumed (Listening for user).")
                }
            }, 100)
        }
    }

    private fun initRecognizer() {
        try {
            speechRecognizer?.destroy()
        } catch (e: Exception) {
            // Ignore
        }
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
            setRecognitionListener(CallRecognitionListener())
        }
    }

    private fun startListeningInternal() {
        if (!isRunning || isPausedForPlayback) return
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            Log.w(TAG, "Speech recognition not available on device.")
            return
        }

        try {
            if (speechRecognizer == null) {
                initRecognizer()
            }

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
                // Optimize silence detection for conversational responsiveness
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 300L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 450L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 450L)
            }

            speechRecognizer?.startListening(intent)
            isListeningNow = true
        } catch (e: Exception) {
            Log.w(TAG, "Failed to startListening: ${e.message}")
            scheduleRestart(500)
        }
    }

    private fun scheduleRestart(delayMs: Long) {
        if (!isRunning || isPausedForPlayback) return
        mainHandler.removeCallbacksAndMessages(null)
        mainHandler.postDelayed({
            if (isRunning && !isPausedForPlayback) {
                startListeningInternal()
            }
        }, delayMs)
    }

    private inner class CallRecognitionListener : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            isListeningNow = true
            retryCount = 0
        }

        override fun onBeginningOfSpeech() {
            Log.d(TAG, "User began speaking.")
        }

        override fun onRmsChanged(rmsdB: Float) {
            // Optional volume callback
        }

        override fun onBufferReceived(buffer: ByteArray?) {}

        override fun onEndOfSpeech() {
            Log.d(TAG, "User finished speaking. Processing on-device transcript...")
            isListeningNow = false
        }

        override fun onError(error: Int) {
            isListeningNow = false
            val errorMsg = when (error) {
                SpeechRecognizer.ERROR_NO_MATCH -> "No match (silence)"
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Speech timeout (silence)"
                SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                SpeechRecognizer.ERROR_NETWORK -> "Network error"
                SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout"
                SpeechRecognizer.ERROR_CLIENT -> "Client error"
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Permission error"
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Recognizer busy"
                SpeechRecognizer.ERROR_SERVER -> "Server error"
                else -> "Error code: $error"
            }
            Log.d(TAG, "SpeechRecognizer $errorMsg")

            if (!isRunning || isPausedForPlayback) return

            // If error is CLIENT or RECOGNIZER_BUSY, re-init the recognizer
            if (error == SpeechRecognizer.ERROR_CLIENT || error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY) {
                initRecognizer()
                scheduleRestart(250)
            } else {
                // For NO_MATCH / SPEECH_TIMEOUT, silence is normal when waiting for user to speak
                scheduleRestart(100)
            }
        }

        override fun onResults(results: Bundle?) {
            isListeningNow = false
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val recognizedText = matches?.firstOrNull()?.trim()

            if (!recognizedText.isNullOrEmpty() && !isPausedForPlayback) {
                Log.i(TAG, "🗣️ Transcribed user speech: '$recognizedText'")
                onSpeechRecognized(recognizedText)
            }

            // Immediately restart listening so the call is hands-free
            if (isRunning && !isPausedForPlayback) {
                scheduleRestart(100)
            }
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val partial = matches?.firstOrNull()?.trim()
            if (!partial.isNullOrEmpty()) {
                onPartialSpeech?.invoke(partial)
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }
}
