"""
cloud/telegram_voice_gateway.py — ARYA Telegram Private 1-on-1 Voice Calling Gateway

Integrates Telethon and PyTgCalls to connect ARYA directly into your private
Telegram group voice chat (Arya, id: -1004215913257). Captures microphone audio
from the call into Gemini Live and streams Gemini Live's real-time voice back.
"""

from __future__ import annotations

import asyncio
import audioop
import json
import logging
import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("TelegramVoiceGateway")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "telegram_config.json"


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
        self.group_call: Optional[Any] = None
        self.pytgcalls_factory: Optional[Any] = None
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
        """
        if not self.is_configured:
            return {"success": False, "error": "Telegram client not configured. Run login_telegram.py first."}

        if not self.client or not self.client.is_connected():
            if self._loop:
                await self._init_client_async()
            else:
                return {"success": False, "error": "Telegram network client not running."}

        try:
            from pytgcalls import GroupCallFactory
            from pytgcalls.group_call_factory import MTProtoClientType
            from telethon.tl.functions.phone import CreateGroupCallRequest

            logger.info(f"Connecting to Telegram group: {self.target_group_title} ({self.target_group_id})...")
            group_entity = await self.client.get_entity(self.target_group_id)

            # Check if group call is active, or start it
            try:
                full_chat = await self.client(
                    telethon.tl.functions.channels.GetFullChannelRequest(channel=group_entity)
                ) if hasattr(group_entity, "broadcast") or getattr(group_entity, "megagroup", False) else None
            except Exception:
                full_chat = None

            # Attempt to create call if not already active
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
                # Often returns GROUPCALL_ALREADY_DISCARDED or already active error; continue
                logger.info(f"Group call creation status: {e} (continuing to join)")

            # Initialize pytgcalls raw audio stream
            if not self.group_call:
                self.pytgcalls_factory = GroupCallFactory(self.client, MTProtoClientType.TELETHON)
                self.group_call = self.pytgcalls_factory.get_raw_group_call(
                    on_played_data=self._on_played_data,
                    on_recorded_data=self._on_recorded_data,
                )

            logger.info("Joining Telegram group voice chat with raw audio pipeline...")
            await self.group_call.start(self.target_group_id)

            self.status = "in_call"
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
        """Leaves the active voice chat."""
        if not self.group_call or self.status != "in_call":
            return {"success": True, "status": "idle", "message": "Not in call."}

        try:
            await self.group_call.stop()
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
            pcm_48k, _ = audioop.ratecv(pcm_24k_mono, 2, 1, 24000, 48000, None)
            with self._audio_lock:
                self._audio_out_buffer.extend(pcm_48k)
                # Keep buffer under 3 seconds to avoid latency
                max_bytes = 48000 * 2 * 3
                if len(self._audio_out_buffer) > max_bytes:
                    del self._audio_out_buffer[:-max_bytes]
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
            pcm_16k, _ = audioop.ratecv(frame, 2, 1, 48000, 16000, None)
            if self.cloud_brain.session and self.cloud_brain._loop:
                asyncio.run_coroutine_threadsafe(
                    self.cloud_brain.send_audio(pcm_16k),
                    self.cloud_brain._loop,
                )
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
