package com.brahma.connect.ui

import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brahma.connect.call.CallManager
import com.brahma.connect.core.AgentStateStore
import com.brahma.connect.core.CallState
import com.brahma.connect.ui.theme.BrahmaConnectTheme
import kotlinx.coroutines.delay

class CallActivity : ComponentActivity() {
    companion object {
        const val EXTRA_CALL_ID = "extra_call_id"
        const val EXTRA_CALLER_NAME = "extra_caller_name"
        const val EXTRA_REASON = "extra_reason"
    }

    private lateinit var callManager: CallManager

    private val requestMicPermission = registerForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            android.util.Log.i("CallActivity", "Microphone permission granted.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        callManager = CallManager.getInstance(this)

        setupLockscreenFlags()

        if (androidx.core.content.ContextCompat.checkSelfPermission(this, android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestMicPermission.launch(android.Manifest.permission.RECORD_AUDIO)
        }

        val callerName = intent.getStringExtra(EXTRA_CALLER_NAME) ?: "ARYA"
        val reason = intent.getStringExtra(EXTRA_REASON) ?: "Voice Call"

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
                    onAccept = {
                        if (androidx.core.content.ContextCompat.checkSelfPermission(this@CallActivity, android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                            requestMicPermission.launch(android.Manifest.permission.RECORD_AUDIO)
                        }
                        callManager.acceptCall()
                    },
                    onReject = {
                        callManager.rejectCall()
                        finish()
                    },
                    onEnd = {
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
}

@Composable
fun CallScreenContent(
    callerName: String,
    reason: String,
    callState: CallState,
    onAccept: () -> Unit,
    onReject: () -> Unit,
    onEnd: () -> Unit,
    onMuteToggle: (Boolean) -> Unit,
    onSpeakerToggle: (Boolean) -> Unit,
) {
    var isMuted by remember { mutableStateOf(false) }
    var isSpeakerOn by remember { mutableStateOf(true) }
    var callSeconds by remember { mutableIntStateOf(0) }

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
                    text = reason,
                    style = MaterialTheme.typography.titleMedium.copy(
                        color = Color(0xFFF4B400)
                    )
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = when (callState) {
                        CallState.RINGING -> "Incoming Call..."
                        CallState.ACTIVE -> {
                            val mins = callSeconds / 60
                            val secs = callSeconds % 60
                            String.format("%02d:%02d", mins, secs)
                        }
                        CallState.ENDED -> "Call Ended"
                        else -> "Connecting..."
                    },
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = Color(0xFF8E949D)
                    )
                )
            }

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
