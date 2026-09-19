"""
cloud_server.py — Brahma Cloud Server & Voice Engine Entry Point

Run this on your Cloud Server / VPS / Docker container.
Exposes WebSocket endpoints for laptop nodes and clients, manages the Gemini
Multimodal Live conversational loop, and routes desktop execution to laptops.

Usage:
    python cloud_server.py [--host 0.0.0.0] [--port 8000] [--token YOUR_SECRET_TOKEN]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import qrcode
import uvicorn
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from core.distributed.protocol import (
    ProtocolTypes,
    MessageEnvelope,
    build_message,
    parse_message,
    new_request_id,
)
from brahma_connect.gateway.protocol import now_iso
from cloud.cloud_brain import CloudBrain, RemoteToolDispatcher
from cloud.cloud_scheduler import CloudScheduler
from memory.memory_manager import load_memory, update_memory, forget
from memory.supabase_memory import is_supabase_configured

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("CloudServer")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "cloud_config.json"


def load_server_config() -> Dict[str, Any]:
    default_cfg = {
        "host": "0.0.0.0",
        "port": 8000,
        "auth_token": "brahma_secret_cloud_token_2026",
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_cfg.update(cfg)
        except Exception as e:
            logger.warning(f"Failed to read {CONFIG_PATH}: {e}")
    if env_token := os.environ.get("BRAHMA_CLOUD_TOKEN"):
        default_cfg["auth_token"] = env_token.strip()
    return default_cfg


class WebSocketToolDispatcher(RemoteToolDispatcher):
    """Dispatches tool execution requests across the WebSocket connection to the laptop."""

    def __init__(self):
        self.laptop_ws: Optional[WebSocket] = None
        self.laptop_info: Dict[str, Any] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}

    @property
    def is_connected(self) -> bool:
        return self.laptop_ws is not None

    def register_laptop(self, ws: WebSocket, info: Dict[str, Any]):
        self.laptop_ws = ws
        self.laptop_info = info
        logger.info(f"Registered laptop worker: {info.get('device_name', 'Unknown')}")

    def unregister_laptop(self):
        logger.info("Laptop worker disconnected.")
        self.laptop_ws = None
        self.laptop_info = {}
        # Cancel any pending requests
        for req_id, future in list(self.pending_requests.items()):
            if not future.done():
                future.set_exception(ConnectionResetError("Laptop worker disconnected"))
        self.pending_requests.clear()

    async def execute_on_laptop(self, tool_name: str, args: Dict[str, Any], timeout: float = 60.0) -> Dict[str, Any]:
        if not self.is_connected:
            return {
                "success": False,
                "result": None,
                "error": "Laptop task worker is currently offline. Please ensure your laptop app is running.",
            }

        # Allow long-running multi-step tools enough time to complete without premature timeouts
        if tool_name in {"autonomous_operator", "website_builder", "dev_agent"}:
            timeout = max(timeout, 180.0)

        req_id = new_request_id()
        msg = build_message(
            ProtocolTypes.EXECUTE_TOOL,
            payload={"tool_name": tool_name, "args": args},
            request_id=req_id,
        )

        future = asyncio.get_event_loop().create_future()
        self.pending_requests[req_id] = future

        try:
            await self.laptop_ws.send_text(msg.to_json())
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {
                "success": False,
                "result": None,
                "error": f"Timed out waiting for laptop to execute '{tool_name}'.",
            }
        except Exception as exc:
            return {
                "success": False,
                "result": None,
                "error": f"RPC Error: {exc}",
            }
        finally:
            self.pending_requests.pop(req_id, None)

    def handle_tool_result(self, req_id: str, payload: Dict[str, Any]):
        if req_id in self.pending_requests:
            future = self.pending_requests[req_id]
            if not future.done():
                future.set_result(payload)


app = FastAPI(title="JARVIS Cloud Brain", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def head_request_middleware(request: Request, call_next):
    """
    Ensures uptime monitors (e.g. UptimeRobot) sending HEAD requests across any route
    receive standard 200 OK responses with empty bodies rather than 405 Method Not Allowed.
    """
    is_head = request.method == "HEAD"
    if is_head:
        request.scope["method"] = "GET"
    response = await call_next(request)
    if is_head:
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=b"",
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
    return response

class CloudPhoneHub:
    """
    Direct Cloud Gateway for Android Companion App.
    Enables ARYA to connect directly to the user's phone over WSS (no laptop mediator).
    """

    def __init__(self):
        self.phone_ws: Optional[WebSocket] = None
        self.phone_info: Dict[str, Any] = {}
        self.active_calls: Dict[str, Dict[str, Any]] = {}
        self.pairing_offers: Dict[str, Dict[str, Any]] = {}
        self.device_secret: str = self._load_or_create_device_secret()
        self.device_id: str = "android_companion_primary"
        from cloud.cloud_daily_briefing import load_phone_location
        self.phone_location: Dict[str, Any] = load_phone_location()
        self.last_first_call_date_ist: str = self._load_last_first_call_date()
        self.call_event_handlers: List[Callable[[str, Dict[str, Any]], Any]] = []
        self.pending_commands: Dict[str, asyncio.Future] = {}

    def _load_last_first_call_date(self) -> str:
        date_file = BASE_DIR / "config" / "last_first_call_date.txt"
        if date_file.exists():
            try:
                return date_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return ""

    def mark_first_call_done(self, date_ist_str: str) -> None:
        self.last_first_call_date_ist = date_ist_str
        date_file = BASE_DIR / "config" / "last_first_call_date.txt"
        try:
            date_file.parent.mkdir(parents=True, exist_ok=True)
            date_file.write_text(date_ist_str, encoding="utf-8")
        except Exception:
            pass

    def _load_or_create_device_secret(self) -> str:
        secret_file = BASE_DIR / "config" / "phone_device_secret.txt"
        if secret_file.exists():
            try:
                sec = secret_file.read_text(encoding="utf-8").strip()
                if sec:
                    return sec
            except Exception:
                pass
        if env_secret := os.environ.get("BRAHMA_PHONE_SECRET"):
            sec = env_secret.strip()
            try:
                secret_file.parent.mkdir(parents=True, exist_ok=True)
                secret_file.write_text(sec, encoding="utf-8")
            except Exception:
                pass
            return sec
        new_sec = secrets.token_hex(24)
        try:
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            secret_file.write_text(new_sec, encoding="utf-8")
        except Exception:
            pass
        return new_sec

    @property
    def is_connected(self) -> bool:
        return self.phone_ws is not None

    def create_pairing_offer(self, host: str = "brahma-cloud-brain.onrender.com") -> Dict[str, Any]:
        token = secrets.token_hex(16)
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = time.time()
        is_local = "127.0.0.1" in host or "localhost" in host
        scheme = "ws" if is_local else "wss"
        port = 8000 if is_local else 443
        offer = {
            "service": "BrahmaCloud",
            "url": f"{scheme}://{host}/ws/phone",
            "host": host,
            "port": port,
            "ssl": not is_local,
            "path": "/ws/phone",
            "pairing_token": token,
            "pairing_code": code,
            "expires": 600,
            "created_at": now_iso(),
        }
        self.pairing_offers[token] = offer
        self.pairing_offers[code] = offer
        return offer

    def generate_qr_data_url(self, host: str = "brahma-cloud-brain.onrender.com") -> str:
        offer = self.create_pairing_offer(host)
        payload_str = json.dumps(offer)
        try:
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(payload_str)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            logger.warning(f"Failed to generate Phone QR code: {e}")
            return ""

    def register_phone(self, ws: WebSocket, info: Dict[str, Any]):
        self.phone_ws = ws
        self.phone_info = dict(info or {})
        self.phone_info["connected_at"] = time.time()
        logger.info(f"📱 Phone connected directly to Cloud Server: {self.phone_info.get('name', 'Android Phone')}")

    def unregister_phone(self, ws: Optional[WebSocket] = None):
        if ws is not None and self.phone_ws is not ws:
            logger.info("📱 Ignoring unregister from stale phone WebSocket connection.")
            return
        logger.info("📱 Phone disconnected from Cloud Server.")
        self.phone_ws = None
        self.phone_info = {}
        self.active_calls.clear()
        for req_id, fut in list(self.pending_commands.items()):
            if not fut.done():
                fut.set_result({"success": False, "error": "Phone disconnected while executing command", "error_code": "PHONE_DISCONNECTED"})
        self.pending_commands.clear()

    async def execute_phone_command(self, action: str, parameters: Optional[Dict[str, Any]] = None, timeout: float = 25.0) -> Dict[str, Any]:
        """
        Sends an execution command to the connected phone and awaits the result asynchronously.
        """
        if not self.is_connected or not self.phone_ws:
            return {
                "success": False,
                "error": "Phone is currently disconnected from Brahma Cloud Brain. Please ensure Brahma Connect is running on your phone.",
                "error_code": "PHONE_DISCONNECTED"
            }

        req_id = new_request_id()
        msg = {
            "type": "command_request",
            "request_id": req_id,
            "timestamp": now_iso(),
            "payload": {
                "action": action,
                "parameters": parameters or {}
            }
        }

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self.pending_commands[req_id] = future

        try:
            await self.phone_ws.send_text(json.dumps(msg))
            logger.info(f"📱 Dispatched command '{action}' to phone (request_id={req_id})")
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"📱 Command '{action}' timed out after {timeout}s (request_id={req_id})")
            return {
                "success": False,
                "error": f"Command '{action}' timed out waiting for phone response after {timeout} seconds.",
                "error_code": "TIMEOUT"
            }
        except Exception as e:
            logger.error(f"📱 Error executing command '{action}': {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "EXECUTION_ERROR"
            }
        finally:
            self.pending_commands.pop(req_id, None)

    async def call_phone(self, caller_name: str = "JARVIS", reason: str = "Voice call from JARVIS") -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "error": "Phone is not connected directly to the cloud server."}

        call_id = new_request_id()
        msg = {
            "type": "call_offer",
            "request_id": call_id,
            "timestamp": now_iso(),
            "payload": {
                "call_id": call_id,
                "caller_name": caller_name,
                "reason": reason,
            },
        }
        try:
            await self.phone_ws.send_text(json.dumps(msg))
            self.active_calls[call_id] = {
                "call_id": call_id,
                "caller": caller_name,
                "reason": reason,
                "status": "ringing",
                "started_at": time.time(),
            }
            logger.info(f"📞 CALL_OFFER sent directly to phone for '{reason}' (call_id={call_id})")
            return {"success": True, "call_id": call_id}
        except Exception as exc:
            logger.error(f"Failed to send call_offer: {exc}")
            return {"success": False, "error": str(exc)}

    def register_call_event_handler(self, handler: Callable[[str, Dict[str, Any]], Any]):
        """Registers a callback for phone call events ('call_unanswered', 'call_declined')."""
        self.call_event_handlers.append(handler)

    def _emit_call_event(self, event_type: str, call_data: Dict[str, Any]):
        for handler in list(self.call_event_handlers):
            try:
                res = handler(event_type, call_data)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as e:
                logger.error(f"Error in call event handler: {e}")

    async def check_ringing_timeouts(self):
        """Monitors active ringing calls. If a call rings > 35s without being answered, triggers timeout & alert."""
        now = time.time()
        for call_id, call_info in list(self.active_calls.items()):
            if call_info.get("status") == "ringing":
                started = call_info.get("started_at", now)
                if now - started > 35.0:
                    logger.warning(f"📞 Android call {call_id} timed out without answer after {int(now - started)}s.")
                    self.active_calls.pop(call_id, None)
                    if self.is_connected:
                        try:
                            msg = {
                                "type": "call_end",
                                "request_id": new_request_id(),
                                "timestamp": now_iso(),
                                "payload": {"call_id": call_id, "reason": "timeout"},
                            }
                            await self.phone_ws.send_text(json.dumps(msg))
                        except Exception:
                            pass
                    self._emit_call_event("call_unanswered", call_info)
                    broadcast_phone_status_to_web()

    async def end_call(self, call_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = call_id
        if not target_id and self.active_calls:
            target_id = next(iter(self.active_calls.keys()))
        if not target_id:
            return {"success": True}

        self.active_calls.pop(target_id, None)
        if self.is_connected:
            try:
                msg = {
                    "type": "call_end",
                    "request_id": new_request_id(),
                    "timestamp": now_iso(),
                    "payload": {"call_id": target_id},
                }
                await self.phone_ws.send_text(json.dumps(msg))
            except Exception:
                pass
        return {"success": True}

    async def forward_audio_to_phone(self, b64_pcm: str):
        if not self.is_connected or not self.active_calls:
            return
        active_call = next((cid for cid, c in self.active_calls.items() if c.get("status") == "active"), None)
        if not active_call and self.active_calls:
            active_call = next(iter(self.active_calls.keys()))
        if not active_call:
            return
        msg = {
            "type": "call_audio",
            "request_id": new_request_id(),
            "timestamp": now_iso(),
            "payload": {"call_id": active_call, "data": b64_pcm},
        }
        try:
            await self.phone_ws.send_text(json.dumps(msg))
        except Exception:
            pass

    async def notify_turn_complete(self):
        """Notifies active phone call that ARYA finished speaking so phone mic re-arms immediately."""
        if not self.is_connected or not self.active_calls:
            return
        active_call = next((cid for cid, c in self.active_calls.items() if c.get("status") == "active"), None)
        if not active_call and self.active_calls:
            active_call = next(iter(self.active_calls.keys()))
        if not active_call:
            return
        msg = {
            "type": "call_turn_complete",
            "request_id": new_request_id(),
            "timestamp": now_iso(),
            "payload": {"call_id": active_call},
        }
        try:
            await self.phone_ws.send_text(json.dumps(msg))
        except Exception:
            pass


dispatcher = WebSocketToolDispatcher()
phone_hub = CloudPhoneHub()
scheduler = CloudScheduler()
brain: Optional[CloudBrain] = None
server_config = load_server_config()
web_clients: set[WebSocket] = set()


def broadcast_audio_to_web(pcm_chunk: bytes):
    """Sends synthesized 24kHz audio from Gemini Live directly to connected browser clients and active phone calls."""
    b64_data = base64.b64encode(pcm_chunk).decode("ascii")
    if phone_hub.is_connected and phone_hub.active_calls:
        asyncio.create_task(phone_hub.forward_audio_to_phone(b64_data))
    if not web_clients:
        return
    payload = json.dumps({"type": "audio_chunk", "data": b64_data})
    for client in list(web_clients):
        try:
            asyncio.create_task(client.send_text(payload))
        except Exception:
            pass


def broadcast_transcript_to_web(role: str, text: str):
    """Broadcasts user and assistant transcripts to connected browser clients."""
    payload = json.dumps({"type": "transcript", "role": role, "text": text})
    for client in list(web_clients):
        try:
            asyncio.create_task(client.send_text(payload))
        except Exception:
            pass


def broadcast_turn_complete_to_web():
    """Broadcasts turn_complete event to browser clients and active phone calls so they know when AI speech ends."""
    if phone_hub.is_connected and phone_hub.active_calls:
        asyncio.create_task(phone_hub.notify_turn_complete())
    if not web_clients:
        return
    payload = json.dumps({"type": "turn_complete"})
    for client in list(web_clients):
        try:
            asyncio.create_task(client.send_text(payload))
        except Exception:
            pass


def broadcast_phone_status_to_web():
    """Broadcasts phone connection and call status to all connected web clients."""
    info = {
        "type": "phone_status",
        "connected": phone_hub.is_connected,
        "phone_info": phone_hub.phone_info if phone_hub.is_connected else None,
        "active_call": next(iter(phone_hub.active_calls.values()), None) if phone_hub.active_calls else None,
    }
    msg = json.dumps(info)
    for client in list(web_clients):
        try:
            asyncio.create_task(client.send_text(msg))
        except Exception:
            pass


main_loop: Optional[asyncio.AbstractEventLoop] = None


def broadcast_whatsapp_event(event_type: str, payload: Any):
    """Broadcasts real-time WhatsApp events (status, qr, messages) to browser clients and triggers urgent alert calls."""
    global main_loop
    msg = json.dumps({"type": event_type, "data": payload})
    for client in list(web_clients):
        try:
            if main_loop and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(client.send_text(msg), main_loop)
            else:
                asyncio.create_task(client.send_text(msg))
        except Exception:
            pass

    # High Urgency Check: Trigger proactive call for critical WhatsApp messages
    if event_type in ("whatsapp_message", "message") and isinstance(payload, dict):
        sender = payload.get("sender") or payload.get("push_name") or "WhatsApp contact"
        text = payload.get("text") or payload.get("body") or ""
        phone_online = phone_hub.is_connected if phone_hub else False
        logger.info(
            f"🔍 Checking WhatsApp urgency for message from '{sender}': '{text[:60]}' "
            f"(phone_hub_connected={phone_online})"
        )
        if text and phone_hub:
            coro = scheduler.check_urgent_message_alert(phone_hub, sender, text)
            if main_loop and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, main_loop)
            else:
                asyncio.create_task(coro)


def on_phone_call_event(event_type: str, call_data: Dict[str, Any]):
    """Handles phone call status changes (unanswered, declined) for Telegram alert failover."""
    reason = call_data.get("reason", "Voice call from JARVIS")
    from cloud.cloud_daily_briefing import get_now_ist
    time_str = get_now_ist().strftime("%I:%M %p IST")

    try:
        from telegram_bot import TelegramBotService
        tg = TelegramBotService.get_instance()
        if not tg.is_running() and not tg.chat_id:
            return

        if event_type == "call_unanswered":
            msg = (
                f"📞 **Missed Call from JARVIS**\n\n"
                f"Boss, I placed a voice call to your phone at {time_str}, but you didn't receive the call.\n\n"
                f"📌 **Call Purpose / Reminder**:\n_{reason}_\n\n"
                f"💬 _You can chat with me here anytime or use my tools!_"
            )
            tg.send_notification(msg)
        elif event_type == "call_declined":
            msg = (
                f"📞 **Call Declined Alert**\n\n"
                f"Boss, you declined my call at {time_str}.\n\n"
                f"📌 **Topic was**:\n_{reason}_\n\n"
                f"I have sent this note here so you don't miss anything."
            )
            tg.send_notification(msg)
    except Exception as ex:
        logger.error(f"Error sending Telegram call failover alert: {ex}")


def on_scheduler_failover(event_type: str, reminder: Dict[str, Any], details: str):
    """Handles scheduler failover (phone offline or busy) for Telegram alert failover."""
    reason = reminder.get("reason", "Scheduled reminder")
    target_time = reminder.get("target_time_display", "Now")

    try:
        from telegram_bot import TelegramBotService
        tg = TelegramBotService.get_instance()
        if not tg.is_running() and not tg.chat_id:
            return

        msg = (
            f"⏰ **Scheduled Reminder (Call Fallback)**\n\n"
            f"Boss, your scheduled reminder is due ({target_time}), but I couldn't reach your phone ({details}).\n\n"
            f"📌 **Reminder**: *{reason}*\n\n"
            f"💬 _Text me here if you'd like me to reschedule or help with anything!_"
        )
        tg.send_notification(msg)
    except Exception as ex:
        logger.error(f"Error sending Telegram scheduler failover alert: {ex}")


@app.on_event("startup")
async def on_startup():
    global brain, main_loop
    main_loop = asyncio.get_running_loop()
    logger.info("Initializing JARVIS Cloud Brain...")
    brain = CloudBrain(
        tool_dispatcher=dispatcher,
        phone_hub=phone_hub,
        scheduler=scheduler,
        on_audio_out=broadcast_audio_to_web,
        on_transcript=broadcast_transcript_to_web,
        on_turn_complete=broadcast_turn_complete_to_web,
        on_log=lambda msg: logger.info(f"[Brain] {msg}"),
    )
    # Start Gemini Live background loop
    asyncio.create_task(brain.run())

    # Start Cloud Scheduler 24/7 background loop
    asyncio.create_task(scheduler.start_loop(phone_hub, brain))

    # Register failover and call status callbacks
    scheduler.register_failover_handler(on_scheduler_failover)
    phone_hub.register_call_event_handler(on_phone_call_event)

    # Start Telegram Bot Service
    try:
        from telegram_bot import TelegramBotService, load_telegram_config
        telegram_bot = TelegramBotService.get_instance()

        async def _telegram_command_bridge(user_text: str) -> Optional[str]:
            if not brain or not brain.is_running:
                return None
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    brain.handle_text_command(user_text, wait_for_response=True, timeout=25.0),
                    main_loop
                )
                return await asyncio.wrap_future(fut)
            except Exception as bridge_err:
                logger.warning(f"Telegram-to-CloudBrain bridge error: {bridge_err}")
                return None

        telegram_bot.bind_command_handler(_telegram_command_bridge)
        tg_cfg = load_telegram_config()
        if tg_cfg.get("enabled", True) and (tg_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")):
            telegram_bot.start()
            logger.info("🤖 Telegram Bot Service started on cloud server.")
        else:
            logger.info("ℹ️ Telegram Bot token not configured yet. Configure via config/telegram_config.json or POST /api/telegram/config.")
    except Exception as tg_err:
        logger.warning(f"Could not start Telegram Bot Service: {tg_err}")

    # Start WhatsApp Gateway
    try:
        from cloud.whatsapp_gateway import WhatsAppGateway
        whatsapp_gw = WhatsAppGateway.get_instance()
        whatsapp_gw.add_listener(broadcast_whatsapp_event)
        whatsapp_gw.start()
    except Exception as wa_err:
        logger.warning(f"Could not start WhatsApp Gateway: {wa_err}")



@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def get_web_ui():
    """Serves the browser-based Web Voice & Task interface."""
    ui_path = BASE_DIR / "cloud" / "web_ui.html"
    if ui_path.exists():
        return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>JARVIS Cloud Brain Online</h1><p>Visit /api/status for JSON health metrics.</p>")


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check():
    """
    Lightweight health check endpoint specifically designed for uptime monitors (e.g. UptimeRobot)
    to keep the Render container alive 24/7. Responds to both GET and HEAD requests with 200 OK.
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "online": True,
            "service": "JARVIS Cloud Brain",
            "gemini_live_connected": brain.session is not None if brain else False,
            "laptop_connected": dispatcher.is_connected,
        },
        status_code=200,
    )


