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
        self.group_call: Optional[Any] = None
        self.pytgcalls_factory: Optional[Any] = None
        self.cloud_brain: Optional[Any] = None

        self._audio_out_buffer: bytearray = bytearray()
        self._audio_lock = threading.Lock()
        self._playout_task: Optional[asyncio.Task] = None
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

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Starts background network client on the provided loop or a dedicated runner thread."""
        if self.is_running or not self.is_configured:
            return

        # If a running event loop is provided or available in current thread, use it directly
        running_loop = loop
        if running_loop is None:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

        if running_loop is not None:
            self._loop = running_loop
            self.is_running = True
            self._loop.create_task(self._init_client_async())
            logger.info("Telegram Voice Gateway initialized on existing asyncio event loop.")
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
        """Dispatches start_call to the event loop where the Telegram client was created."""
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._loop and curr_loop != self._loop:
            future = asyncio.run_coroutine_threadsafe(self._do_start_call(), self._loop)
            return await asyncio.wrap_future(future)
        return await self._do_start_call()

    async def _do_start_call(self) -> Dict[str, Any]:
        """
        Starts or joins the group voice chat in the Arya group on self._loop.
        """
        if not self.is_configured:
            return {"success": False, "error": "Telegram client not configured. Run login_telegram.py first."}

        if not self.client or not self.client.is_connected():
            if self._loop:
                await self._init_client_async()
            else:
                return {"success": False, "error": "Telegram network client not running."}

        try:
            logger.info(f"Connecting to Telegram group: {self.target_group_title} ({self.target_group_id})...")
            group_entity = await self.client.get_entity(self.target_group_id)

            # Check if group call is active, or start it
            try:
                from telethon.tl.functions.phone import CreateGroupCallRequest
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
                logger.info(f"Group call check/creation notice: {e}")

            # Join voice chat using PyTgCalls 2.x
            joined = False
            try:
                from pytgcalls import PyTgCalls
                from pytgcalls.types import MediaStream, ExternalMedia, GroupCallConfig, StreamFrames, Direction, Device

                if self.pytgcalls_app is None:
                    self.pytgcalls_app = PyTgCalls(self.client)

                if not getattr(self.pytgcalls_app, "_is_running", False):
                    await self.pytgcalls_app.start()

                # Add real-time audio input callback
                async def _on_stream_update(client, update):
                    try:
                        if isinstance(update, StreamFrames) and update.direction == Direction.INCOMING:
                            for frame in update.frames:
                                if frame.frame:
                                    self._on_recorded_data(None, frame.frame, len(frame.frame))
                    except Exception as frame_err:
                        logger.warning(f"Audio frame receive error: {frame_err}")

                self.pytgcalls_app.add_handler(_on_stream_update)

                config = GroupCallConfig(auto_start=True)
                media = MediaStream(ExternalMedia.AUDIO)
                await self.pytgcalls_app.play(self.target_group_id, media, config=config)
                joined = True
                logger.info("Joined Telegram group call via PyTgCalls 2.x.")

                # Start audio playout pacer
                if self._playout_task is None or self._playout_task.done():
                    self._playout_task = asyncio.create_task(self._playout_loop())

            except Exception as e1:
                logger.warning(f"PyTgCalls 2.x start failed: {e1}")

            if not joined:
                # Safe legacy fallback for pytgcalls 0.9/1.x if present
                try:
                    from pytgcalls import GroupCallFactory
                    from pytgcalls.group_call_factory import MTProtoClientType
                    self.pytgcalls_factory = GroupCallFactory(self.client, MTProtoClientType.TELETHON)
                    self.group_call = self.pytgcalls_factory.get_raw_group_call(
                        on_played_data=self._on_played_data,
                        on_recorded_data=self._on_recorded_data,
                    )
                    await self.group_call.start(self.target_group_id)
                    joined = True
                    logger.info("Joined Telegram group call via legacy GroupCallFactory.")
                except Exception as e2:
                    logger.warning(f"Legacy GroupCallFactory fallback not available: {e2}")

            if not joined:
                return {"success": False, "error": "Could not join voice chat with PyTgCalls drivers."}

            self.status = "in_call"
            self._broadcast("telegram_status", self.get_status())

            # Trigger immediate verbal greeting from ARYA out loud in the voice call
            if self.cloud_brain and self.cloud_brain.session:
                target_loop = self.cloud_brain._loop or self._loop
                if target_loop and target_loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.cloud_brain.handle_text_command(
                            "You are now live in the private Telegram voice call with Boss. Greet Boss out loud immediately with your signature sharp, witty style like: 'Hey Boss, I'm live on Telegram. What's on your mind?'"
                        ),
                        target_loop,
                    )
                    logger.info("Triggered initial Telegram voice call verbal greeting from ARYA.")

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

    async def _playout_loop(self):
        """Paces outgoing 48kHz audio to PyTgCalls in 20ms chunks (1920 bytes)."""
        logger.info("Starting Telegram audio playout pacer loop.")
        try:
            from pytgcalls.types import Device
            sent_count = 0
            while self.status == "in_call":
                chunk = None
                with self._audio_lock:
                    if len(self._audio_out_buffer) >= 1920:
                        chunk = bytes(self._audio_out_buffer[:1920])
                        del self._audio_out_buffer[:1920]
                if chunk and self.pytgcalls_app:
                    try:
                        await self.pytgcalls_app.send_frame(self.target_group_id, Device.MICROPHONE, chunk)
                        sent_count += 1
                        if sent_count % 100 == 1:
                            logger.info(f"Streamed audio frames to Telegram voice room (packet #{sent_count}).")
                    except Exception as e:
                        logger.warning(f"send_frame error: {e}")
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.error(f"Error in audio playout pacer loop: {err}")
        finally:
            logger.info("Stopped Telegram audio playout pacer loop.")

    async def leave_call(self) -> Dict[str, Any]:
        """Dispatches leave_call to the event loop where the Telegram client was created."""
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._loop and curr_loop != self._loop:
            future = asyncio.run_coroutine_threadsafe(self._do_leave_call(), self._loop)
            return await asyncio.wrap_future(future)
        return await self._do_leave_call()

    async def _do_leave_call(self) -> Dict[str, Any]:
        """Leaves the active voice chat on self._loop."""
        if self.status != "in_call":
            return {"success": True, "status": "idle", "message": "Not in call."}

        try:
            if self._playout_task and not self._playout_task.done():
                self._playout_task.cancel()
                self._playout_task = None

            if hasattr(self, "pytgcalls_app") and self.pytgcalls_app:
                try:
                    await self.pytgcalls_app.leave_call(self.target_group_id)
                except Exception:
                    pass
            if self.group_call:
                try:
                    await self.group_call.stop()
                except Exception:
                    pass

            self.status = "ready"
            with self._audio_lock:
                self._audio_out_buffer.clear()
            self._broadcast("telegram_status", self.get_status())
            logger.info("Left Telegram group voice chat.")
            return {"success": True, "status": "ready", "message": "Left Telegram voice chat."}
        except Exception as e:
            logger.error(f"Error leaving Telegram call: {e}")
            return {"success": False, "error": str(e)}

    def feed_output_audio(self, pcm_24k_mono: bytes):
        """
        Feeds Gemini Live's 24kHz 16-bit PCM audio out into Telegram's 48kHz playout buffer.
        """
        if not pcm_24k_mono:
            return
        try:
            # Resample from 24,000 Hz to 48,000 Hz for Telegram
            pcm_48k = resample_24k_to_48k(pcm_24k_mono)
            with self._audio_lock:
                self._audio_out_buffer.extend(pcm_48k)
                # Keep buffer under 3 seconds to avoid latency
                max_bytes = 48000 * 2 * 3
                if len(self._audio_out_buffer) > max_bytes:
                    del self._audio_out_buffer[:-max_bytes]
            self._feed_count = getattr(self, "_feed_count", 0) + 1
            if self._feed_count % 50 == 1:
                logger.info(f"Received Gemini audio chunk ({len(pcm_24k_mono)} bytes) -> Telegram buffer: {len(self._audio_out_buffer)} bytes")
        except Exception as err:
            logger.error(f"Error buffering Gemini audio for Telegram: {err}")

    def _on_played_data(self, group_call: Any, length: int) -> bytes:
        """
        Callback from tgcalls requesting `length` bytes of raw 48kHz audio to broadcast into Telegram.
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
        Callback from tgcalls with `length` bytes of raw 48kHz audio from the user's mic.
        """
        if not frame or not self.cloud_brain:
            return
        try:
            # Downsample 48,000 Hz to 16,000 Hz for Gemini Live input
            pcm_16k = resample_48k_to_16k(frame)
            if self.cloud_brain and self.cloud_brain.session:
                target_loop = self.cloud_brain._loop or self._loop
                if target_loop and target_loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.cloud_brain.handle_incoming_audio(pcm_16k),
                        target_loop,
                    )
                    self._rec_count = getattr(self, "_rec_count", 0) + 1
                    if self._rec_count % 100 == 1:
                        logger.info(f"Forwarded mic audio chunk ({len(pcm_16k)} bytes) to Gemini Live.")
        except Exception as e:
            logger.warning(f"Audio forward error: {e}")

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
