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


def resample_24k_mono_to_48k_stereo(pcm_24k_mono: bytes) -> bytes:
    """
    Converts 24kHz 16-bit mono PCM (from Gemini Live) to 48kHz 16-bit stereo PCM (for Telegram WebRTC).
    Each 2-byte mono sample is duplicated across time (1:2) and channels (Left=Right).
    Ratio is exactly 4.0: 1 sample (2 bytes) -> 2 stereo samples (8 bytes).
    Eliminates 2x playback speed ("speaking so fast") and distortion ("not clear").
    """
    if not pcm_24k_mono:
        return b""
    return b"".join(pcm_24k_mono[i : i + 2] * 4 for i in range(0, len(pcm_24k_mono) - 1, 2))


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

            self.status = "in_call"
            with self._audio_lock:
                self._audio_out_buffer.clear()

            # Start background sender loop for Gemini audio frames
            if self._audio_sender_task and not self._audio_sender_task.done():
                self._audio_sender_task.cancel()
            self._audio_sender_task = asyncio.create_task(self._audio_sender_loop())

            self._broadcast("telegram_status", self.get_status())

            # Send brief confirmation in group
            try:
                await self.client.send_message(
                    group_entity,
                    "⚡ ARYA is active in the voice room! Speak anytime, Boss."
                )
            except Exception:
                pass

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

        self._broadcast("telegram_status", self.get_status())
        logger.info("Left Telegram group voice chat.")
        return {"success": True, "status": "ready", "message": "Left Telegram voice chat."}

    async def _audio_sender_loop(self):
        """Pumps 48kHz stereo PCM audio frames to Telegram voice chat with precision monotonic 20ms pacing."""
        from pytgcalls.types import Device
        # 48000 Hz * 2 channels (stereo) * 2 bytes/sample * 0.02s = 3840 bytes per 20ms frame
        frame_size = 3840
        silence_frame = b"\x00" * frame_size
        silence_sent = 0
        next_send_time = time.monotonic()

        while self.status == "in_call":
            chunk = None
            with self._audio_lock:
                if len(self._audio_out_buffer) >= frame_size:
                    chunk = bytes(self._audio_out_buffer[:frame_size])
                    del self._audio_out_buffer[:frame_size]
                elif len(self._audio_out_buffer) > 0:
                    chunk = bytes(self._audio_out_buffer).ljust(frame_size, b"\x00")
                    self._audio_out_buffer.clear()

            if chunk:
                silence_sent = 0
                try:
                    if self.pytgcalls_app:
                        await self.pytgcalls_app.send_frame(
                            self.target_group_id,
                            Device.MICROPHONE,
                            chunk,
                        )
                except Exception as e:
                    logger.debug(f"send_frame error: {e}")
            else:
                if silence_sent < 15:  # ~300ms trailing comfort silence
                    try:
                        if self.pytgcalls_app:
                            await self.pytgcalls_app.send_frame(
                                self.target_group_id,
                                Device.MICROPHONE,
                                silence_frame,
                            )
                    except Exception:
                        pass
                    silence_sent += 1

            # Precision monotonic pacing: exactly 50.0 frames/sec (prevents speech speedup or jitter)
            next_send_time += 0.02
            sleep_duration = next_send_time - time.monotonic()
            if sleep_duration > 0.002:
                await asyncio.sleep(sleep_duration)
            elif sleep_duration < -0.1:
                next_send_time = time.monotonic()
                await asyncio.sleep(0.005)
            else:
                await asyncio.sleep(0.001)

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
                # Keep buffer under 3 seconds of 48kHz stereo (48000 * 2 channels * 2 bytes * 3 = 576,000 bytes)
                max_bytes = 48000 * 4 * 3
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
        Callback from tgcalls with raw 48kHz stereo audio from the user's mic.
        Downsamples to 16kHz mono and forwards to Gemini Live.
        """
        if not frame or not self.cloud_brain:
            return
        try:
            pcm_16k = resample_48k_stereo_to_16k_mono(frame)
            if self.cloud_brain.session and self.cloud_brain._loop:
                asyncio.run_coroutine_threadsafe(
                    self.cloud_brain.send_audio(pcm_16k),
                    self.cloud_brain._loop,
                )
                self._rec_count = getattr(self, "_rec_count", 0) + 1
                if self._rec_count % 50 == 1:
                    logger.info(f"Forwarded mic audio chunk ({len(pcm_16k)} bytes) to Gemini Live.")
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