@app.api_route("/api/status", methods=["GET", "HEAD"])
async def get_status():
    """System health check and connection status."""
    return {
        "status": "online",
        "gemini_live_connected": brain.session is not None if brain else False,
        "laptop_connected": dispatcher.is_connected,
        "laptop_info": dispatcher.laptop_info if dispatcher.is_connected else None,
        "active_rpc_requests": len(dispatcher.pending_requests),
    }


@app.post("/api/command")
async def post_command(data: Dict[str, Any]):
    """Inject a text command into the Cloud Brain and return the assistant response."""
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text' field.")
    if not brain:
        raise HTTPException(status_code=503, detail="Brain not ready.")
    reply = await brain.handle_text_command(text, wait_for_response=True, timeout=20.0)
    return {"status": "success", "text": text, "reply": reply or "Done."}


@app.get("/api/memories")
async def get_memories():
    """Retrieve all structured memories."""
    return {
        "supabase_connected": is_supabase_configured(),
        "memories": load_memory(),
    }


@app.post("/api/memories")
async def save_user_memory(data: Dict[str, Any]):
    """Manually add or update a memory fact."""
    category = data.get("category", "notes")
    key = data.get("key", "").strip()
    value = data.get("value", "").strip()
    if not key or not value:
        raise HTTPException(status_code=400, detail="Missing key or value.")
    update_memory({category: {key: {"value": value}}})
    return {"status": "success", "category": category, "key": key, "value": value}


