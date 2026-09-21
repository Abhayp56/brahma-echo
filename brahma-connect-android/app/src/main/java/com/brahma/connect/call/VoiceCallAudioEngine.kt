package com.brahma.connect.call

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class VoiceCallAudioEngine(
    private val context: Context,
    private val onAudioChunkRecorded: (base64Chunk: String) -> Unit,
) {
    companion object {
        private const val TAG = "VoiceCallAudioEngine"
        const val RECORD_SAMPLE_RATE = 16000
        const val PLAYBACK_SAMPLE_RATE = 24000
    }

    var onPlaybackStarted: (() -> Unit)? = null
    var onPlaybackFinished: (() -> Unit)? = null

    private val mainHandler = Handler(Looper.getMainLooper())
    private val finishPlaybackRunnable = Runnable {
        onPlaybackFinished?.invoke()
    }

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null

    private val audioTrackLock = Any()
    private var recordingJob: Job? = null
    private var playbackJob: Job? = null
    private val playbackChannel = kotlinx.coroutines.channels.Channel<ByteArray>(kotlinx.coroutines.channels.Channel.UNLIMITED)
    private val engineScope = CoroutineScope(Dispatchers.IO + Job())
    private var isRunning = false
    private var isMuted = false

    fun start(enableMicRecording: Boolean = true) {
        if (isRunning) return
        isRunning = true
        setupAudioRouting()
        setupAudioTrack()
        startPlaybackLoop()
        if (enableMicRecording) {
            setupAudioRecord()
            startRecordingLoop()
            Log.i(TAG, "VoiceCallAudioEngine started with raw mic recording enabled (Full-Duplex VoIP mode).")
        } else {
            Log.i(TAG, "VoiceCallAudioEngine started (Playback track & routing active).")
        }
    }

    fun stop() {
        if (!isRunning) return
        isRunning = false
        recordingJob?.cancel()
        recordingJob = null

        playbackJob?.cancel()
        playbackJob = null
        while (playbackChannel.tryReceive().isSuccess) { /* Drain buffer */ }

        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping AudioRecord: ${e.message}")
        }
        audioRecord = null

        synchronized(audioTrackLock) {
            try {
                audioTrack?.stop()
                audioTrack?.flush()
                audioTrack?.release()
            } catch (e: Exception) {
                Log.w(TAG, "Error stopping AudioTrack: ${e.message}")
            }
            audioTrack = null
        }

        try {
            echoCanceler?.release()
        } catch (_: Exception) {}
        echoCanceler = null

        try {
            noiseSuppressor?.release()
        } catch (_: Exception) {}
        noiseSuppressor = null

        restoreAudioRouting()
        mainHandler.removeCallbacksAndMessages(null)
        Log.i(TAG, "VoiceCallAudioEngine stopped.")
    }

    fun playAudioChunkBase64(base64Data: String) {
        if (!isRunning) return
        try {
            val pcmBytes = Base64.decode(base64Data, Base64.DEFAULT)
            // Non-blocking enqueue: returns instantly without blocking the OkHttp WebSocket reader thread!
            playbackChannel.trySend(pcmBytes)

            mainHandler.removeCallbacks(finishPlaybackRunnable)
            onPlaybackStarted?.invoke()
            // 750ms buffer prevents network jitter between audio chunks from false-triggering end of turn
            mainHandler.postDelayed(finishPlaybackRunnable, 750L)
        } catch (e: Exception) {
            Log.w(TAG, "Error enqueueing incoming audio chunk: ${e.message}")
        }
    }

    private fun startPlaybackLoop() {
        playbackJob = engineScope.launch {
            for (chunk in playbackChannel) {
                if (!isActive || !isRunning) break
                synchronized(audioTrackLock) {
                    val track = audioTrack
                    if (track != null && isRunning) {
                        try {
                            track.write(chunk, 0, chunk.size)
                        } catch (e: Exception) {
                            Log.w(TAG, "AudioTrack write error: ${e.message}")
                        }
                    }
                }
            }
        }
    }

    fun notifyTurnComplete() {
        mainHandler.removeCallbacks(finishPlaybackRunnable)
        mainHandler.postDelayed(finishPlaybackRunnable, 100L)
    }

    fun setMuted(muted: Boolean) {
        isMuted = muted
    }

    fun setSpeakerphoneOn(speakerOn: Boolean) {
        try {
            audioManager.isSpeakerphoneOn = speakerOn
        } catch (e: Exception) {
            Log.w(TAG, "Failed to toggle speakerphone: ${e.message}")
        }
    }

    private var audioFocusRequest: AudioFocusRequest? = null

    private fun setupAudioRouting() {
        try {
            audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
            audioManager.isSpeakerphoneOn = true

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
                    .setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build()
                    )
                    .setAcceptsDelayedFocusGain(false)
                    .setOnAudioFocusChangeListener { /* Hold voice call focus */ }
                    .build()
                audioFocusRequest = focus
                audioManager.requestAudioFocus(focus)
            } else {
                @Suppress("DEPRECATION")
                audioManager.requestAudioFocus(null, AudioManager.STREAM_VOICE_CALL, AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to set audio mode IN_COMMUNICATION or request audio focus: ${e.message}")
        }
    }

    private fun restoreAudioRouting() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                audioFocusRequest?.let { audioManager.abandonAudioFocusRequest(it) }
                audioFocusRequest = null
            } else {
                @Suppress("DEPRECATION")
                audioManager.abandonAudioFocus(null)
            }
            audioManager.mode = AudioManager.MODE_NORMAL
            audioManager.isSpeakerphoneOn = false
        } catch (e: Exception) {
            Log.w(TAG, "Failed to restore audio mode NORMAL: ${e.message}")
        }
    }

    private fun setupAudioTrack() {
        val minBufferSize = AudioTrack.getMinBufferSize(
            PLAYBACK_SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        val bufferSize = maxOf(minBufferSize, 4096)

        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(PLAYBACK_SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(bufferSize)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()

        audioTrack?.play()
    }

    private fun setupAudioRecord() {
        val minBufferSize = AudioRecord.getMinBufferSize(
            RECORD_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        val bufferSize = maxOf(minBufferSize, 2048)

        try {
            var record: AudioRecord? = null
            try {
                record = AudioRecord(
                    MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                    RECORD_SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize
                )
            } catch (e: Exception) {
                Log.w(TAG, "VOICE_COMMUNICATION failed: ${e.message}")
            }

            if (record == null || record.state != AudioRecord.STATE_INITIALIZED) {
                record?.release()
                Log.i(TAG, "Falling back to AudioSource.MIC for AudioRecord")
                record = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    RECORD_SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize
                )
            }

            if (record.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord failed to initialize in both VOICE_COMMUNICATION and MIC modes!")
                record.release()
                return
            }

            val sessionId = record.audioSessionId
            if (AcousticEchoCanceler.isAvailable()) {
                try {
                    echoCanceler = AcousticEchoCanceler.create(sessionId)?.apply {
                        enabled = true
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Could not create AcousticEchoCanceler: ${e.message}")
                }
            }
            if (NoiseSuppressor.isAvailable()) {
                try {
                    noiseSuppressor = NoiseSuppressor.create(sessionId)?.apply {
                        enabled = true
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Could not create NoiseSuppressor: ${e.message}")
                }
            }

            record.startRecording()
            audioRecord = record
        } catch (e: SecurityException) {
            Log.e(TAG, "RECORD_AUDIO permission missing: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start AudioRecord: ${e.message}")
        }
    }

    private fun startRecordingLoop() {
        recordingJob = engineScope.launch {
            val buffer = ByteArray(1024)
            while (isActive && isRunning) {
                val record = audioRecord ?: break
                val read = record.read(buffer, 0, buffer.size)
                if (read > 0 && !isMuted) {
                    val chunk = if (read == buffer.size) buffer else buffer.copyOf(read)
                    val base64 = Base64.encodeToString(chunk, Base64.NO_WRAP)
                    onAudioChunkRecorded(base64)
                } else if (read <= 0) {
                    if (read < 0) {
                        Log.w(TAG, "AudioRecord read error code: $read")
                    }
                    delay(20)
                }
            }
        }
    }
}
