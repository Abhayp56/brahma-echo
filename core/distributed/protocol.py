"""
core/distributed/protocol.py — Distributed WebSocket Communication Protocol

Defines structured message contracts and serialization between the Cloud Brain
and Local Laptop Task Workers.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ProtocolTypes:
    # Authentication & Registration
    AUTH = "auth"
    AUTH_ACK = "auth_ack"
    AUTH_ERROR = "auth_error"

    # Tool Execution RPC (Cloud Brain -> Laptop Worker -> Cloud Brain)
    EXECUTE_TOOL = "execute_tool"
    TOOL_RESULT = "tool_result"
    TOOL_PROGRESS = "tool_progress"

    # Multimodal & Audio
    AUDIO_CHUNK = "audio_chunk"
    AUDIO_CONTROL = "audio_control"

    # Commands & Interruption
    TEXT_COMMAND = "text_command"
    INTERRUPT = "interrupt"

    # Screen Capture (Cloud Brain requests screenshot for vision analysis)
    CAPTURE_SCREEN = "capture_screen"
    SCREEN_RESULT = "screen_result"

    # Workspace & UI Status (Laptop Worker -> Cloud or Cloud -> UI)
    WORKSPACE_UPDATE = "workspace_update"

    # Heartbeat
    PING = "ping"
    PONG = "pong"

    # Error
    ERROR = "error"


def new_request_id() -> str:
    """Generate a unique request ID for RPC tracking."""
    return uuid.uuid4().hex


def utc_iso_timestamp() -> str:
    """Generate current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MessageEnvelope:
    """Standard message envelope for all distributed communication."""
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=new_request_id)
    timestamp: str = field(default_factory=utc_iso_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageEnvelope":
        if not isinstance(data, dict):
            raise ValueError("Message data must be a dictionary")
        return cls(
            type=data.get("type", "unknown"),
            request_id=data.get("request_id") or new_request_id(),
            timestamp=data.get("timestamp") or utc_iso_timestamp(),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "MessageEnvelope":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        data = json.loads(raw)
        return cls.from_dict(data)


def build_message(
    msg_type: str,
    payload: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> MessageEnvelope:
    """Helper to construct a typed MessageEnvelope."""
    return MessageEnvelope(
        type=msg_type,
        payload=payload or {},
        request_id=request_id or new_request_id(),
        timestamp=utc_iso_timestamp(),
    )


def parse_message(raw: str | bytes | dict) -> MessageEnvelope:
    """Parse incoming data into a MessageEnvelope."""
    if isinstance(raw, dict):
        return MessageEnvelope.from_dict(raw)
    return MessageEnvelope.from_json(raw)