@app.delete("/api/memories")
async def delete_user_memory(category: str, key: str):
    """Delete a memory fact."""
    if not key or not category:
        raise HTTPException(status_code=400, detail="Missing category or key.")
    res = forget(key, category)
    return {"status": "success", "result": res}


# =========================================================================
# WhatsApp Multi-Device Gateway REST Endpoints
# =========================================================================

@app.get("/api/whatsapp/status")
async def get_whatsapp_status():
    """Returns the current connection status of the WhatsApp companion node."""
    from cloud.whatsapp_gateway import WhatsAppGateway
    return WhatsAppGateway.get_instance().get_status()


@app.get("/api/whatsapp/qr")
async def get_whatsapp_qr():
    """Returns the latest WhatsApp Web pairing QR code, auto-restarting if disconnected."""
    from cloud.whatsapp_gateway import WhatsAppGateway
    gw = WhatsAppGateway.get_instance()
    if (gw.status == "disconnected" or not gw.qr_data_url) and not gw.is_connected:
        gw.restart()
        await asyncio.sleep(1.2)
    return {"qr_data_url": gw.qr_data_url, "status": gw.status}


@app.post("/api/whatsapp/refresh-qr")
async def refresh_whatsapp_qr():
    """Forces generation of a brand new pairing QR code."""
    from cloud.whatsapp_gateway import WhatsAppGateway
    gw = WhatsAppGateway.get_instance()
    gw.restart()
    await asyncio.sleep(1.5)
    return {"success": True, "qr_data_url": gw.qr_data_url, "status": gw.status}


