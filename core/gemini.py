"""
core/gemini.py — Resilient Multi-Model Gemini Ladder & Cooldown Manager

Architecture:
    Centralized model execution framework for local laptop tools and worker actions.
    Eliminates unbounded execution hangs and feature failures by enforcing:
    1. Mandatory API timeouts (minimum 10s deadline via HttpOptions).
    2. 9-rung model fallback ladder ordered by response latency.
    3. Intelligent error cooldown tracking per model rung:
       - Quota Exhausted (429): 5-minute cooldown.
       - Service Outage/Timeout (503/504): 30-minute cooldown.
       - Model Unavailable/Access Error (404/403): 6-hour cooldown.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("GeminiLadder")

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

KEY_FILE = BASE_DIR / "config" / "api_keys.json"

FAST = "fast"
SMART = "smart"
SEARCH = "search"

_LADDERS: Dict[str, tuple] = {
    FAST: (
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3-flash-preview",
    ),
    SMART: (
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3-flash-preview",
        "gemini-flash-latest",
    ),
    SEARCH: (
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
    ),
}

DEFAULT_TIMEOUT_MS = 10_000
MIN_TIMEOUT_MS = 10_000

_COOLDOWN_QUOTA = 300       # 5 minutes
_COOLDOWN_UNAVAILABLE = 1800 # 30 minutes
_COOLDOWN_GONE = 21600      # 6 hours

_cooldown: Dict[str, float] = {}
_cool_lock = threading.Lock()
_key_lock = threading.Lock()
_cached_key: Optional[str] = None


def _cool(model: str, seconds: float = _COOLDOWN_QUOTA) -> None:
    with _cool_lock:
        _cooldown[model] = time.monotonic() + seconds


def _is_cooling(model: str) -> bool:
    with _cool_lock:
        until = _cooldown.get(model, 0.0)
        if until and time.monotonic() < until:
            return True
        _cooldown.pop(model, None)
        return False


def is_quota_error(err: str) -> bool:
    return "429" in err or "RESOURCE_EXHAUSTED" in err


def is_unavailable_error(err: str) -> bool:
    low = err.lower()
    return "503" in err or "504" in err or "unavailable" in low or "deadline_exceeded" in low


def is_gone_error(err: str) -> bool:
    low = err.lower()
    return "404" in err or "not found" in low or "is not supported" in low or "permission" in low or "403" in err


def get_api_key(refresh: bool = False) -> str:
    """Retrieve Gemini API key from config file with thread-safe caching."""
    global _cached_key
    with _key_lock:
        if _cached_key is not None and not refresh:
            return _cached_key
        try:
            if KEY_FILE.exists():
                data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
                _cached_key = str(data.get("gemini_api_key") or "")
        except Exception as e:
            logger.warning(f"Could not read API key from {KEY_FILE}: {e}")
            _cached_key = ""
        return _cached_key or ""


def build_client(timeout_ms: int = DEFAULT_TIMEOUT_MS, key: str = ""):
    """Build google.genai Client with mandatory timeout limits."""
    from google import genai
    from google.genai import types as gtypes

    resolved_key = key or get_api_key()
    if not resolved_key:
        raise RuntimeError("No Gemini API key configured in api_keys.json")

    return genai.Client(
        api_key=resolved_key,
        http_options=gtypes.HttpOptions(timeout=max(MIN_TIMEOUT_MS, int(timeout_ms))),
    )


def call(
    contents: Any,
    tier: str = FAST,
    config: Any = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    key: str = "",
) -> Any:
    """Execute generation request across the model ladder.
    
    Walks through models in the tier ladder, skipping cooled down rungs.
    Returns raw SDK response object or None if all rungs fail.
    """
    ladder = _LADDERS.get(tier)
    if ladder is None:
        ladder = (tier,) + tuple(m for m in _LADDERS[SMART] if m != tier)

    resolved_key = key or get_api_key()
    if not resolved_key:
        logger.error("[Gemini] No API key available.")
        return None

    client_obj = None
    tried_models = [m for m in ladder if not _is_cooling(m)] or list(ladder)

    for model in tried_models:
        try:
            if client_obj is None:
                client_obj = build_client(timeout_ms=timeout_ms, key=resolved_key)
            
            kwargs: Dict[str, Any] = {"model": model, "contents": contents}
            if config is not None:
                kwargs["config"] = config

            resp = client_obj.models.generate_content(**kwargs)
            return resp

        except Exception as e:
            err_msg = str(e)
            if is_quota_error(err_msg):
                _cool(model, _COOLDOWN_QUOTA)
                logger.warning(f"[Gemini] Model '{model}' quota exhausted. Resting for {_COOLDOWN_QUOTA // 60}m.")
            elif is_gone_error(err_msg):
                _cool(model, _COOLDOWN_GONE)
                logger.warning(f"[Gemini] Model '{model}' unavailable/404. Resting for {_COOLDOWN_GONE // 3600}h.")
            elif is_unavailable_error(err_msg):
                _cool(model, _COOLDOWN_UNAVAILABLE)
                logger.warning(f"[Gemini] Model '{model}' timed out/503. Resting for {_COOLDOWN_UNAVAILABLE // 60}m.")
            else:
                logger.error(f"[Gemini] Model '{model}' error: {type(e).__name__}: {err_msg[:140]}")

    return None


def text(
    contents: Any,
    tier: str = FAST,
    config: Any = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    key: str = "",
    default: str = "",
) -> str:
    """Execute generation request and return extracted text string."""
    resp = call(contents, tier=tier, config=config, timeout_ms=timeout_ms, key=key)
    if resp is None:
        return default
    txt = getattr(resp, "text", None) or ""
    return txt.strip() or default


def as_json(
    contents: Any,
    tier: str = FAST,
    config: Any = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    key: str = "",
    default: Any = None,
) -> Any:
    """Execute generation request and parse response as structured JSON object/dict."""
    raw = text(contents, tier=tier, config=config, timeout_ms=timeout_ms, key=key)
    if not raw:
        return default

    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    if "{" in cleaned and "}" in cleaned:
        cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
    elif "[" in cleaned and "]" in cleaned:
        cleaned = cleaned[cleaned.find("[") : cleaned.rfind("]") + 1]

    try:
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"[Gemini] Failed to parse JSON response: {e}")
        return default
