"""
laptop_worker.py — Brahma Local Laptop Task Worker

Runs on the user's local Windows laptop.
Establishes an outbound reverse WebSocket connection to the Brahma Cloud Brain,
executes local desktop tools (OS automation, apps, browser, office documents),
and handles local microphone capture and speaker playback.

Usage:
    python laptop_worker.py [--server ws://your-server:8000/ws/node] [--token YOUR_TOKEN] [--headless]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import websockets

from core.distributed.protocol import (
    ProtocolTypes,
    MessageEnvelope,
    build_message,
    parse_message,
)
from core.distributed.local_tool_dispatcher import LocalToolDispatcher, HeadlessPlayerShim

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("LaptopWorker")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "cloud_config.json"

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1024


def load_config() -> Dict[str, Any]:
    default_cfg = {
        "cloud_server_url": "ws://127.0.0.1:8000/ws/node",
        "auth_token": "brahma_secret_cloud_token_2026",
        "device_name": "My-Windows-Laptop",
        "enable_audio": True,
        "enable_ui": False,
        "reconnect_interval": 3,
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_cfg.update(cfg)
        except Exception as e:
            logger.warning(f"Failed to read {CONFIG_PATH}: {e}")
    return default_cfg


class AudioWorker:
    """Handles local microphone streaming up to Cloud and speaker playback down from Cloud."""

    def __init__(self, send_audio_cb):
        self.send_audio_cb = send_audio_cb
        self.audio_out_queue: Optional[asyncio.Queue] = None
        self.mic_stream = None
        self.is_running = False
        self.is_muted = False
        self.is_speaking = False

    def start_playback_loop(self, loop: asyncio.AbstractEventLoop):
        self.audio_out_queue = asyncio.Queue()
        try:
            import sounddevice as sd
            logger.info("Initializing audio output stream (24kHz)...")

            def _play_thread():
                try:
                    stream = sd.RawOutputStream(
                        samplerate=RECEIVE_SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=CHUNK_SIZE,
                    )
                    stream.start()
                    while self.is_running:
                        try:
                            if self.audio_out_queue:
                                future = asyncio.run_coroutine_threadsafe(self.audio_out_queue.get(), loop)
                                chunk = future.result(timeout=1.0)
                                self.is_speaking = True
                                stream.write(chunk)
                        except (asyncio.TimeoutError, Exception):
                            self.is_speaking = False
                    stream.stop()
                    stream.close()
                except Exception as e:
                    logger.warning(f"Audio output disabled or error: {e}")

            threading.Thread(target=_play_thread, daemon=True, name="audio-speaker").start()
        except Exception as e:
            logger.warning(f"Could not start audio playback: {e}")

    def start_mic_loop(self, loop: asyncio.AbstractEventLoop):
        try:
            import sounddevice as sd
            import numpy as np
            logger.info("Initializing microphone input stream (16kHz)...")

            def mic_callback(indata, frames, time_info, status):
                if not self.is_running or self.is_muted:
                    return

                # Calculate RMS
                rms = np.sqrt(np.mean(np.square(indata, dtype=np.float32)))
                # Gate audio if AI is speaking locally to prevent echo
                threshold = 1200.0 if self.is_speaking else 15.0

                if rms > threshold:
                    raw_pcm = indata.tobytes()
                    loop.call_soon_threadsafe(self.send_audio_cb, raw_pcm)

            self.mic_stream = sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=mic_callback,
            )
            self.mic_stream.start()
            logger.info("🎤 Microphone streaming active.")
            return self.mic_stream
        except Exception as e:
            logger.warning(f"Microphone input disabled or unavailable: {e}")
            return None


class LaptopWorker:
    """Client worker running on the laptop connecting to the Cloud Brain."""

    def __init__(self, config: Dict[str, Any], headless: bool = True):
        self.config = config
        self.headless = headless
        self.server_url = config.get("cloud_server_url", "ws://127.0.0.1:8000/ws/node")
        self.auth_token = config.get("auth_token", "")
        self.device_name = config.get("device_name", "Windows-Laptop")
        self.reconnect_interval = config.get("reconnect_interval", 3)

        self.player = HeadlessPlayerShim(log_callback=lambda msg: logger.info(f"[PlayerLog] {msg}"))
        self.dispatcher = LocalToolDispatcher(player=self.player)
        self.ws = None
        self.is_running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.audio_worker = None

    def queue_mic_audio(self, raw_pcm: bytes):
        """Callback to send captured microphone audio chunk over WebSocket."""
        if not getattr(self, "is_authenticated", False) or not self.ws or getattr(self.ws, "closed", True):
            return
        try:
            b64_data = base64.b64encode(raw_pcm).decode("ascii")
            msg = build_message(ProtocolTypes.AUDIO_CHUNK, {"data": b64_data})
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(self.ws.send(msg.to_json()), self.loop)
        except Exception:
            pass

    async def _handle_execute_tool(self, req_id: str, payload: Dict[str, Any]):
        """Execute local tool on this PC and return results to cloud server."""
        tool_name = payload.get("tool_name", "")
        args = payload.get("args", {})

        logger.info(f"Received tool execution command from Cloud: '{tool_name}'")
        res = await self.dispatcher.execute(tool_name, args)

        # Send back TOOL_RESULT
        reply = build_message(
            ProtocolTypes.TOOL_RESULT,
            payload=res,
            request_id=req_id,
        )
        if self.ws and not self.ws.closed:
            await self.ws.send(reply.to_json())
            logger.info(f"Sent result for '{tool_name}' back to Cloud.")

    async def _connect_and_listen(self):
        self.is_authenticated = False
        logger.info(f"Connecting to Brahma Cloud Brain at {self.server_url}...")
        try:
            async with websockets.connect(self.server_url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("Connected to server. Sending authentication handshake...")

                # 1. Send AUTH
                auth_msg = build_message(
                    ProtocolTypes.AUTH,
                    payload={
                        "token": self.auth_token,
                        "device_name": self.device_name,
                        "platform": sys.platform,
                    },
                )
                await ws.send(auth_msg.to_json())

                # 2. Wait for AUTH_ACK
                ack_raw = await ws.recv()
                ack = parse_message(ack_raw)
                if ack.type != ProtocolTypes.AUTH_ACK:
                    logger.error(f"Authentication rejected by Cloud Server: {ack.payload}")
                    return

                self.ws = ws
                self.is_authenticated = True
                logger.info("🟢 Authenticated with Cloud Brain! Ready to execute desktop tasks.")

                # 3. Message dispatch loop
                async for raw in ws:
                    msg = parse_message(raw)

                    if msg.type == ProtocolTypes.EXECUTE_TOOL:
                        asyncio.create_task(self._handle_execute_tool(msg.request_id, msg.payload))

                    elif msg.type == ProtocolTypes.AUDIO_CHUNK:
                        # Voice playback is handled entirely on the web interface; laptop stays silent
                        pass

                    elif msg.type == ProtocolTypes.PING:
                        pong = build_message(ProtocolTypes.PONG, request_id=msg.request_id)
                        await ws.send(pong.to_json())
        finally:
            self.is_authenticated = False
            self.ws = None

    async def run(self):
        self.loop = asyncio.get_event_loop()
        self.is_running = True

        # Audio playback is strictly off on laptop worker (audio handled on web interface)
        if self.config.get("enable_speaker", False):
            self.audio_worker = AudioWorker(self.queue_mic_audio)
            self.audio_worker.is_running = True
            self.audio_worker.start_playback_loop(self.loop)
        if self.config.get("enable_mic", False):
            if not self.audio_worker:
                self.audio_worker = AudioWorker(self.queue_mic_audio)
                self.audio_worker.is_running = True
            self.audio_worker.start_mic_loop(self.loop)

        # Connection and auto-reconnect loop
        while self.is_running:
            try:
                await self._connect_and_listen()
            except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as exc:
                logger.warning(f"Connection to Cloud Brain lost: {exc}. Retrying in {self.reconnect_interval}s...")
            except Exception as exc:
                logger.error(f"Unexpected worker error: {exc}. Retrying in {self.reconnect_interval}s...")

            await asyncio.sleep(self.reconnect_interval)


def main():
    parser = argparse.ArgumentParser(description="Brahma Echo Local Laptop Task Worker")
    parser.add_argument("--server", help="Cloud WebSocket URL (e.g. ws://127.0.0.1:8000/ws/node)")
    parser.add_argument("--token", help="Auth token for Cloud Brain")
    parser.add_argument("--name", help="Device name for this laptop")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio mic/speaker streaming")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless worker mode")
    args = parser.parse_args()

    cfg = load_config()
    if args.server:
        cfg["cloud_server_url"] = args.server
    if args.token:
        cfg["auth_token"] = args.token
    if args.name:
        cfg["device_name"] = args.name
    if args.no_audio:
        cfg["enable_audio"] = False

    logger.info("==========================================================================")
    logger.info("       BRAHMA ECHO — LOCAL LAPTOP TASK WORKER NODE")
    logger.info(f"       Device Name : {cfg['device_name']}")
    logger.info(f"       Target Cloud: {cfg['cloud_server_url']}")
    logger.info("==========================================================================")

    worker = LaptopWorker(cfg, headless=args.headless)
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("\nShutting down Laptop Worker...")


if __name__ == "__main__":
    main()