@app.post("/api/whatsapp/pair-phone")
async def pair_whatsapp_phone(data: Dict[str, Any]):
    """Requests an 8-character pairing code for linking via phone number."""
    phone = data.get("phone", "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Missing 'phone' field.")
    from cloud.whatsapp_gateway import WhatsAppGateway
    gw = WhatsAppGateway.get_instance()
    res = gw.request_phone_pairing_code(phone)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to generate pairing code."))
    return res


@app.post("/api/whatsapp/send")
async def send_whatsapp_message(data: Dict[str, Any]):
    """Sends a text message, image, or document through WhatsApp."""
    recipient = data.get("recipient", "").strip()
    message = data.get("message", "").strip()
    file_path = data.get("file_path", "").strip()
    media_type = data.get("media_type", "document")
    if not recipient or (not message and not file_path):
        raise HTTPException(status_code=400, detail="Missing recipient or message/file.")

    from cloud.whatsapp_gateway import WhatsAppGateway
    gw = WhatsAppGateway.get_instance()
    if file_path:
        res = gw.send_media(recipient, file_path, caption=message, media_type=media_type)
    else:
        res = gw.send_text(recipient, message)
    return res


@app.post("/api/whatsapp/mode")
async def set_whatsapp_mode(data: Dict[str, Any]):
    """Sets conversational mode ('notify_only', 'whitelist', 'auto_pilot')."""
    mode = data.get("mode", "notify_only")
    from cloud.whatsapp_gateway import WhatsAppGateway
    return WhatsAppGateway.get_instance().set_mode(mode)


