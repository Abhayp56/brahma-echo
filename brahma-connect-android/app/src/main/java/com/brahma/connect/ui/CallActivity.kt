package com.brahma.connect.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.brahma.connect.call.CallManager
import com.brahma.connect.camera.CameraVisionStreamer
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.core.CallState
import com.brahma.connect.ui.theme.BrahmaConnectTheme
import kotlinx.coroutines.delay

class CallActivity : ComponentActivity() {
    companion object {
        const val EXTRA_CALL_ID = "extra_call_id"
        const val EXTRA_CALLER_NAME = "extra_caller_name"
        const val EXTRA_REASON = "extra_reason"
        const val EXTRA_AUTO_ANSWER = "extra_auto_answer"
    }

    private lateinit var callManager: CallManager
    private var visionStreamer: CameraVisionStreamer? = null

    private val requestMicPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            android.util.Log.i("CallActivity", "Microphone permission granted.")
        }
    }

    private val requestCameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            android.util.Log.i("CallActivity", "Camera permission granted for vision.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        callManager = CallManager.getInstance(this)

        setupLockscreenFlags()

        if (androidx.core.content.ContextCompat.checkSelfPermission(this, android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestMicPermission.launch(android.Manifest.permission.RECORD_AUDIO)
        }

        val callerName = intent.getStringExtra(EXTRA_CALLER_NAME) ?: "JARVIS"
        val reason = intent.getStringExtra(EXTRA_REASON) ?: "Voice Call"
        val autoAnswer = intent.getBooleanExtra(EXTRA_AUTO_ANSWER, false)

        if (autoAnswer) {
            android.util.Log.i("CallActivity", "Auto-answering call from notification action.")
            callManager.acceptCall()
        }

        setContent {
            BrahmaConnectTheme {
                val callState by AgentStateStore.callState.collectAsState()

                LaunchedEffect(callState) {
                    if (callState == CallState.IDLE || callState == CallState.ENDED) {
                        delay(400)
                        finish()
                    }
                }

                CallScreenContent(
                    callerName = callerName,
                    reason = reason,
                    callState = callState,
                    hasCameraPermission = ContextCompat.checkSelfPermission(this@CallActivity, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED,
                    onRequestCameraPermission = {
                        requestCameraPermission.launch(Manifest.permission.CAMERA)
                    },
                    onStartVision = { previewView ->
                        visionStreamer = CameraVisionStreamer(this@CallActivity, this@CallActivity) { b64Jpeg ->
                            callManager.sendVisionFrame(b64Jpeg)
                        }
                        visionStreamer?.start(previewView)
                    },
                    onStopVision = {
                        visionStreamer?.stop()
                        visionStreamer = null
                    },
                    onSwitchCamera = {
                        visionStreamer?.switchCamera()
                    },
                    onAccept = {
                        if (ContextCompat.checkSelfPermission(this@CallActivity, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                            requestMicPermission.launch(Manifest.permission.RECORD_AUDIO)
                        }
                        callManager.acceptCall()
                    },
                    onReject = {
                        visionStreamer?.stop()
                        callManager.rejectCall()
                        finish()
                    },
                    onEnd = {
                        visionStreamer?.stop()
                        callManager.endCall()
                        finish()
                    },
                    onMuteToggle = { muted -> callManager.setMuted(muted) },
                    onSpeakerToggle = { speakerOn -> callManager.setSpeakerphoneOn(speakerOn) }
                )
            }
        }
    }

    private fun setupLockscreenFlags() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        )
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val autoAnswer = intent.getBooleanExtra(EXTRA_AUTO_ANSWER, false)
        if (autoAnswer) {
            android.util.Log.i("CallActivity", "Auto-answering call from onNewIntent.")
            callManager.acceptCall()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        visionStreamer?.stop()
        visionStreamer = null
    }
}

@Composable
fun CallScreenContent(
    callerName: String,
    reason: String,
    callState: CallState,
    hasCameraPermission: Boolean,
    onRequestCameraPermission: () -> Unit,
    onStartVision: (PreviewView) -> Unit,
    onStopVision: () -> Unit,
    onSwitchCamera: () -> Unit,
    onAccept: () -> Unit,
    onReject: () -> Unit,
    onEnd: () -> Unit,
    onMuteToggle: (Boolean) -> Unit,
    onSpeakerToggle: (Boolean) -> Unit,
) {
    var isMuted by remember { mutableStateOf(false) }
    var isSpeakerOn by remember { mutableStateOf(true) }
    var isVisionActive by remember { mutableStateOf(false) }
    var callSeconds by remember { mutableIntStateOf(0) }

    DisposableEffect(Unit) {
        onDispose {
            onStopVision()
        }
    }

    LaunchedEffect(callState) {
        if (callState == CallState.ACTIVE) {
            while (true) {
                delay(1000)
                callSeconds++
            }
        }
    }

    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1.0f,
        targetValue = 1.15f,
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulseScale"
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(
                        Color(0xFF060913),
                        Color(0xFF020305)
                    )
                )
            )
            .padding(24.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = 48.dp, bottom = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            // Header Info
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = callerName,
                    style = MaterialTheme.typography.headlineLarge.copy(
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFFF4F6F8),
                        letterSpacing = 1.sp
                    )
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = if (callState == CallState.ACTIVE) {
                        val mins = callSeconds / 60
                        val secs = callSeconds % 60
                        String.format("%02d:%02d", mins, secs)
                    } else reason,
                    style = MaterialTheme.typography.bodyLarge.copy(
                        color = Color(0xFF8E949D)
                    )
                )
            }

            // Center Area: Camera Viewfinder OR Glowing Orb
            if (isVisionActive && callState == CallState.ACTIVE) {
                Box(
                    modifier = Modifier
                        .size(240.dp)
                        .clip(RoundedCornerShape(28.dp))
                        .border(2.5.dp, Color(0xFF22C55E), RoundedCornerShape(28.dp))
                        .background(Color.Black),
                    contentAlignment = Alignment.Center
                ) {
                    AndroidView(
                        factory = { ctx ->
                            PreviewView(ctx).also { pv ->
                                onStartVision(pv)
                            }
                        },
                        modifier = Modifier.fillMaxSize()
                    )

                    // Flip camera overlay button
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(10.dp)
                    ) {
                        Surface(
                            onClick = onSwitchCamera,
                            shape = CircleShape,
                            color = Color.Black.copy(alpha = 0.65f),
                            contentColor = Color.White,
                            modifier = Modifier.size(40.dp)
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text("🔄", fontSize = 18.sp)
                            }
                        }
                    }

                    // Live badge overlay
                    Box(
                        modifier = Modifier
                            .align(Alignment.BottomStart)
                            .padding(10.dp)
                            .background(Color(0xFF22C55E).copy(alpha = 0.9f), RoundedCornerShape(6.dp))
                            .padding(horizontal = 8.dp, vertical = 3.dp)
                    ) {
                        Text("LIVE VISION", color = Color.Black, fontSize = 10.sp, fontWeight = FontWeight.Black)
                    }
                }
            } else {
                // Glowing Orb / Avatar
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier
                        .size(180.dp)
                        .scale(if (callState == CallState.RINGING || callState == CallState.ACTIVE) pulseScale else 1f)
                ) {
                    Box(
                        modifier = Modifier
                            .size(160.dp)
                            .background(
                                Brush.radialGradient(
                                    colors = listOf(
                                        Color(0xFFF4B400).copy(alpha = 0.35f),
                                        Color(0xFFF4B400).copy(alpha = 0.05f),
                                        Color.Transparent
                                    )
                                ),
                                shape = CircleShape
                            )
                    )
                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier
                            .size(110.dp)
                            .background(Color(0xFF10131A), shape = CircleShape)
                            .border(2.dp, Color(0xFFF4B400), CircleShape)
                    ) {
                        Text(
                            text = "A",
                            fontSize = 44.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFF4B400)
                        )
                    }
                }
            }

            // Call Action Buttons
            when (callState) {
                CallState.RINGING -> {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 32.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Decline Button
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            FloatingActionButton(
                                onClick = onReject,
                                containerColor = Color(0xFFE53935),
                                contentColor = Color.White,
                                shape = CircleShape,
                                modifier = Modifier.size(72.dp),
                                elevation = FloatingActionButtonDefaults.elevation(6.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Close,
                                    contentDescription = "Decline",
                                    modifier = Modifier.size(36.dp)
                                )
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("Decline", color = Color(0xFFE53935), fontWeight = FontWeight.SemiBold)
                        }

                        // Accept Button
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            FloatingActionButton(
                                onClick = onAccept,
                                containerColor = Color(0xFF43A047),
                                contentColor = Color.White,
                                shape = CircleShape,
                                modifier = Modifier.size(72.dp),
                                elevation = FloatingActionButtonDefaults.elevation(6.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Check,
                                    contentDescription = "Accept",
                                    modifier = Modifier.size(36.dp)
                                )
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("Accept", color = Color(0xFF43A047), fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
                CallState.ACTIVE -> {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        // Mid Controls (Mute, Speaker)
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 32.dp, vertical = 20.dp),
                            horizontalArrangement = Arrangement.SpaceEvenly
                        ) {
                            // Mute button
                            Surface(
                                onClick = {
                                    isMuted = !isMuted
                                    onMuteToggle(isMuted)
                                },
                                shape = CircleShape,
                                color = if (isMuted) Color(0xFFF4B400) else Color(0xFF1E222D),
                                contentColor = if (isMuted) Color.Black else Color.White,
                                modifier = Modifier.size(64.dp)
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Text(
                                        text = if (isMuted) "MUTED" else "MUTE",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }

                            // Speaker button
                            Surface(
                                onClick = {
                                    isSpeakerOn = !isSpeakerOn
                                    onSpeakerToggle(isSpeakerOn)
                                },
                                shape = CircleShape,
                                color = if (isSpeakerOn) Color(0xFFF4B400) else Color(0xFF1E222D),
                                contentColor = if (isSpeakerOn) Color.Black else Color.White,
                                modifier = Modifier.size(64.dp)
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Text(
                                        text = if (isSpeakerOn) "SPEAKER" else "EARPIECE",
                                        fontSize = 9.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }

                            // Vision Toggle button
                            Surface(
                                onClick = {
                                    if (!isVisionActive && !hasCameraPermission) {
                                        onRequestCameraPermission()
                                    } else {
                                        isVisionActive = !isVisionActive
                                        if (!isVisionActive) {
                                            onStopVision()
                                        }
                                    }
                                },
                                shape = CircleShape,
                                color = if (isVisionActive) Color(0xFF22C55E) else Color(0xFF1E222D),
                                contentColor = if (isVisionActive) Color.Black else Color.White,
                                modifier = Modifier.size(64.dp)
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                        Text(if (isVisionActive) "👁️" else "📷", fontSize = 16.sp)
                                        Text(
                                            text = if (isVisionActive) "VISION ON" else "VISION",
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Bold
                                        )
                                    }
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(16.dp))

                        // End Call Button
                        FloatingActionButton(
                            onClick = onEnd,
                            containerColor = Color(0xFFE53935),
                            contentColor = Color.White,
                            shape = CircleShape,
                            modifier = Modifier.size(72.dp),
                            elevation = FloatingActionButtonDefaults.elevation(6.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Close,
                                contentDescription = "End Call",
                                modifier = Modifier.size(36.dp)
                            )
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("End Call", color = Color(0xFFE53935), fontWeight = FontWeight.SemiBold)
                    }
                }
                else -> {
                    Text(
                        text = "Call Ended",
                        color = Color(0xFF8E949D),
                        fontSize = 16.sp
                    )
                }
            }
        }
    }
}
