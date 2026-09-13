package com.brahma.connect.call

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.Build
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
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private var speechRecognizer: SpeechRecognizer? = null
    private var isRunning = false
    private var isPausedForPlayback = false
    private var isListeningNow = false
    private var isMutedByEngine = false
    private var useOnDevice = true
    private var retryCount = 0

    fun start() {
        mainHandler.post {
            if (isRunning) return@post
            isRunning = true
            isPausedForPlayback = false
            retryCount = 0
            useOnDevice = true
            initRecognizer()
            startListeningInternal()
            Log.i(TAG, "VoiceCallSpeechEngine started (Fast Turn Mode, Mic Dedicated).")
        }
    }

    fun stop() {
        mainHandler.post {
            if (!isRunning) return@post
            isRunning = false
            isPausedForPlayback = false
            isListeningNow = false
            mainHandler.removeCallbacksAndMessages(null)
            muteBeepStreams()
            try {
                speechRecognizer?.stopListening()
                speechRecognizer?.cancel()
                speechRecognizer?.destroy()
            } catch (e: Exception) {
                Log.w(TAG, "Error destroying SpeechRecognizer: ${e.message}")
            }
            speechRecognizer = null
            mainHandler.postDelayed({ unmuteBeepStreams() }, 200)
            Log.i(TAG, "VoiceCallSpeechEngine stopped.")
        }
    }

    fun pauseListening() {
        mainHandler.post {
            if (!isRunning) return@post
            isPausedForPlayback = true
            isListeningNow = false
            mainHandler.removeCallbacksAndMessages(null)
            muteBeepStreams()
            try {
                speechRecognizer?.cancel()
            } catch (e: Exception) {
                Log.w(TAG, "Error pausing SpeechRecognizer: ${e.message}")
            }
            mainHandler.postDelayed({ unmuteBeepStreams() }, 200)
            Log.d(TAG, "SpeechRecognizer paused (ARYA is speaking).")
        }
    }

    fun resumeListening() {
        mainHandler.post {
            if (!isRunning) return@post
            isPausedForPlayback = false
            mainHandler.removeCallbacksAndMessages(null)
            // Brief delay to ensure speaker echo has fully cleared the room
            mainHandler.postDelayed({
                if (isRunning && !isPausedForPlayback) {
                    startListeningInternal()
                    Log.d(TAG, "SpeechRecognizer resumed (Listening for user).")
                }
            }, 100)
        }
    }

    private fun muteBeepStreams() {
        if (audioManager == null || isMutedByEngine) return
        isMutedByEngine = true
        val streams = intArrayOf(
            AudioManager.STREAM_NOTIFICATION,
            AudioManager.STREAM_SYSTEM,
            AudioManager.STREAM_MUSIC
        )
        for (s in streams) {
            try {
                audioManager.adjustStreamVolume(s, AudioManager.ADJUST_MUTE, 0)
            } catch (e: Exception) {
                // Ignore if restricted by system policy
            }
        }
    }

    private fun unmuteBeepStreams() {
        if (audioManager == null || !isMutedByEngine) return
        isMutedByEngine = false
        val streams = intArrayOf(
            AudioManager.STREAM_NOTIFICATION,
            AudioManager.STREAM_SYSTEM,
            AudioManager.STREAM_MUSIC
        )
        for (s in streams) {
            try {
                audioManager.adjustStreamVolume(s, AudioManager.ADJUST_UNMUTE, 0)
            } catch (e: Exception) {
                // Ignore if restricted by system policy
            }
        }
    }

    private fun initRecognizer() {
        try {
            speechRecognizer?.destroy()
        } catch (e: Exception) {
            // Ignore
        }
        speechRecognizer = try {
            if (useOnDevice && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
                SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
            ) {
                Log.d(TAG, "Using on-device SpeechRecognizer (Android 12+)")
                SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
            } else {
                Log.d(TAG, "Using standard SpeechRecognizer")
                SpeechRecognizer.createSpeechRecognizer(context)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Fallback to standard createSpeechRecognizer: ${e.message}")
            SpeechRecognizer.createSpeechRecognizer(context)
        }.apply {
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
                if (useOnDevice) {
                    putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                }
                // Fast conversational turn detection (450ms silence)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 250L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 450L)
                putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 450L)
            }

            muteBeepStreams()
            speechRecognizer?.startListening(intent)
            isListeningNow = true
            mainHandler.postDelayed({ unmuteBeepStreams() }, 350)
        } catch (e: Exception) {
            unmuteBeepStreams()
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
            mainHandler.postDelayed({ unmuteBeepStreams() }, 100)
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
            muteBeepStreams()
            mainHandler.postDelayed({ unmuteBeepStreams() }, 350)
        }

        override fun onError(error: Int) {
            isListeningNow = false
            unmuteBeepStreams()
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

            if (error == SpeechRecognizer.ERROR_CLIENT ||
                error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY ||
                error == SpeechRecognizer.ERROR_SERVER ||
                error == SpeechRecognizer.ERROR_AUDIO
            ) {
                if (useOnDevice) {
                    Log.i(TAG, "Falling back from on-device to standard SpeechRecognizer")
                    useOnDevice = false
                }
                initRecognizer()
                scheduleRestart(250)
            } else {
                // For NO_MATCH / SPEECH_TIMEOUT, silence is normal when waiting for user to speak
                scheduleRestart(150)
            }
        }

        override fun onResults(results: Bundle?) {
            isListeningNow = false
            unmuteBeepStreams()
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
