"""
cloud/vapi_service.py — ARYA Outbound AI Phone Calling Service (via Vapi.ai)

Provides conversational AI phone calling capabilities:
1. Calling the user directly on their phone (e.g. morning briefings, wake-up calls, urgent alerts).
2. Calling other people/businesses on the user's behalf (e.g. clinic appointments, reminders, enquiries).

Supports zero-code account switching:
When free trial credits expire, updating VAPI_API_KEY and VAPI_PHONE_NUMBER_ID
in config/api_keys.json or environment variables instantly switches to the new account.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("VapiService")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
VAPI_API_BASE = "https://api.vapi.ai"


def get_vapi_config() -> Dict[str, str]:
    """
    Retrieve Vapi configuration from environment variables or config/api_keys.json.
    Keys:
      - vapi_api_key
      - vapi_phone_number_id
      - my_phone_number
    """
    api_key = os.environ.get("VAPI_API_KEY", "").strip()
    phone_number_id = os.environ.get("VAPI_PHONE_NUMBER_ID", "").strip()
    my_number = os.environ.get("MY_PHONE_NUMBER", "").strip()

    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                api_key = api_key or data.get("vapi_api_key", "").strip()
                phone_number_id = phone_number_id or data.get("vapi_phone_number_id", "").strip()
                my_number = my_number or data.get("my_phone_number", "").strip()
        except Exception as e:
            logger.warning(f"Error reading {API_CONFIG_PATH}: {e}")

    return {
        "vapi_api_key": api_key,
        "vapi_phone_number_id": phone_number_id,
        "my_phone_number": my_number,
    }


def is_vapi_configured() -> bool:
    """Check if required Vapi credentials exist."""
    conf = get_vapi_config()
    return bool(conf.get("vapi_api_key") and conf.get("vapi_phone_number_id"))


def _format_phone_number(raw_number: str) -> str:
    """Format and validate phone number with leading + and international country code."""
    cleaned = re.sub(r"[^\d+]", "", raw_number.strip())
    if not cleaned.startswith("+"):
        # If user provides 10-digit Indian number without country code, default to +91
        if len(cleaned) == 10:
            cleaned = "+91" + cleaned
        else:
            cleaned = "+" + cleaned
    return cleaned


def _vapi_request(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    """Helper executing HTTP requests to the Vapi.ai REST API."""
    conf = get_vapi_config()
    api_key = conf.get("vapi_api_key")
    if not api_key:
        return {
            "success": False,
            "configured": False,
            "error": (
                "Vapi.ai is not configured. Please add 'vapi_api_key' and "
                "'vapi_phone_number_id' to config/api_keys.json or environment variables."
            ),
        }

    url = f"{VAPI_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Brahma-Echo-Assistant/2.0",
    }

    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            content = resp.read().decode("utf-8")
            if not content:
                return {"success": True}
            return json.loads(content)
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8") if he.fp else str(he)
        logger.error(f"Vapi API HTTP {he.code}: {err_body}")
        return {"success": False, "error": f"Vapi HTTP {he.code}: {err_body}"}
    except Exception as e:
        logger.error(f"Vapi request error: {e}")
        return {"success": False, "error": str(e)}


def make_phone_call_sync(
    phone_number: Optional[str] = None,
    task_objective: str = "",
    first_message: Optional[str] = None,
    caller_name: str = "Abhay",
) -> Dict[str, Any]:
    """
    Initiate an outbound phone call with an intelligent conversational AI assistant.
    If phone_number is omitted, calls the user's default configured number.
    """
    conf = get_vapi_config()
    phone_number_id = conf.get("vapi_phone_number_id")
    my_number = conf.get("my_phone_number")

    if not conf.get("vapi_api_key") or not phone_number_id:
        return {
            "success": False,
            "configured": False,
            "error": "Vapi.ai is not configured yet. Add 'vapi_api_key' and 'vapi_phone_number_id' to config/api_keys.json.",
        }

    target_number = phone_number.strip() if phone_number and phone_number.strip() else my_number
    if not target_number:
        return {
            "success": False,
            "error": "No destination phone number specified and no default 'my_phone_number' found in configuration.",
        }

    formatted_number = _format_phone_number(target_number)
    is_calling_owner = bool(my_number and formatted_number == _format_phone_number(my_number))

    # Construct task-tailored system prompt for the conversational assistant
    if is_calling_owner:
        system_prompt = (
            f"You are ARYA, the personal AI voice assistant calling your boss {caller_name}.\n"
            f"Purpose of this phone call: {task_objective or 'Deliver requested briefing or check-in'}.\n"
            f"Guidelines:\n"
            f"- Speak warmly, professionally, and conversationally in a natural human voice.\n"
            f"- Keep sentences clear and concise for phone communication.\n"
            f"- Fulfill the user's requested briefing or query interactively.\n"
            f"- Wrap up politely when done."
        )
        if not first_message:
            first_message = f"Hello {caller_name}, this is ARYA calling. {task_objective or 'How can I help you right now?'}"
    else:
        system_prompt = (
            f"You are ARYA, a polite, professional, and articulate personal AI voice assistant calling on behalf of {caller_name}.\n"
            f"Objective of this call: {task_objective or 'General inquiry'}.\n"
            f"Guidelines:\n"
            f"- Clearly state that you are calling on behalf of {caller_name}.\n"
            f"- Be courteous, concise, and listen attentively to the person's answers.\n"
            f"- Note all relevant details, appointment slots, or answers they give.\n"
            f"- Thank them warmly and conclude the call once the objective is reached."
        )
        if not first_message:
            first_message = (
                f"Hello! I am ARYA, an AI voice assistant calling on behalf of {caller_name}. "
                f"May I speak with you regarding {task_objective or 'a quick inquiry'}?"
            )

    payload = {
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": formatted_number,
        },
        "assistant": {
            "name": "ARYA",
            "model": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt}
                ],
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel - natural, clear voice
            },
            "firstMessage": first_message,
        },
    }

    res = _vapi_request("/call", method="POST", payload=payload)
    if isinstance(res, dict) and res.get("id"):
        return {
            "success": True,
            "configured": True,
            "call_id": res.get("id"),
            "status": res.get("status", "queued"),
            "phone_number": formatted_number,
            "is_calling_owner": is_calling_owner,
            "message": f"Successfully initiated outbound call to {formatted_number}.",
        }

    return res if isinstance(res, dict) else {"success": False, "error": "Failed to initiate call."}


def get_call_details_sync(call_id: str) -> Dict[str, Any]:
    """Retrieve status, duration, summary, and transcript of a call."""
    if not call_id or not call_id.strip():
        return {"success": False, "error": "Missing call_id."}

    res = _vapi_request(f"/call/{call_id.strip()}", method="GET")
    if isinstance(res, dict) and res.get("id"):
        return {
            "success": True,
            "configured": True,
            "call_id": res.get("id"),
            "status": res.get("status"),
            "duration": res.get("duration"),
            "summary": res.get("summary", ""),
            "transcript": res.get("transcript", ""),
            "cost": res.get("cost"),
            "ended_reason": res.get("endedReason"),
        }
    return res


def list_calls_sync(limit: int = 5) -> Dict[str, Any]:
    """List recent calls made through Vapi."""
    res = _vapi_request(f"/call?limit={min(max(limit, 1), 20)}", method="GET")
    if isinstance(res, list):
        summary_list = []
        for c in res:
            summary_list.append({
                "id": c.get("id"),
                "status": c.get("status"),
                "customer_number": c.get("customer", {}).get("number"),
                "created_at": c.get("createdAt"),
                "summary": c.get("summary", ""),
            })
        return {"success": True, "configured": True, "total": len(summary_list), "calls": summary_list}
    return res if isinstance(res, dict) else {"success": False, "error": "Failed to list calls."}


async def execute_vapi_tool(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous entry point for ARYA Cloud Brain."""
    act = (action or args.get("action", "call_me")).lower().strip()
    phone_number = args.get("phone_number") or args.get("number") or args.get("to")
    objective = (
        args.get("task_objective")
        or args.get("objective")
        or args.get("purpose")
        or args.get("message")
        or args.get("topic", "")
    )
    first_msg = args.get("first_message") or args.get("greeting")
    caller_name = args.get("caller_name") or "Abhay"

    if act in {"call_me", "call_user", "ring_me", "wake_me"}:
        return await asyncio.to_thread(
            make_phone_call_sync,
            phone_number=phone_number,  # will default to my_phone_number
            task_objective=objective or "Wake-up briefing and daily check-in",
            first_message=first_msg,
            caller_name=caller_name,
        )
    elif act in {"call_number", "make_call", "dial", "call", "call_others", "outbound_call"}:
        return await asyncio.to_thread(
            make_phone_call_sync,
            phone_number=phone_number,
            task_objective=objective,
            first_message=first_msg,
            caller_name=caller_name,
        )
    elif act in {"check_call_status", "call_status", "get_call", "details", "transcript"}:
        call_id = args.get("call_id") or ""
        return await asyncio.to_thread(get_call_details_sync, call_id=call_id)
    elif act in {"list_calls", "recent_calls", "call_history"}:
        limit = int(args.get("limit") or 5)
        return await asyncio.to_thread(list_calls_sync, limit=limit)

    return {"success": False, "error": f"Unknown call action: '{action}'."}
