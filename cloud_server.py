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


app = FastAPI(title="ARYA Cloud Brain", version="2.0.0")
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
        self.device_secret: str = secrets.token_hex(24)
        self.device_id: str = "android_companion_primary"

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

    def unregister_phone(self):
        logger.info("📱 Phone disconnected from Cloud Server.")
        self.phone_ws = None
        self.phone_info = {}
        self.active_calls.clear()

    async def call_phone(self, caller_name: str = "ARYA", reason: str = "Voice call from ARYA") -> Dict[str, Any]:
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


dispatcher = WebSocketToolDispatcher()
phone_hub = CloudPhoneHub()
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
    """Broadcasts turn_complete event to browser clients so they know when AI speech ends."""
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
    """Broadcasts real-time WhatsApp events (status, qr, messages) to browser clients."""
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


@app.on_event("startup")
async def on_startup():
    global brain, main_loop
    main_loop = asyncio.get_running_loop()
    logger.info("Initializing ARYA Cloud Brain...")
    brain = CloudBrain(
        tool_dispatcher=dispatcher,
        phone_hub=phone_hub,
        on_audio_out=broadcast_audio_to_web,
        on_transcript=broadcast_transcript_to_web,
        on_turn_complete=broadcast_turn_complete_to_web,
        on_log=lambda msg: logger.info(f"[Brain] {msg}"),
    )
    # Start Gemini Live background loop
    asyncio.create_task(brain.run())

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
    return HTMLResponse(content="<h1>ARYA Cloud Brain Online</h1><p>Visit /api/status for JSON health metrics.</p>")


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
            "service": "Brahma Cloud Brain",
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


@app.post("/api/phone/end-call")
async def api_end_phone_call():
    """Hangs up any active phone call."""
    return await phone_hub.end_call()


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
                    if brain:
                        greeting = f"[Voice call connected with user on phone for: '{reason}'. Greet the user naturally, concisely, and warmly right now to start the live conversation!]"
                        asyncio.create_task(brain.handle_text_command(greeting))

            # 5. Call Rejected
            elif msg_type == "call_reject":
                call_id = payload.get("call_id")
                phone_hub.active_calls.pop(call_id, None)
                logger.info(f"📞 Android call {call_id} was DECLINED by user.")
                broadcast_phone_status_to_web()

            # 6. Call Ended
            elif msg_type == "call_end":
                call_id = payload.get("call_id")
                phone_hub.active_calls.pop(call_id, None)
                logger.info(f"📞 Android call {call_id} ENDED.")
                broadcast_phone_status_to_web()

            # 7. Incoming Audio from Phone Microphone
            elif msg_type == "call_audio":
                b64_data = payload.get("data", "")
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
            phone_hub.unregister_phone()
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
