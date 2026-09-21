package com.brahma.connect.media

import android.content.ComponentName
import android.content.Context
import android.media.AudioManager
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.Build
import android.util.Log
import android.view.KeyEvent
import com.brahma.connect.notifications.BrahmaNotificationListenerService

/**
 * Controls background media playback universally across apps (Spotify, YouTube Music, podcasts, etc.)
 * using MediaSessionManager (when NotificationListenerService is enabled) and AudioManager fallback.
 */
class UniversalMediaController(private val context: Context) {

    companion object {
        private const val TAG = "UniversalMediaCtrl"
    }

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private val sessionManager = context.getSystemService(Context.MEDIA_SESSION_SERVICE) as? MediaSessionManager

    /**
     * Retrieves metadata about the currently playing media (title, artist, album, app).
     */
    fun getNowPlaying(): Map<String, Any?> {
        val controllers = getActiveMediaControllers()
        for (controller in controllers) {
            val playbackState = controller.playbackState
            val isPlaying = playbackState != null && playbackState.state == PlaybackState.STATE_PLAYING
            val metadata = controller.metadata

            if (metadata != null || isPlaying) {
                val title = metadata?.getString(android.media.MediaMetadata.METADATA_KEY_TITLE)
                val artist = metadata?.getString(android.media.MediaMetadata.METADATA_KEY_ARTIST)
                val album = metadata?.getString(android.media.MediaMetadata.METADATA_KEY_ALBUM)

                return mapOf(
                    "is_playing" to isPlaying,
                    "title" to (title ?: "Unknown Track"),
                    "artist" to (artist ?: "Unknown Artist"),
                    "album" to (album ?: "Unknown Album"),
                    "package" to controller.packageName,
                )
            }
        }

        val isMusicActive = audioManager?.isMusicActive == true
        return mapOf(
            "is_playing" to isMusicActive,
            "title" to if (isMusicActive) "Active Audio Playing" else "Nothing Playing",
            "artist" to null,
            "album" to null,
            "package" to null,
        )
    }

    /**
     * Executes a media transport action: play, pause, toggle, next, previous, stop.
     */
    fun executeAction(action: String): Boolean {
        val normalized = action.lowercase().trim()
        val controllers = getActiveMediaControllers()

        // 1. Try direct MediaSession transport controls if active sessions exist
        if (controllers.isNotEmpty()) {
            val activeController = controllers.firstOrNull {
                it.playbackState?.state == PlaybackState.STATE_PLAYING
            } ?: controllers.first()

            val controls = activeController.transportControls
            try {
                when (normalized) {
                    "pause" -> { controls.pause(); return true }
                    "play" -> { controls.play(); return true }
                    "toggle", "play_pause" -> {
                        if (activeController.playbackState?.state == PlaybackState.STATE_PLAYING) {
                            controls.pause()
                        } else {
                            controls.play()
                        }
                        return true
                    }
                    "next", "skip_next" -> { controls.skipToNext(); return true }
                    "previous", "prev", "skip_prev" -> { controls.skipToPrevious(); return true }
                    "stop" -> { controls.stop(); return true }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Direct transport control failed, falling back to key event: ${e.message}")
            }
        }

        // 2. Fallback to system-wide media key event dispatch
        val keyCode = when (normalized) {
            "pause" -> KeyEvent.KEYCODE_MEDIA_PAUSE
            "play" -> KeyEvent.KEYCODE_MEDIA_PLAY
            "toggle", "play_pause" -> KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
            "next", "skip_next" -> KeyEvent.KEYCODE_MEDIA_NEXT
            "previous", "prev", "skip_prev" -> KeyEvent.KEYCODE_MEDIA_PREVIOUS
            "stop" -> KeyEvent.KEYCODE_MEDIA_STOP
            else -> KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
        }

        dispatchMediaKeyEvent(keyCode)
        return true
    }

    /**
     * Stop Everything: Pauses media playback, stops any active audio stream, and resets playback.
     */
    fun stopEverything(): Map<String, Any?> {
        val stoppedMedia = executeAction("pause")
        // Also dispatch STOP keycode to ensure full termination of playback
        dispatchMediaKeyEvent(KeyEvent.KEYCODE_MEDIA_STOP)

        return mapOf(
            "media_stopped" to stoppedMedia,
            "message" to "All active media playback halted."
        )
    }

    private fun dispatchMediaKeyEvent(keyCode: Int) {
        val am = audioManager ?: return
        try {
            val downEvent = KeyEvent(KeyEvent.ACTION_DOWN, keyCode)
            val upEvent = KeyEvent(KeyEvent.ACTION_UP, keyCode)
            am.dispatchMediaKeyEvent(downEvent)
            am.dispatchMediaKeyEvent(upEvent)
            Log.d(TAG, "Dispatched media key event: $keyCode")
        } catch (e: Exception) {
            Log.e(TAG, "Error dispatching media key event: ${e.message}")
        }
    }

    private fun getActiveMediaControllers(): List<MediaController> {
        if (sessionManager == null) return emptyList()

        return try {
            if (BrahmaNotificationListenerService.instance != null) {
                val component = ComponentName(context, BrahmaNotificationListenerService::class.java)
                sessionManager.getActiveSessions(component)
            } else {
                emptyList()
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "Notification listener permission needed for getActiveSessions: ${e.message}")
            emptyList()
        } catch (e: Exception) {
            Log.w(TAG, "Error fetching active media sessions: ${e.message}")
            emptyList()
        }
    }
}
