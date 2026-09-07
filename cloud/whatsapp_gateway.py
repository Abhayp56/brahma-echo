"""
cloud/whatsapp_gateway.py — ARYA Server-Side WhatsApp Multi-Device Gateway

Maintains 24/7 background WhatsApp connection on the cloud server using Multi-Device protocol.
Enables ARYA to send messages, images, and documents, and converse with contacts.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# Ensure Python 3.10 compatibility for typing.Self before importing neonize
import typing
if not hasattr(typing, "Self"):
    try:
        import typing_extensions
        typing.Self = typing_extensions.Self
    except ImportError:
        pass

import qrcode

from cloud.whatsapp_conversations import (
    clean_phone_number,
    resolve_phone_number,
    save_contact_number,
    generate_ai_reply,
)

logger = logging.getLogger("WhatsAppGateway")

BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_DIR = BASE_DIR / "config"
SESSION_PATH = SESSION_DIR / "whatsapp_session.db"
CONFIG_PATH = SESSION_DIR / "whatsapp_config.json"


def _generate_qr_data_url(qr_raw: bytes | str) -> str:
    """Convert raw QR string/bytes into a Base64 PNG data URL for direct web rendering."""
    if isinstance(qr_raw, bytes):
        try:
            qr_text = qr_raw.decode("utf-8")
        except Exception:
            qr_text = str(qr_raw)
    else:
        qr_text = str(qr_raw)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_str}"


class WhatsAppGateway:
    """
    Singleton gateway managing the WhatsApp Multi-Device companion node.
    Runs persistently on the cloud server.
    """

    _instance: Optional[WhatsAppGateway] = None

    @classmethod
    def get_instance(cls) -> WhatsAppGateway:
        if cls._instance is None:
            cls._instance = WhatsAppGateway()
        return cls._instance

    def __init__(self):
        self.status: str = "disconnected"  # disconnected | qr_ready | connecting | connected
        self.qr_data_url: Optional[str] = None
        self.linked_phone: Optional[str] = None
        self.linked_name: Optional[str] = None
        self.mode: str = "notify_only"  # notify_only | whitelist | auto_pilot
        self.whitelist: Set[str] = set()
        self.recent_chats: List[Dict[str, Any]] = []

        self.client: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._event_listeners: List[Callable[[str, Any], None]] = []
        self._lock = threading.Lock()
        self.is_running = False

        self._load_config()

    @property
    def is_connected(self) -> bool:
        return self.status == "connected"

    def _load_config(self):
        """Load persistent WhatsApp configuration (mode, whitelist, etc.)."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.mode = data.get("mode", "notify_only")
                    self.whitelist = set(data.get("whitelist", []))
            except Exception as e:
                logger.warning(f"Failed to read {CONFIG_PATH}: {e}")

    def _save_config(self):
        """Save persistent WhatsApp configuration."""
        try:
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "mode": self.mode,
                    "whitelist": list(self.whitelist),
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save {CONFIG_PATH}: {e}")

    def add_listener(self, callback: Callable[[str, Any], None]):
        """Register a callback for WhatsApp events (qr, status, message)."""
        self._event_listeners.append(callback)

    def _broadcast(self, event_type: str, payload: Any):
        """Notify all registered listeners (e.g. web clients via WebSocket)."""
        for listener in self._event_listeners:
            try:
                listener(event_type, payload)
            except Exception as e:
                logger.warning(f"Error in WhatsApp event listener: {e}")

    def start(self):
        """Initialize and start the WhatsApp background worker."""
        if self.is_running:
            return

        try:
            from neonize.client import NewClient
            from neonize.events import ConnectedEv, MessageEv, PairStatusEv
        except ImportError as exc:
            logger.error(f"Neonize is not available: {exc}. WhatsApp gateway disabled.")
            return

        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        db_path = str(SESSION_PATH)

        logger.info(f"Initializing WhatsApp Multi-Device Client with session at {db_path}...")
        self.status = "connecting"
        self._broadcast("whatsapp_status", self.get_status())

        try:
            self.client = NewClient(db_path)
        except Exception as e:
            logger.error(f"Failed to create NewClient: {e}")
            self.status = "disconnected"
            return

        # 1. QR Code Event
        @self.client.qr
        def on_qr(client_inst, qr_bytes):
            logger.info("⚡ WhatsApp Pairing QR Code generated!")
            try:
                data_url = _generate_qr_data_url(qr_bytes)
                with self._lock:
                    self.qr_data_url = data_url
                    self.status = "qr_ready"
                self._broadcast("whatsapp_qr", {"qr_data_url": data_url})
                self._broadcast("whatsapp_status", self.get_status())
            except Exception as ex:
                logger.error(f"Error generating QR code: {ex}")

        # 2. Connected Event
        @self.client.event(ConnectedEv)
        def on_connected(client_inst, event: ConnectedEv):
            logger.info("🟢 WhatsApp Multi-Device session successfully connected!")
            with self._lock:
                self.status = "connected"
                self.qr_data_url = None
                try:
                    me = client_inst.get_me()
                    if me:
                        self.linked_phone = me.JID.User if hasattr(me, "JID") else str(me)
                        self.linked_name = getattr(me, "PushName", None) or "User"
                except Exception:
                    pass

            self._broadcast("whatsapp_status", self.get_status())

        # 3. Pairing Status Event
        @self.client.event(PairStatusEv)
        def on_pair_status(client_inst, event: PairStatusEv):
            logger.info(f"WhatsApp Pair Status: {event}")

        # 4. Inbound Message Event
        @self.client.event(MessageEv)
        def on_message(client_inst, message: MessageEv):
            try:
                info = getattr(message, "Info", None)
                if not info:
                    return

                src = getattr(info, "MessageSource", None)
                if src and getattr(src, "IsFromMe", False):
                    # Do not process our own outgoing messages
                    return

                chat_jid = getattr(src, "Chat", None) if src else None
                sender_jid = getattr(src, "Sender", None) if src else None
                sender_alt = getattr(src, "SenderAlt", None) if src else None

                # For 1-on-1 chats, reply directly to Chat JID or Sender JID
                reply_jid = chat_jid or sender_jid
                sender_phone = (
                    getattr(sender_alt, "User", None)
                    or getattr(sender_jid, "User", None)
                    or getattr(chat_jid, "User", "")
                )
                push_name = getattr(info, "Pushname", "") or sender_phone or "Friend"

                # Detect if this message came from a WhatsApp group
                chat_server = getattr(chat_jid, "Server", "") if chat_jid else ""
                sender_server = getattr(sender_jid, "Server", "") if sender_jid else ""
                is_group = bool(
                    getattr(src, "IsGroup", False)
                    or chat_server == "g.us"
                    or sender_server == "g.us"
                    or "@g.us" in str(getattr(chat_jid, "String", ""))
                )

                # Extract text content
                msg_obj = getattr(message, "Message", None)
                text = ""
                if msg_obj:
                    if getattr(msg_obj, "conversation", None):
                        text = msg_obj.conversation
                    elif getattr(msg_obj, "extendedTextMessage", None):
                        text = msg_obj.extendedTextMessage.text

                if not text:
                    return

                logger.info(
                    f"📩 Incoming WhatsApp {'[GROUP] ' if is_group else ''}from "
                    f"{push_name} ({sender_phone}): '{text}'"
                )

                record = {
                    "id": getattr(info, "ID", str(time.time())),
                    "sender": push_name,
                    "phone": sender_phone,
                    "text": text,
                    "time": time.strftime("%H:%M"),
                    "direction": "inbound",
                    "is_ai_reply": False,
                    "is_group": is_group,
                }

                with self._lock:
                    self.recent_chats.append(record)
                    if len(self.recent_chats) > 50:
                        self.recent_chats.pop(0)

                # Broadcast to Web UI so user sees incoming text live
                self._broadcast("whatsapp_message", record)

                # Auto-reply decision
                should_reply = False
                if is_group:
                    # STRICT RULE: ARYA remembers group chats for Abhay, but NEVER sends auto-replies into groups!
                    should_reply = False
                    logger.info(f"👥 Group message logged from {push_name}. Group auto-reply suppressed.")
                elif self.mode == "auto_pilot":
                    should_reply = True
                elif self.mode == "whitelist":
                    clean_sender = clean_phone_number(sender_phone)
                    if sender_phone in self.whitelist or clean_sender in self.whitelist:
                        should_reply = True

                if should_reply:
                    threading.Thread(
                        target=self._auto_reply_worker,
                        args=(sender_phone, push_name, text, reply_jid),
                        daemon=True,
                    ).start()

            except Exception as err:
                logger.error(f"Error handling incoming WhatsApp message: {err}")

        # Start worker thread
        def _runner():
            logger.info("WhatsApp background network thread started.")
            try:
                self.client.connect()
            except Exception as e:
                logger.error(f"WhatsApp client run loop stopped: {e}")
            finally:
                with self._lock:
                    self.is_running = False
                    if self.status != "connected":
                        self.status = "disconnected"
                self._broadcast("whatsapp_status", self.get_status())

        self.is_running = True
        self._thread = threading.Thread(target=_runner, name="WhatsAppRunner", daemon=True)
        self._thread.start()

    def _auto_reply_worker(
        self,
        sender_phone: str,
        sender_name: str,
        incoming_text: str,
        reply_jid: Optional[Any] = None,
    ):
        """Generates AI response and sends it back to contact with natural delay."""
        try:
            time.sleep(1.5)  # Natural human delay
            reply = generate_ai_reply(sender_name, sender_phone, incoming_text)
            if not reply:
                reply = "Hey! This is ARYA, Abhay's AI assistant. He is currently occupied, but I've noted your message for him!"

            logger.info(f"🤖 ARYA sending autonomous WhatsApp reply to {sender_name}: '{reply}'")
            res = self.send_text(sender_phone, reply, target_jid=reply_jid)
            if res.get("success"):
                record = {
                    "id": str(time.time()),
                    "sender": "ARYA (AI Auto-Reply)",
                    "phone": sender_phone,
                    "text": reply,
                    "time": time.strftime("%H:%M"),
                    "direction": "outbound",
                    "is_ai_reply": True,
                }
                with self._lock:
                    self.recent_chats.append(record)
                self._broadcast("whatsapp_message", record)
        except Exception as e:
            logger.error(f"Error in _auto_reply_worker: {e}")

    def send_text(
        self,
        recipient: str,
        message: str,
        target_jid: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp.
        If target_jid is provided, sends directly to that JID (supporting LID & private chat threads).
        """
        if self.status != "connected" or not self.client:
            return {
                "success": False,
                "error": "WhatsApp is not connected. Please scan the QR code in the ARYA Web UI first.",
            }

        try:
            from neonize.utils import build_jid

            if target_jid is not None:
                jid = target_jid
                phone = getattr(target_jid, "User", recipient)
            else:
                phone = resolve_phone_number(recipient)
                if not phone:
                    return {
                        "success": False,
                        "needs_phone": True,
                        "error": f"Could not find phone number for '{recipient}'. Please provide their WhatsApp phone number.",
                    }
                jid = build_jid(phone, server="s.whatsapp.net")

            self.client.send_message(jid, message)
            logger.info(f"✅ Sent WhatsApp message to {phone}: '{message[:40]}'")

            # Record outgoing message
            record = {
                "id": str(time.time()),
                "sender": "You / ARYA",
                "phone": phone,
                "text": message,
                "time": time.strftime("%H:%M"),
                "direction": "outbound",
                "is_ai_reply": False,
            }
            with self._lock:
                self.recent_chats.append(record)
            self._broadcast("whatsapp_message", record)

            return {
                "success": True,
                "recipient": recipient,
                "phone": phone,
                "message": message,
            }
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {phone}: {e}")
            return {"success": False, "error": str(e)}

    def send_media(
        self,
        recipient: str,
        file_path_or_url: str,
        caption: str = "",
        media_type: str = "document",
    ) -> Dict[str, Any]:
        """
        Send an image or document via WhatsApp.
        """
        if self.status != "connected" or not self.client:
            return {
                "success": False,
                "error": "WhatsApp is not connected. Please scan the QR code in the ARYA Web UI first.",
            }

        phone = resolve_phone_number(recipient)
        if not phone:
            return {
                "success": False,
                "needs_phone": True,
                "error": f"Could not find phone number for '{recipient}'. Please provide their WhatsApp phone number.",
            }

        file_path = Path(file_path_or_url)
        if not file_path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path_or_url}",
            }

        try:
            from neonize.utils import build_jid
            jid = build_jid(phone)

            ext = file_path.suffix.lower()
            is_image = media_type == "image" or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}

            if is_image:
                self.client.send_image(jid, str(file_path), caption=caption)
            else:
                self.client.send_document(
                    jid,
                    str(file_path),
                    caption=caption,
                    filename=file_path.name,
                )

            logger.info(f"✅ Sent WhatsApp media ({file_path.name}) to {phone}")

            record = {
                "id": str(time.time()),
                "sender": "You / ARYA",
                "phone": phone,
                "text": f"[{'Image' if is_image else 'Document'}: {file_path.name}] {caption}",
                "time": time.strftime("%H:%M"),
                "direction": "outbound",
                "is_ai_reply": False,
            }
            with self._lock:
                self.recent_chats.append(record)
            self._broadcast("whatsapp_message", record)

            return {
                "success": True,
                "recipient": recipient,
                "phone": phone,
                "file": file_path.name,
                "caption": caption,
            }
        except Exception as e:
            logger.error(f"Failed to send media via WhatsApp: {e}")
            return {"success": False, "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Return structured status of the WhatsApp companion node."""
        return {
            "status": self.status,
            "is_connected": self.status == "connected",
            "linked_phone": self.linked_phone,
            "linked_name": self.linked_name,
            "mode": self.mode,
            "whitelist_count": len(self.whitelist),
            "whitelist": sorted(list(self.whitelist)),
            "recent_chat_count": len(self.recent_chats),
            "has_qr": self.qr_data_url is not None,
        }

    def set_mode(self, mode: str) -> Dict[str, Any]:
        """Update conversational mode ('notify_only', 'whitelist', 'auto_pilot')."""
        if mode in {"notify_only", "whitelist", "auto_pilot"}:
            self.mode = mode
            self._save_config()
            self._broadcast("whatsapp_status", self.get_status())
            return {"success": True, "mode": self.mode}
        return {"success": False, "error": f"Invalid mode: {mode}"}

    def update_whitelist(self, recipient_or_phone: str, action: str = "add") -> Dict[str, Any]:
        """Add or remove phone number or contact from auto-reply whitelist."""
        clean = clean_phone_number(recipient_or_phone)
        if not clean or len(clean) < 7:
            from cloud.whatsapp_conversations import resolve_phone_number
            resolved = resolve_phone_number(recipient_or_phone)
            if resolved:
                clean = resolved

        if not clean:
            return {
                "success": False,
                "error": f"Could not resolve phone number for '{recipient_or_phone}'. Please provide a valid number with country code.",
            }

        if action == "add":
            self.whitelist.add(clean)
        elif action == "remove":
            self.whitelist.discard(clean)

        self._save_config()
        self._broadcast("whatsapp_status", self.get_status())
        return {"success": True, "action": action, "phone": clean, "whitelist": sorted(list(self.whitelist))}

    def disconnect(self):
        """Disconnect or logout current session."""
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        with self._lock:
            self.is_running = False
            self.status = "disconnected"
            self.qr_data_url = None
            self.linked_phone = None
            self.linked_name = None
        self._broadcast("whatsapp_status", self.get_status())
        return {"success": True, "status": "disconnected"}

    def restart(self):
        """Cleanly restart WhatsApp client and generate a fresh QR code."""
        logger.info("Restarting WhatsApp Multi-Device Gateway...")
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        with self._lock:
            self.client = None
            self.is_running = False
            self.status = "connecting"
            self.qr_data_url = None
        self.start()

    def request_phone_pairing_code(self, phone: str) -> Dict[str, Any]:
        """Request an 8-digit pairing code from WhatsApp for phone linking."""
        clean = clean_phone_number(phone)
        if not clean or len(clean) < 10:
            return {
                "success": False,
                "error": "Invalid phone number. Please enter country code followed by number (e.g. 919876543210).",
            }

        if not self.is_running or not self.client:
            self.restart()
            time.sleep(2)

        try:
            code = self.client.PairPhone(clean, show_push_notification=True)
            logger.info(f"⚡ WhatsApp Pairing Code generated for {clean}: {code}")
            return {"success": True, "code": code, "phone": clean}
        except Exception as e:
            logger.error(f"PairPhone error: {e}")
            return {"success": False, "error": str(e)}