@app.get("/api/whatsapp/chats")
async def get_whatsapp_chats():
    """Returns recent incoming and outgoing WhatsApp messages."""
    from cloud.whatsapp_gateway import WhatsAppGateway
    return {"chats": WhatsAppGateway.get_instance().recent_chats}


@app.post("/api/whatsapp/whitelist")
async def update_whatsapp_whitelist(data: Dict[str, Any]):
    """Add or remove a contact phone number from the VIP auto-reply whitelist."""
    phone = data.get("phone", "").strip()
    action = data.get("action", "add")
    from cloud.whatsapp_gateway import WhatsAppGateway
    return WhatsAppGateway.get_instance().update_whitelist(phone, action)


@app.post("/api/whatsapp/disconnect")
async def disconnect_whatsapp():
    """Disconnects or resets the WhatsApp companion session."""
    from cloud.whatsapp_gateway import WhatsAppGateway
    return WhatsAppGateway.get_instance().disconnect()


# =========================================================================
# Telegram Bot REST Endpoints
# =========================================================================

@app.get("/api/telegram/status")
async def get_telegram_status():
    """Returns the online, pairing, and username status of the Telegram Bot."""
    from telegram_bot import TelegramBotService, load_telegram_config
    tg = TelegramBotService.get_instance()
    cfg = load_telegram_config()
    return {
        "running": tg.is_running(),
        "bot_username": tg.bot_username,
        "chat_id": tg.chat_id,
        "has_token": bool(tg.bot_token),
        "owner_name": cfg.get("owner_name", ""),
    }


@app.post("/api/telegram/config")
async def save_telegram_configuration(data: Dict[str, Any]):
    """Configures bot token and enabled state, auto-(re)starting if valid token is provided."""
    from telegram_bot import TelegramBotService, save_telegram_config
    bot_token = (data.get("bot_token") or "").strip()
    chat_id = str(data.get("chat_id") or "").strip()
    enabled = bool(data.get("enabled", True))
    updates: Dict[str, Any] = {"enabled": enabled}
    if bot_token:
        updates["bot_token"] = bot_token
    if chat_id:
        updates["chat_id"] = chat_id
    save_telegram_config(updates)

    tg = TelegramBotService.get_instance()
    if enabled and (bot_token or tg.bot_token):
        tg.stop()
        tg.start(bot_token or tg.bot_token)
    elif not enabled:
        tg.stop()
    return {"status": "success", "running": tg.is_running(), "chat_id": tg.chat_id}


