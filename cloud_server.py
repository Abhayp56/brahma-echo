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
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from core.distributed.protocol import (
    ProtocolTypes,
    MessageEnvelope,
    build_message,
    parse_message,
    new_request_id,
)
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

dispatcher = WebSocketToolDispatcher()
brain: Optional[CloudBrain] = None
server_config = load_server_config()
web_clients: set[WebSocket] = set()


def broadcast_audio_to_web(pcm_chunk: bytes):
    """Sends synthesized 24kHz audio from Gemini Live directly to connected browser clients."""
    if not web_clients:
        return
    b64_data = base64.b64encode(pcm_chunk).decode("ascii")
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


@app.on_event("startup")
async def on_startup():
    global brain
    logger.info("Initializing ARYA Cloud Brain...")
    brain = CloudBrain(
        tool_dispatcher=dispatcher,
        on_audio_out=broadcast_audio_to_web,
        on_transcript=broadcast_transcript_to_web,
        on_turn_complete=broadcast_turn_complete_to_web,
        on_log=lambda msg: logger.info(f"[Brain] {msg}"),
    )
    # Start Gemini Live background loop
    asyncio.create_task(brain.run())


@app.get("/", response_class=HTMLResponse)
async def get_web_ui():
    """Serves the browser-based Web Voice & Task interface."""
    ui_path = BASE_DIR / "cloud" / "web_ui.html"
    if ui_path.exists():
        return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>ARYA Cloud Brain Online</h1><p>Visit /api/status for JSON health metrics.</p>")


@app.get("/api/status")
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
