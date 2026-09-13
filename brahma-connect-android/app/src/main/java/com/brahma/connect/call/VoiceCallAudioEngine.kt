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
    private var playbackJob: Job? = null
    private val playbackQueue = java.util.concurrent.LinkedBlockingQueue<ByteArray>(40)
    private val engineScope = CoroutineScope(Dispatchers.IO + Job())
    private var isRunning = false
    private var isMuted = false

    @Volatile private var isAryaSpeaking = false
    @Volatile private var lastAryaSpeechTimestamp = 0L

    fun start() {
        if (isRunning) return
        isRunning = true
        playbackQueue.clear()
        isAryaSpeaking = false
        lastAryaSpeechTimestamp = 0L
        setupAudioRouting()
        setupAudioTrack()
        setupAudioRecord()
        startPlaybackLoop()
        startRecordingLoop()
        Log.i(TAG, "VoiceCallAudioEngine started (Low-Latency Realtime Mode).")
    }

    fun stop() {
        if (!isRunning) return
        isRunning = false
        recordingJob?.cancel()
        recordingJob = null
        playbackJob?.cancel()
        playbackJob = null
        playbackQueue.clear()

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

    fun clearPlayback() {
        playbackQueue.clear()
        isAryaSpeaking = false
        try {
            audioTrack?.pause()
            audioTrack?.flush()
            audioTrack?.play()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to flush AudioTrack: ${e.message}")
        }
    }

    fun playAudioChunkBase64(base64Data: String) {
        if (!isRunning) return
        try {
            val pcmBytes = Base64.decode(base64Data, Base64.DEFAULT)
            // Prevent playback queue buildup; drop oldest chunks if network bursts
            while (playbackQueue.size > 12) {
                playbackQueue.poll()
            }
            playbackQueue.offer(pcmBytes)
        } catch (e: Exception) {
            Log.w(TAG, "Error queuing audio chunk: ${e.message}")
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

    private fun startPlaybackLoop() {
        playbackJob = engineScope.launch {
            while (isActive && isRunning) {
                val track = audioTrack ?: break
                val chunk = playbackQueue.poll(40, java.util.concurrent.TimeUnit.MILLISECONDS)
                if (chunk != null && chunk.isNotEmpty()) {
                    isAryaSpeaking = true
                    lastAryaSpeechTimestamp = System.currentTimeMillis()
                    track.write(chunk, 0, chunk.size)
                } else {
                    if (isAryaSpeaking && System.currentTimeMillis() - lastAryaSpeechTimestamp > 350L) {
                        isAryaSpeaking = false
                    }
                }
            }
        }
    }

    private fun startRecordingLoop() {
        recordingJob = engineScope.launch {
            // 1600 bytes = 800 samples = 50ms at 16kHz (optimal VoIP packetization interval)
            val buffer = ByteArray(1600)
            while (isActive && isRunning) {
                val record = audioRecord ?: break
                val read = record.read(buffer, 0, buffer.size)
                if (read > 0 && !isMuted) {
                    val now = System.currentTimeMillis()
                    val speaking = isAryaSpeaking || (now - lastAryaSpeechTimestamp < 400L)

                    // Calculate RMS of recorded chunk to detect user voice vs speakerphone echo
                    var sum = 0.0
                    var i = 0
                    val numSamples = read / 2
                    while (i < read - 1) {
                        val sample = (buffer[i].toInt() and 0xFF) or (buffer[i + 1].toInt() shl 8)
                        val shortSample = sample.toShort()
                        sum += shortSample.toDouble() * shortSample.toDouble()
                        i += 2
                    }
                    val rms = if (numSamples > 0) Math.sqrt(sum / numSamples) else 0.0

                    // Smart Echo Gate:
                    // When ARYA is speaking through the loudspeaker:
                    // - Hardware AEC reduces speaker residue into mic to < 2200 RMS.
                    // - If RMS < 2600, suppress chunk so ARYA does NOT hear her own voice and interrupt herself!
                    // - If RMS >= 2600, user is speaking over ARYA (barge-in):
                    //   -> immediately cut off loudspeaker playback and send chunk to Gemini Live!
                    // When ARYA is silent:
                    // - Filter low background noise (RMS >= 60) to keep Gemini Live VAD crisp and responsive.
                    val shouldSend = if (speaking) {
                        if (rms >= 2600.0) {
                            clearPlayback()
                            true
                        } else {
                            false
                        }
                    } else {
                        rms >= 60.0
                    }


                    if (shouldSend) {
                        val chunk = if (read == buffer.size) buffer else buffer.copyOf(read)
                        val base64 = Base64.encodeToString(chunk, Base64.NO_WRAP)
                        onAudioChunkRecorded(base64)
                    }
                }
            }
        }
    }
}