@app.post("/api/telegram/send")
async def send_telegram_notification_api(data: Dict[str, Any]):
    """Sends a direct message or reminder notification to the user via Telegram."""
    message = (data.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Missing 'message' parameter.")
    from telegram_bot import TelegramBotService
    tg = TelegramBotService.get_instance()
    chat_id = data.get("chat_id")
    success = tg.send_notification(message, chat_id=chat_id)
    return {"status": "success" if success else "failed", "sent": success}


# =========================================================================
# Server-Side Live Utility Tool REST Endpoints (Open-Meteo, Nominatim, etc.)
# =========================================================================

@app.get("/api/utility/weather")
async def api_get_weather(location: str = "Mumbai", lat: Optional[float] = None, lon: Optional[float] = None):
    """Direct REST endpoint to test Open-Meteo & Nominatim weather."""
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool("get_weather", {"location": location, "lat": lat, "lon": lon})


@app.get("/api/utility/currency")
async def api_convert_currency(amount: float = 1.0, from_curr: str = "USD", to_curr: str = "INR"):
    """Direct REST endpoint to test Frankfurter currency conversion."""
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool("convert_currency", {"amount": amount, "from_currency": from_curr, "to_currency": to_curr})


@app.get("/api/utility/wiki")
async def api_get_wiki(query: str = "Artificial intelligence"):
    """Direct REST endpoint to test Wikipedia REST API summaries."""
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool("wikipedia_summary", {"query": query})


@app.get("/api/utility/joke")
async def api_get_joke(category: str = "Programming,Miscellaneous"):
    """Direct REST endpoint to test JokeAPI safe jokes."""
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool("get_joke", {"category": category})


@app.get("/api/utility/advice")
async def api_get_advice(topic: Optional[str] = None):
    """Direct REST endpoint to test Advice Slip API."""
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool("get_advice", {"topic": topic})


@app.get("/api/utility/shorten")
async def api_shorten_url(url: str):
    """Direct REST endpoint to test TinyURL link shortening."""
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool("shorten_url", {"url": url})


@app.get("/api/utility/chart")
async def api_generate_chart(
    chart_type: str = "bar",
    labels: str = "Jan,Feb,Mar,Apr",
    data: str = "10,25,15,30",
    title: str = "Sample Metric",
):
    """Direct REST endpoint to test QuickChart visualization."""
    from cloud.cloud_utilities import execute_utility_tool
    label_list = [item.strip() for item in labels.split(",") if item.strip()]
    data_list = []
    for d in data.split(","):
        try:
            data_list.append(float(d.strip()))
        except ValueError:
            pass
    return await execute_utility_tool("generate_chart", {
        "chart_type": chart_type,
        "labels": label_list,
        "data": data_list,
        "title": title,
    })


@app.post("/api/utility/execute")
async def api_execute_utility(payload: Dict[str, Any]):
    """Generic execution endpoint for any of the 8 utilities."""
    tool_name = payload.get("tool")
    args = payload.get("args", {})
    if not tool_name:
        raise HTTPException(status_code=400, detail="Missing 'tool' parameter.")
    from cloud.cloud_utilities import execute_utility_tool
    return await execute_utility_tool(tool_name, args)


# =========================================================================
# Productivity Tool Endpoints: News, Calendar, Gmail, Todoist
# =========================================================================

@app.get("/api/news")
async def api_get_news(query: Optional[str] = None, category: Optional[str] = None, limit: int = 5):
    """Direct REST endpoint to fetch news headlines."""
    from cloud.news_service import get_news_headlines
    return await get_news_headlines(query=query, category=category, max_results=limit)


@app.get("/api/calendar/events")
async def api_get_calendar_events(max_results: int = 10):
    """Direct REST endpoint to list upcoming Google Calendar events."""
    from cloud.google_workspace import execute_calendar_tool
    return await execute_calendar_tool("list_events", {"max_results": max_results})


@app.post("/api/calendar/create")
async def api_create_calendar_event(payload: Dict[str, Any]):
    """Direct REST endpoint to create a Google Calendar event."""
    from cloud.google_workspace import execute_calendar_tool
    return await execute_calendar_tool("create_event", payload)


@app.get("/api/gmail/emails")
async def api_get_gmail_emails(query: str = "is:unread", limit: int = 5):
    """Direct REST endpoint to list/search Gmail messages."""
    from cloud.google_workspace import execute_gmail_tool
    return await execute_gmail_tool("list_emails", {"query": query, "max_results": limit})


@app.post("/api/gmail/send")
async def api_send_gmail_email(payload: Dict[str, Any]):
    """Direct REST endpoint to send an email via Gmail."""
    from cloud.google_workspace import execute_gmail_tool
    return await execute_gmail_tool("send_email", payload)


@app.get("/api/todoist/tasks")
async def api_get_todoist_tasks(filter: Optional[str] = None):
    """Direct REST endpoint to list active Todoist tasks."""
    from cloud.todoist_service import execute_todoist_tool
    return await execute_todoist_tool("list_tasks", {"filter": filter})


@app.post("/api/todoist/create")
async def api_create_todoist_task(payload: Dict[str, Any]):
    """Direct REST endpoint to create a Todoist task."""
    from cloud.todoist_service import execute_todoist_tool
    return await execute_todoist_tool("add_task", payload)


# =========================================================================
# Android Phone Companion Direct Cloud Endpoints (No Laptop Required)
# =========================================================================

@app.get("/api/phone/status")
async def get_phone_status():
    """Returns the direct connection and active call status of the Android Phone Companion."""
    return {
        "connected": phone_hub.is_connected,
        "phone_info": phone_hub.phone_info if phone_hub.is_connected else None,
        "active_calls": list(phone_hub.active_calls.values()),
    }


@app.get("/api/phone/qr")
async def get_phone_qr(request: Request):
    """Generates a dynamic QR code for pairing the Android app directly with this Cloud Server."""
    host = request.headers.get("host", "brahma-cloud-brain.onrender.com")
    qr_data = phone_hub.generate_qr_data_url(host)
    return {
        "success": True,
        "qr_data_url": qr_data,
        "host": host,
        "connected": phone_hub.is_connected,
    }


@app.post("/api/phone/call")
async def api_trigger_phone_call(data: Dict[str, Any] | None = None):
    """Triggers an incoming VoIP phone call directly from the Cloud Brain to the Android Phone."""
    params = data or {}
    caller = str(params.get("caller") or "ARYA").strip()
    reason = str(params.get("reason") or "Voice Call from ARYA Web AI").strip()
    return await phone_hub.call_phone(caller_name=caller, reason=reason)


@app.post("/api/phone/command")
async def api_trigger_phone_command(data: Dict[str, Any] | None = None):
    """
    Executes an action directly on the connected phone (see_screen, smart_ui_click, send_whatsapp, etc.).
    """
    params = data or {}
    action = str(params.get("action", "")).strip()
    parameters = params.get("parameters", {})
    if not action:
        raise HTTPException(status_code=400, detail="Missing 'action' parameter.")
    return await phone_hub.execute_phone_command(action, parameters)


async def trigger_call_greeting(reason: str):
    """
    Intelligently triggers the initial voice greeting when a phone call is connected:
    - If it's the FIRST CALL OF THE DAY: Delivers a full morning executive briefing
      (exact IST time, live weather for phone location, schedule, emails, WhatsApp, headlines).
    - On subsequent calls of the same day: Delivers a crisp, warm, natural ARYA greeting.
    """
    if not brain:
        return
    try:
        from cloud.cloud_daily_briefing import get_now_ist, compile_server_daily_briefing
        now_ist = get_now_ist()
        today_date_ist = now_ist.strftime("%Y-%m-%d")

        is_first_call = (phone_hub.last_first_call_date_ist != today_date_ist)
        if is_first_call:
            phone_hub.mark_first_call_done(today_date_ist)
            logger.info(f"🌅 First call of today ({today_date_ist}) detected! Compiling morning briefing...")
            briefing = await compile_server_daily_briefing(category="all")
            sched_str = ", ".join(briefing.get("schedule", [])) if briefing.get("schedule") else "No calendar meetings scheduled"
            email_info = briefing.get("emails", {})
            email_str = f"{email_info.get('count', 0)} unread emails" if email_info.get("has_unread") else "Inbox clean"
            wa_info = briefing.get("whatsapp", {})
            wa_str = wa_info.get("summary", "No pending messages")
            headline = briefing.get("headlines", ["All systems operational"])[0] if briefing.get("headlines") else "Systems green"

            greeting = (
                f"[FIRST CALL OF THE DAY - EXECUTIVE DAILY BRIEFING]\n"
                f"Today is {briefing['date']}, exact time is {briefing['time']}.\n"
                f"This is the boss's FIRST phone call of the day! Greet Abhay with supreme energy, poise, and warmth as JARVIS.\n"
                f"LANGUAGE & IDENTITY RULE: Speak in your natural, fluent Hindi / Hinglish as your primary language using your male identity ('मैं कर रहा हूँ', 'मैं बताता हूँ', 'करूँगा') with your 70% witty humor and charm.\n"
                f"Deliver his full executive briefing smoothly without skipping sections:\n"
                f"1. Warm daily greeting and exact IST time ({briefing['time']})\n"
                f"2. Local weather in {briefing['location']}: {briefing['weather']}\n"
                f"3. Today's schedule: {sched_str}\n"
                f"4. Communications: {email_str} | WhatsApp: {wa_str}\n"
                f"5. Top headline: {headline}\n\n"
                f"Spoken guide (Hindi):\n\"{briefing['narrative_hindi']}\"\n\n"
                f"Speak this in a natural, executive conversational Hindi tone, and conclude by asking how you can assist him today!"
            )
        else:
            time_str = now_ist.strftime("%I:%M %p IST")
            greeting = (
                f"[The user just called you directly from their Android phone (reason: '{reason}'). "
                f"Current IST time is {time_str}. Greet the boss warmly and naturally in Hindi as JARVIS (male AI co-pilot, 'नमस्ते बॉस, बताइए मैं आपकी क्या सेवा करूँ?'). "
                f"Match the user's language dynamically if they reply in English or Hindi!]"
            )

        await brain.handle_text_command(greeting)
    except Exception as gerr:
        logger.error(f"Error triggering call greeting: {gerr}")
        if brain:
            await brain.handle_text_command("[Voice call connected with user on phone. Greet the user warmly as JARVIS in Hindi with witty charm and ask how you can assist them!]")


@app.websocket("/ws/phone")
async def websocket_phone_companion(websocket: WebSocket):
    """
    Direct WebSocket connection for the Android Phone Companion App.
    Eliminates laptop mediator — connects phone directly to the Cloud Brain.
    """
    await websocket.accept()
    logger.info("📱 New incoming phone connection on /ws/phone")

    phone_registered = False
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")
            req_id = data.get("request_id", "")
            payload = data.get("payload", {})

            # 1. Hello / Discover
            if msg_type == "hello":
                reply = {
                    "type": "pair_request",
                    "request_id": req_id,
                    "timestamp": now_iso(),
                    "payload": {"message": "Please send pair_request with pairing_token or authenticate with credential."},
                }
                await websocket.send_text(json.dumps(reply))

            # 2. Pair Request
            elif msg_type == "pair_request":
                device_name = payload.get("device_name") or payload.get("name") or "Android Phone"
                reply = {
                    "type": "pair_approved",
                    "request_id": req_id,
                    "timestamp": now_iso(),
                    "payload": {
                        "device": {
                            "device_id": phone_hub.device_id,
                            "name": device_name,
                            "platform": "android",
                        },
                        "device_secret": phone_hub.device_secret,
                    },
                }
                await websocket.send_text(json.dumps(reply))
                logger.info(f"📱 Approved pairing request for device: {device_name}")

            # 3. Authenticate
            elif msg_type == "authenticate":
                device_name = payload.get("device_name") or payload.get("name") or "Android Phone"
                phone_hub.register_phone(websocket, payload)
                phone_registered = True
                reply = {
                    "type": "device_online",
                    "request_id": req_id,
                    "timestamp": now_iso(),
                    "payload": {"status": "online", "device_id": phone_hub.device_id},
                }
                await websocket.send_text(json.dumps(reply))
                broadcast_phone_status_to_web()

            # 3b. Phone Contacts Auto-Sync
            elif msg_type == "contacts_sync":
                contacts_list = payload.get("contacts", [])
                logger.info(f"📱 Received contacts_sync from phone with {len(contacts_list)} items")
                try:
                    from cloud.contacts_manager import get_contacts_manager
                    mgr = get_contacts_manager()
                    count = mgr.sync_phone_contacts(contacts_list)
                    reply = {
                        "type": "result",
                        "request_id": req_id,
                        "timestamp": now_iso(),
                        "payload": {"status": "ok", "synced_count": count},
                    }
                    await websocket.send_text(json.dumps(reply))
                except Exception as cex:
                    logger.error(f"Error processing contacts_sync: {cex}")

            # 3b. Phone Command Result / Error Response
            elif msg_type == "result":
                if req_id and req_id in phone_hub.pending_commands:
                    fut = phone_hub.pending_commands[req_id]
                    if not fut.done():
                        fut.set_result(payload)

            elif msg_type == "error":
                if req_id and req_id in phone_hub.pending_commands:
                    fut = phone_hub.pending_commands[req_id]
                    if not fut.done():
                        fut.set_result({"success": False, "error": payload.get("error", "Phone command failed")})

            # 3c. Phone Location Auto-Sync (GPS & Locality for accurate localized weather)
            elif msg_type == "location_sync":
                lat = payload.get("lat") or payload.get("latitude")
                lon = payload.get("lon") or payload.get("longitude")
                city = payload.get("city") or payload.get("locality", "")
                state = payload.get("state") or payload.get("admin_area", "")
                country = payload.get("country", "India")
                address = payload.get("address", "")
                logger.info(f"📍 Received location_sync from phone: city='{city}', lat={lat}, lon={lon}")
                try:
                    from cloud.cloud_daily_briefing import save_phone_location
                    loc_info = {
                        "lat": float(lat) if lat is not None else None,
                        "lon": float(lon) if lon is not None else None,
                        "city": str(city).strip(),
                        "state": str(state).strip(),
                        "country": str(country).strip(),
                        "address": str(address).strip(),
                        "updated_at": now_iso(),
                    }
                    phone_hub.phone_location = loc_info
                    save_phone_location(loc_info)
                    reply = {
                        "type": "result",
                        "request_id": req_id,
                        "timestamp": now_iso(),
                        "payload": {"status": "ok", "location": loc_info},
                    }
                    await websocket.send_text(json.dumps(reply))
                except Exception as lex:
                    logger.error(f"Error processing location_sync: {lex}")

            # 4. Call Answered
            elif msg_type == "call_answer":
                call_id = payload.get("call_id")
                target_call = None
                if call_id and call_id in phone_hub.active_calls:
                    target_call = phone_hub.active_calls[call_id]
                elif phone_hub.active_calls:
                    target_call = next(reversed(list(phone_hub.active_calls.values())))
                    call_id = target_call.get("call_id")
                if target_call:
                    target_call["status"] = "active"
                    reason = target_call.get("reason", "Voice Call")
                    logger.info(f"📞 Android call {call_id} is now ACTIVE. Triggering voice greeting...")
                    broadcast_phone_status_to_web()
                    asyncio.create_task(trigger_call_greeting(reason))

            # 4b. User-Initiated Outbound Call from Android App ("Call ARYA" button)
            elif msg_type == "call_request":
                reason = payload.get("reason", "Direct call from Android companion")
                call_id = new_request_id()
                phone_hub.active_calls[call_id] = {
                    "call_id": call_id,
                    "status": "active",
                    "caller": "User",
                    "reason": reason,
                    "started_at": time.time(),
                }
                logger.info(f"📞 User initiated call from phone (call_id={call_id}). Starting live session...")
                reply = {
                    "type": "call_answer",
                    "request_id": req_id,
                    "timestamp": now_iso(),
                    "payload": {"call_id": call_id, "status": "active"},
                }
                await websocket.send_text(json.dumps(reply))
                broadcast_phone_status_to_web()
                asyncio.create_task(trigger_call_greeting(reason))

            # 5. Call Rejected
            elif msg_type == "call_reject":
                call_id = payload.get("call_id")
                call_info = phone_hub.active_calls.pop(call_id, None) or {
                    "call_id": call_id,
                    "reason": payload.get("reason", "Voice call"),
                }
                logger.info(f"📞 Android call {call_id} was DECLINED by user.")
                phone_hub._emit_call_event("call_declined", call_info)
                broadcast_phone_status_to_web()

            # 6. Call Ended
            elif msg_type == "call_end":
                call_id = payload.get("call_id")
                phone_hub.active_calls.pop(call_id, None)
                logger.info(f"📞 Android call {call_id} ENDED.")
                broadcast_phone_status_to_web()

            # 7. Incoming Speech Text from Phone (On-Device Speech Recognition - Instant Turn)
            elif msg_type == "call_speech_text":
                text = payload.get("text", "").strip()
                phone_hub.last_speech_text_ts = time.time()
                if text and brain:
                    logger.info(f"🗣️ Phone speech text recognized: '{text}' (call_id={payload.get('call_id')})")
                    await brain.handle_text_command(text)

            # 7b. Incoming Audio from Phone Microphone (Raw PCM fallback)
            elif msg_type == "call_audio":
                b64_data = payload.get("data", "")
                # Skip raw audio forwarding if phone recently sent transcribed text (avoids 1007 Live API conflict)
                if time.time() - getattr(phone_hub, "last_speech_text_ts", 0) < 4.0:
                    continue
                if b64_data and brain:
                    pcm_bytes = base64.b64decode(b64_data)
                    await brain.handle_incoming_audio(pcm_bytes)

            # 8. Ping / Pong
            elif msg_type == "ping":
                reply = {
                    "type": "pong",
                    "request_id": req_id,
                    "timestamp": now_iso(),
                    "payload": {"status": "ok"},
                }
                await websocket.send_text(json.dumps(reply))

    except WebSocketDisconnect:
        logger.info("📱 Phone WebSocket disconnected.")
    except Exception as exc:
        logger.warning(f"Phone WebSocket error: {exc}")
    finally:
        if phone_registered:
            phone_hub.unregister_phone(websocket)
            broadcast_phone_status_to_web()


@app.websocket("/ws/web")
async def websocket_web(websocket: WebSocket):
    """Real-time WebSocket connection for web browser interface."""
    await websocket.accept()
    web_clients.add(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") == "text_command":
                text = data.get("text", "").strip()
                if text and brain:
                    await brain.handle_text_command(text)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning(f"Web client error: {exc}")
    finally:
        web_clients.discard(websocket)


@app.websocket("/ws/node")
async def websocket_laptop_node(websocket: WebSocket):
    """
    Persistent reverse WebSocket connection from the Laptop Task Worker.
    No port forwarding required on the laptop.
    """
    await websocket.accept()
    logger.info("New connection on /ws/node. Awaiting authentication...")

    authenticated = False
    try:
        # Step 1: Wait for AUTH message
        raw = await websocket.receive_text()
        msg = parse_message(raw)

        if msg.type != ProtocolTypes.AUTH:
            err = build_message(ProtocolTypes.AUTH_ERROR, {"error": "First message must be 'auth'"})
            await websocket.send_text(err.to_json())
            await websocket.close()
            return

        expected_token = server_config.get("auth_token", "")
        provided_token = msg.payload.get("token", "")

        if expected_token and provided_token != expected_token:
            logger.warning("Laptop auth failed: invalid token provided.")
            err = build_message(ProtocolTypes.AUTH_ERROR, {"error": "Invalid authentication token"})
            await websocket.send_text(err.to_json())
            await websocket.close()
            return

        # Authenticated successfully
        authenticated = True
        dispatcher.register_laptop(websocket, msg.payload)
        ack = build_message(ProtocolTypes.AUTH_ACK, {"status": "authenticated", "server": "Brahma Cloud Brain"})
        await websocket.send_text(ack.to_json())
        logger.info(f"Laptop authenticated successfully: {msg.payload.get('device_name', 'Desktop')}")

        # Step 2: Main message loop
        while True:
            raw_msg = await websocket.receive_text()
            incoming = parse_message(raw_msg)

            # Handle Tool Results
            if incoming.type == ProtocolTypes.TOOL_RESULT:
                dispatcher.handle_tool_result(incoming.request_id, incoming.payload)

            # Handle Incoming Mic Audio from Laptop
            elif incoming.type == ProtocolTypes.AUDIO_CHUNK:
                b64_pcm = incoming.payload.get("data", "")
                if b64_pcm and brain:
                    pcm_bytes = base64.b64decode(b64_pcm)
                    await brain.handle_incoming_audio(pcm_bytes)

            # Handle Text Commands from Laptop UI
            elif incoming.type == ProtocolTypes.TEXT_COMMAND:
                text = incoming.payload.get("text", "")
                if text and brain:
                    await brain.handle_text_command(text)

            # Handle Ping/Pong
            elif incoming.type == ProtocolTypes.PING:
                pong = build_message(ProtocolTypes.PONG, request_id=incoming.request_id)
                await websocket.send_text(pong.to_json())

    except WebSocketDisconnect:
        logger.info("Laptop disconnected.")
    except Exception as exc:
        logger.error(f"Error in laptop WebSocket loop: {exc}")
    finally:
        if authenticated:
            dispatcher.unregister_laptop()


def main():
    parser = argparse.ArgumentParser(description="Brahma Echo Cloud Server")
    parser.add_argument("--host", default=server_config.get("host", "0.0.0.0"), help="Bind host")
    default_port = int(os.environ.get("PORT", server_config.get("port", 8000)))
    parser.add_argument("--port", type=int, default=default_port, help="Bind port")
    parser.add_argument("--token", default=server_config.get("auth_token"), help="Server auth token")
    args = parser.parse_args()

    if args.token:
        server_config["auth_token"] = args.token

    logger.info(f"Starting Brahma Cloud Brain on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
