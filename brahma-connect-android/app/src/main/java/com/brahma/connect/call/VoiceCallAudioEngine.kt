package com.brahma.connect.call

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
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

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null

    private var recordingJob: Job? = null
    private val engineScope = CoroutineScope(Dispatchers.IO + Job())
    private var isRunning = false
    private var isMuted = false

    fun start() {
        if (isRunning) return
        isRunning = true
        setupAudioRouting()
        setupAudioTrack()
        setupAudioRecord()
        startRecordingLoop()
        Log.i(TAG, "VoiceCallAudioEngine started.")
    }

    fun stop() {
        if (!isRunning) return
        isRunning = false
        recordingJob?.cancel()
        recordingJob = null

        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping AudioRecord: ${e.message}")
        }
        audioRecord = null

        try {
            audioTrack?.stop()
            audioTrack?.flush()
            audioTrack?.release()
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping AudioTrack: ${e.message}")
        }
        audioTrack = null

        echoCanceler?.release()
        echoCanceler = null
        noiseSuppressor?.release()
        noiseSuppressor = null

        restoreAudioRouting()
        Log.i(TAG, "VoiceCallAudioEngine stopped.")
    }

    fun playAudioChunkBase64(base64Data: String) {
        if (!isRunning) return
        try {
            val pcmBytes = Base64.decode(base64Data, Base64.DEFAULT)
            audioTrack?.write(pcmBytes, 0, pcmBytes.size)
        } catch (e: Exception) {
            Log.w(TAG, "Error playing incoming audio chunk: ${e.message}")
        }
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

    private fun setupAudioRouting() {
        try {
            audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
            audioManager.isSpeakerphoneOn = true
        } catch (e: Exception) {
            Log.w(TAG, "Failed to set audio mode IN_COMMUNICATION: ${e.message}")
        }
    }

    private fun restoreAudioRouting() {
        try {
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

            val sessionId = record.audioSessionId
            if (AcousticEchoCanceler.isAvailable()) {
                echoCanceler = AcousticEchoCanceler.create(sessionId)?.apply {
                    enabled = true
                }
            }
            if (NoiseSuppressor.isAvailable()) {
                noiseSuppressor = NoiseSuppressor.create(sessionId)?.apply {
                    enabled = true
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
                }
            }
        }
    }
}
