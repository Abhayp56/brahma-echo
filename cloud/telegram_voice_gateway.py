"""
cloud/telegram_voice_gateway.py — ARYA Telegram Private 1-on-1 Voice Calling Gateway

Integrates Telethon and PyTgCalls to connect ARYA directly into your private
Telegram group voice chat (Arya, id: -1004215913257). Captures microphone audio
from the call into Gemini Live and streams Gemini Live's real-time voice back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import audioop
except ModuleNotFoundError:
    try:
        import audioop_lts as audioop  # Fallback for Python 3.13+
    except ModuleNotFoundError:
        audioop = None

logger = logging.getLogger("TelegramVoiceGateway")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "telegram_config.json"


def resample_48k_to_16k(pcm_48k: bytes) -> bytes:
    """
    Downsamples 48kHz 16-bit mono PCM to 16kHz 16-bit mono PCM (3:1 decimation).
    Works on Python 3.8 through 3.14+ with or without the audioop C extension.
    """
    if not pcm_48k:
        return b""
    if audioop is not None:
        try:
            pcm_16k, _ = audioop.ratecv(pcm_48k, 2, 1, 48000, 16000, None)
            return pcm_16k
        except Exception:
            pass
    # Pure Python exact 3:1 decimation: each sample is 2 bytes; keep 2 bytes out of every 6
    return b"".join(pcm_48k[i : i + 2] for i in range(0, len(pcm_48k) - 1, 6))


def resample_24k_to_48k(pcm_24k: bytes) -> bytes:
    """
    Upsamples 24kHz 16-bit mono PCM to 48kHz 16-bit mono PCM (1:2 repetition).
    Works on Python 3.8 through 3.14+ with or without the audioop C extension.
    """
    if not pcm_24k:
        return b""
    if audioop is not None:
        try:
            pcm_48k, _ = audioop.ratecv(pcm_24k, 2, 1, 24000, 48000, None)
            return pcm_48k
        except Exception:
            pass
    # Pure Python exact 1:2 duplication: duplicate each 2-byte sample
    return b"".join(pcm_24k[i : i + 2] * 2 for i in range(0, len(pcm_24k) - 1, 2))


def resample_24k_mono_to_48k_stereo(pcm_24k_mono: bytes, gain: float = 1.3) -> bytes:
    """
    Converts 24kHz 16-bit mono PCM (from Gemini Live) to 48kHz 16-bit stereo PCM (for Telegram WebRTC).
    Performs smooth linear interpolation upsampling to eliminate jagged step artifacts and robotic buzz,
    applies a +30% volume boost for crystal-clear audibility, and duplicates across Left & Right channels.
    Ratio is exactly 4.0: 1 mono sample (2 bytes) -> 2 stereo samples (8 bytes).
    Eliminates 2x playback speed ("speaking so fast") and distortion ("not clear").
    """
    if not pcm_24k_mono:
        return b""

    # Apply volume boost for clear audibility in Telegram voice room
    boosted = pcm_24k_mono
    if gain != 1.0 and audioop is not None:
        try:
            boosted = audioop.mul(pcm_24k_mono, 2, gain)
        except Exception:
            pass

    count = len(boosted) // 2
    if count == 0:
        return b""
    import struct
    samples = struct.unpack(f"<{count}h", boosted[: count * 2])
    out = []
    for j in range(count - 1):
        s1 = samples[j]
        s2 = samples[j + 1]
        mid = (s1 + s2) // 2
        out.extend([s1, s1, mid, mid])
    last = samples[-1]
    out.extend([last, last, last, last])
    return struct.pack(f"<{len(out)}h", *out)


def resample_48k_stereo_to_16k_mono(pcm_48k_stereo: bytes) -> bytes:
    """
    Converts 48kHz 16-bit stereo PCM (from Telegram WebRTC) to 16kHz 16-bit mono PCM (for Gemini Live).
    Each stereo frame is 4 bytes (2B Left + 2B Right).
    3:1 time decimation + Left channel extraction: takes 2 bytes every 12 bytes.
    Ratio is exactly 6.0: 6 bytes stereo -> 1 byte mono (12B -> 2B).
    """
    if not pcm_48k_stereo:
        return b""
    if len(pcm_48k_stereo) % 4 == 0 and len(pcm_48k_stereo) >= 12:
        return b"".join(pcm_48k_stereo[i : i + 2] for i in range(0, len(pcm_48k_stereo) - 1, 12))
    return b"".join(pcm_48k_stereo[i : i + 2] for i in range(0, len(pcm_48k_stereo) - 1, 6))


def calculate_rms(pcm_data: bytes) -> int:
    """Calculates RMS volume for 16-bit PCM audio (with or without audioop)."""
    if not pcm_data:
        return 0
    if audioop is not None:
        try:
            return audioop.rms(pcm_data, 2)
        except Exception:
            pass
    import struct, math
    count = len(pcm_data) // 2
    if count == 0:
        return 0
    samples = struct.unpack(f"<{count}h", pcm_data[: count * 2])
    sum_squares = sum(s * s for s in samples)
    return int(math.sqrt(sum_squares / count))


class TelegramVoiceGateway:
    """
    Singleton gateway managing the Telegram MTProto client and group voice chat.
    """
    _instance: Optional[TelegramVoiceGateway] = None

    @classmethod
    def get_instance(cls) -> TelegramVoiceGateway:
        if cls._instance is None:
            cls._instance = TelegramVoiceGateway()
        return cls._instance

    def __init__(self):
        self.status: str = "disconnected"  # disconnected | ready | in_call | error
        self.api_id: Optional[int] = None
        self.api_hash: Optional[str] = None
        self.session_string: Optional[str] = None
        self.account_name: Optional[str] = None
        self.phone: Optional[str] = None
        self.target_group_id: int = -1004215913257  # Verified private group ID
        self.target_group_title: str = "Arya"

        self.client: Optional[Any] = None
        self.pytgcalls_app: Optional[Any] = None
        self._audio_sender_task: Optional[asyncio.Task] = None
        self.cloud_brain: Optional[Any] = None

        self._audio_out_buffer: bytearray = bytearray()
        self._audio_lock = threading.Lock()
        self._mic_in_buffer: bytearray = bytearray()
        self._mic_lock = threading.Lock()
        self._event_listeners: List[Callable[[str, Any], None]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running: bool = False

        self._load_config()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_id and self.api_hash and self.session_string)

    def _load_config(self):
        """Loads credentials from telegram_config.json."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_id = data.get("api_id")
                    self.api_hash = data.get("api_hash")
                    self.session_string = data.get("session_string")
                    self.account_name = data.get("account_name", "ARYA")
                    self.phone = data.get("phone")
                    if data.get("target_group_id"):
                        self.target_group_id = int(data["target_group_id"])
                    if data.get("target_group_title"):
                        self.target_group_title = data["target_group_title"]
                self.status = "ready"
                logger.info(f"Loaded Telegram configuration for {self.account_name} ({self.phone})")
            except Exception as e:
                logger.warning(f"Failed to read {CONFIG_PATH}: {e}")
                self.status = "error"

    def add_listener(self, callback: Callable[[str, Any], None]):
        """Register callback for status updates."""
        self._event_listeners.append(callback)

    def _broadcast(self, event_type: str, payload: Any):
        for listener in self._event_listeners:
            try:
                listener(event_type, payload)
            except Exception as e:
                logger.warning(f"Error in Telegram listener: {e}")

    def set_cloud_brain(self, brain: Any):
        """Attaches the CloudBrain instance for bidirectional live audio."""
        self.cloud_brain = brain

    def start(self):
        """Starts background network client thread."""
        if self.is_running or not self.is_configured:
            return

        def _runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._init_client_async())
            self._loop.run_forever()

        self.is_running = True
        self._thread = threading.Thread(target=_runner, name="TelegramVoiceRunner", daemon=True)
        self._thread.start()

    async def _init_client_async(self):
        """Connects Telethon MTProto client."""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            self.client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash,
                loop=self._loop,
            )
            await self.client.start()
            self.status = "ready"
            logger.info("✅ Telegram MTProto client connected and authenticated.")
            self._broadcast("telegram_status", self.get_status())
        except Exception as e:
            logger.error(f"Failed to connect Telegram MTProto client: {e}")
            self.status = "error"
            self._broadcast("telegram_status", self.get_status())

    async def start_call(self) -> Dict[str, Any]:
        """
        Starts or joins the group voice chat in the Arya group.
        Thread-safe: dispatches onto the gateway event loop if invoked from another thread.
        """
        if not self.is_configured:
            return {"success": False, "error": "Telegram client not configured. Run login_telegram.py first."}

        if not self._loop or not self.client or not self.client.is_connected():
            return {"success": False, "error": "Telegram network client not running yet."}

        try:
            current_loop = None
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if current_loop and current_loop != self._loop:
                future = asyncio.run_coroutine_threadsafe(self._start_call_coro(), self._loop)
                return await asyncio.wrap_future(future)
            else:
                return await self._start_call_coro()
        except Exception as exc:
            logger.error(f"Failed to start/join Telegram voice call: {exc}")
            return {"success": False, "error": str(exc)}

    async def _start_call_coro(self) -> Dict[str, Any]:
        """Core call join routine running on the gateway event loop."""
        if self.status == "in_call":
            return {
                "success": True,
                "status": "in_call",
                "group_id": self.target_group_id,
                "group_title": self.target_group_title,
                "message": "ARYA is already in the voice room.",
            }

        try:
            from pytgcalls import PyTgCalls
            from pytgcalls.types import (
                MediaStream,
                ExternalMedia,
                RecordStream,
                Device,
                Direction,
                StreamFrames,
            )
            from pytgcalls.types.raw import AudioParameters
            from pytgcalls.types.calls import GroupCallConfig
            from telethon.tl.functions.phone import CreateGroupCallRequest

            logger.info(f"Connecting to Telegram group: {self.target_group_title} ({self.target_group_id})...")
            group_entity = await self.client.get_entity(self.target_group_id)

            # Attempt to create group call if not active
            try:
                random_id = random.randint(100000, 99999999)
                await self.client(
                    CreateGroupCallRequest(
                        peer=group_entity,
                        random_id=random_id,
                        title="ARYA Executive Voice Room",
                    )
                )
                logger.info("Created new Telegram group voice chat room.")
            except Exception as e:
                logger.debug(f"Group call check/creation note: {e}")

            # Initialize PyTgCalls if not already initialized
            if not self.pytgcalls_app:
                self.pytgcalls_app = PyTgCalls(self.client)

                @self.pytgcalls_app.on_update()
                async def _handle_tg_stream_update(client, update):
                    try:
                        if isinstance(update, StreamFrames) and update.direction == Direction.INCOMING:
                            for f in update.frames:
                                if f.frame:
                                    self._on_recorded_data(None, f.frame, len(f.frame))
                    except Exception as frame_err:
                        logger.debug(f"StreamFrame handler error: {frame_err}")

            if not getattr(self.pytgcalls_app, "_is_running", False):
                await self.pytgcalls_app.start()

            # Join call and configure 48kHz stereo audio playback
            audio_params = AudioParameters(bitrate=48000, channels=2)
            await self.pytgcalls_app.play(
                self.target_group_id,
                MediaStream(ExternalMedia.AUDIO, audio_parameters=audio_params),
                config=GroupCallConfig(auto_start=True),
            )

            try:
                await self.pytgcalls_app.record(
                    self.target_group_id,
                    RecordStream(audio=True, audio_parameters=audio_params),
                )
            except Exception as rec_err:
                logger.debug(f"RecordStream notice: {rec_err}")

            # Explicitly unmute ARYA and set clear transmission volume with retries
            async def _ensure_unmuted():
                for delay in [0.2, 1.0, 3.0]:
                    await asyncio.sleep(delay)
                    if self.status == "in_call" and self.pytgcalls_app:
                        try:
                            await self.pytgcalls_app.unmute(self.target_group_id)
                            logger.info(f"Unmuted ARYA in Telegram voice room (delay={delay}s).")
                        except Exception as un_err:
                            logger.debug(f"Unmute note: {un_err}")
                        try:
                            await self.pytgcalls_app.change_volume_call(self.target_group_id, 200)
                        except Exception:
                            pass

            asyncio.create_task(_ensure_unmuted())

            self.status = "in_call"
            with self._audio_lock:
                self._audio_out_buffer.clear()
            with self._mic_lock:
                self._mic_in_buffer.clear()

            # Start background sender loop for Gemini audio frames
            if self._audio_sender_task and not self._audio_sender_task.done():
                self._audio_sender_task.cancel()
            self._audio_sender_task = asyncio.create_task(self._audio_sender_loop())

            self._broadcast("telegram_status", self.get_status())

            # Send brief confirmation in group chat
            try:
                await self.client.send_message(
                    group_entity,
                    "⚡ ARYA is active in the voice room! Speak anytime, Boss."
                )
            except Exception:
                pass

            # Immediate spoken greeting so user hears ARYA's voice loud and clear upon joining
            if self.cloud_brain:
                async def _spoken_greeting():
                    await asyncio.sleep(1.2)
                    try:
                        await self.cloud_brain.handle_text_command(
                            "Hello boss! I'm active in the voice room. How can I help you today?"
                        )
                    except Exception as ge:
                        logger.debug(f"Greeting error: {ge}")
                asyncio.create_task(_spoken_greeting())

            return {
                "success": True,
                "status": "in_call",
                "group_id": self.target_group_id,
                "group_title": self.target_group_title,
                "message": "ARYA has joined the Telegram voice room.",
            }

        except Exception as exc:
            logger.error(f"Failed to start/join Telegram voice call: {exc}")
            return {"success": False, "error": str(exc)}

    async def leave_call(self) -> Dict[str, Any]:
        """
        Leaves the active voice chat.
        Thread-safe: dispatches onto the gateway event loop if invoked from another thread.
        """
        if self.status != "in_call":
            return {"success": True, "status": "idle", "message": "Not in call."}

        if not self._loop:
            return {"success": False, "error": "Telegram network client not running."}

        try:
            current_loop = None
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if current_loop and current_loop != self._loop:
                future = asyncio.run_coroutine_threadsafe(self._leave_call_coro(), self._loop)
                return await asyncio.wrap_future(future)
            else:
                return await self._leave_call_coro()
        except Exception as exc:
            logger.error(f"Error leaving Telegram call: {exc}")
            return {"success": False, "error": str(exc)}

    async def _leave_call_coro(self) -> Dict[str, Any]:
        """Core leave routine running on the gateway event loop."""
        if self._audio_sender_task and not self._audio_sender_task.done():
            self._audio_sender_task.cancel()
            self._audio_sender_task = None

        if self.pytgcalls_app:
            try:
                await self.pytgcalls_app.leave_call(self.target_group_id)
            except Exception as e:
                logger.debug(f"PyTgCalls leave_call note: {e}")

        self.status = "ready"
        with self._audio_lock:
            self._audio_out_buffer.clear()
        with self._mic_lock:
            self._mic_in_buffer.clear()

        self._broadcast("telegram_status", self.get_status())
        logger.info("Left Telegram group voice chat.")
        return {"success": True, "status": "ready", "message": "Left Telegram voice chat."}

    async def _audio_sender_loop(self):
        """Pumps 48kHz stereo PCM audio frames to Telegram voice chat with precision monotonic 20ms pacing."""
        from pytgcalls.types import Device
        # 48000 Hz * 2 channels (stereo) * 2 bytes/sample * 0.02s = 3840 bytes per 20ms frame
        frame_size = 3840
        silence_frame = b"\x00" * frame_size
        next_send_time = time.monotonic()
        last_error_time = 0.0

        while self.status == "in_call":
            chunk = None
            with self._audio_lock:
                if len(self._audio_out_buffer) >= frame_size:
                    chunk = bytes(self._audio_out_buffer[:frame_size])
                    del self._audio_out_buffer[:frame_size]
                elif len(self._audio_out_buffer) > 0:
                    chunk = bytes(self._audio_out_buffer).ljust(frame_size, b"\x00")
                    self._audio_out_buffer.clear()

            # Continuous warm RTP streaming: keeps WebRTC pipeline active so there is 0 start latency
            frame_to_send = chunk if chunk else silence_frame
            try:
                if self.pytgcalls_app:
                    await self.pytgcalls_app.send_frame(
                        self.target_group_id,
                        Device.MICROPHONE,
                        frame_to_send,
                    )
            except Exception as e:
                now_t = time.monotonic()
                if now_t - last_error_time > 5.0:
                    logger.warning(f"Telegram send_frame warning: {e}")
                    last_error_time = now_t

            # Precision monotonic pacing: exactly 50.0 frames/sec (prevents speech speedup or jitter)
            next_send_time += 0.02
            now = time.monotonic()
            sleep_duration = next_send_time - now
            if sleep_duration > 0.002:
                await asyncio.sleep(sleep_duration)
            elif (now - next_send_time) > 0.08:
                # If we fell behind by more than 4 frames (>80ms), re-align time anchor
                next_send_time = now
            else:
                await asyncio.sleep(0.001)

    def clear_output_buffer(self) -> int:
        """Flushes all queued outgoing audio from Telegram playout buffer for instant barge-in."""
        with self._audio_lock:
            cleared = len(self._audio_out_buffer)
            self._audio_out_buffer.clear()
            return cleared

    def feed_output_audio(self, pcm_24k_mono: bytes):
        """
        Feeds Gemini Live's 24kHz 16-bit mono PCM audio out into Telegram's 48kHz stereo playout buffer.
        """
        if not pcm_24k_mono:
            return
        try:
            pcm_48k_stereo = resample_24k_mono_to_48k_stereo(pcm_24k_mono)
            with self._audio_lock:
                self._audio_out_buffer.extend(pcm_48k_stereo)
                # Keep buffer up to 30 seconds of 48kHz stereo (5,760,000 bytes) so sentences are never truncated
                max_bytes = 48000 * 4 * 30
                if len(self._audio_out_buffer) > max_bytes:
                    del self._audio_out_buffer[:-max_bytes]
            self._feed_count = getattr(self, "_feed_count", 0) + 1
            if self._feed_count % 50 == 1:
                logger.info(f"Buffered Gemini audio for Telegram ({len(pcm_24k_mono)}B -> {len(self._audio_out_buffer)}B stereo buffer)")
        except Exception as err:
            logger.error(f"Error buffering Gemini audio for Telegram: {err}")

    def _on_played_data(self, group_call: Any, length: int) -> bytes:
        """
        Callback from tgcalls requesting `length` bytes of raw audio to broadcast into Telegram.
        """
        with self._audio_lock:
            if len(self._audio_out_buffer) >= length:
                chunk = bytes(self._audio_out_buffer[:length])
                del self._audio_out_buffer[:length]
                return chunk
            elif len(self._audio_out_buffer) > 0:
                chunk = bytes(self._audio_out_buffer)
                self._audio_out_buffer.clear()
                return chunk.ljust(length, b"\x00")
            else:
                return b"\x00" * length

    def _on_recorded_data(self, group_call: Any, frame: bytes, length: int):
        """
        Callback from tgcalls with raw 48kHz stereo audio from user's mic in Telegram voice chat.
        Downsamples to 16kHz mono, batches into 50ms packets, applies adaptive speech detection
        with 350ms hangover holdoff, gates room noise into pure digital silence for instant Gemini
        Live turn completion (<300ms), and flushes stale playback buffer on user barge-in.
        """
        if not frame or not self.cloud_brain:
            return
        try:
            pcm_16k = resample_48k_stereo_to_16k_mono(frame)
            if not pcm_16k:
                return

            payload_to_send = None
            with self._mic_lock:
                self._mic_in_buffer.extend(pcm_16k)
                # 50ms frame at 16kHz mono 16-bit = 16000 * 2 * 0.05 = 1600 bytes
                if len(self._mic_in_buffer) >= 1600:
                    payload_to_send = bytes(self._mic_in_buffer[:1600])
                    del self._mic_in_buffer[:1600]

            if not payload_to_send:
                return

            rms = calculate_rms(payload_to_send)

            # Adaptive noise floor and speech detection
            if not hasattr(self, "_noise_floor"):
                self._noise_floor = 60.0
                self._speech_hangover_frames = 0
                self._is_user_speaking = False

            # Track background noise floor slowly when signal is quiet
            if rms < self._noise_floor * 1.5:
                self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms

            speech_threshold = max(90, int(self._noise_floor + 35))

            if rms > speech_threshold:
                # 7 frames of 50ms = 350ms hangover to protect natural sentence endings
                self._speech_hangover_frames = 7
                if not self._is_user_speaking:
                    self._is_user_speaking = True
                    cleared = self.clear_output_buffer()
                    logger.info(f"⚡ User speaking (RMS={rms}, thresh={speech_threshold}) | Flushed {cleared}B stale audio.")
                gated_audio = payload_to_send
            elif self._speech_hangover_frames > 0:
                self._speech_hangover_frames -= 1
                # Forward speech hangover untouched
                gated_audio = payload_to_send
            else:
                if self._is_user_speaking:
                    self._is_user_speaking = False
                    logger.info("Silence detected: forwarding clean digital silence for instant Gemini Live turn detection.")
                # Send pure digital zeros so Gemini Live detects end-of-turn in <250ms
                gated_audio = b"\x00" * len(payload_to_send)

            if self.cloud_brain.session and self.cloud_brain._loop:
                asyncio.run_coroutine_threadsafe(
                    self.cloud_brain.send_audio(gated_audio),
                    self.cloud_brain._loop,
                )
                self._rec_count = getattr(self, "_rec_count", 0) + 1
                if self._rec_count % 40 == 1:
                    logger.info(f"Forwarded mic audio chunk ({len(gated_audio)}B, rms={rms}, speaking={self._is_user_speaking}) to Gemini Live.")
        except Exception as e:
            logger.debug(f"Audio forward error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns structured gateway status."""
        return {
            "status": self.status,
            "is_configured": self.is_configured,
            "in_call": self.status == "in_call",
            "account_name": self.account_name,
            "phone": self.phone,
            "group_id": self.target_group_id,
            "group_title": self.target_group_title,
        }
