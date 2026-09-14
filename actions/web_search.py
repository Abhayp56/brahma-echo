# actions/web_search.py — Local & Remote Web Search Tool Action
"""
Web Search Action for Brahma / ARYA.
Delegates to the Multi-Provider Search Service (GcrawlAI -> serpstack -> Zenserp -> DDG -> Gemini Grounding).
Maintains 100% backward compatibility with main.py, agent planners, and laptop execution.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("WebSearchAction")

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def web_search(
    parameters: Optional[Dict[str, Any]] = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Executes web search using the multi-provider fallback engine.
    Compatible with existing signatures across Brahma / Echo codebase.
    """
    params = parameters or {}
    query = str(params.get("query", "")).strip()
    mode = str(params.get("mode", "search")).lower().strip()
    items = params.get("items", [])
    aspect = str(params.get("aspect", "general")).strip() or "general"

    if not query and not items:
        return "Please provide a search query, boss."

    if items and mode != "compare":
        mode = "compare"

    if player:
        log_label = query or ", ".join(str(i) for i in items)
        try:
            player.write_log(f"[Search] {log_label}")
        except Exception:
            pass

    print(f"[WebSearch] Query: {query!r} | Mode: {mode}")

    try:
        from cloud.search_service import get_search_engine
        engine = get_search_engine()
        result = engine.execute(
            query=query,
            mode=mode,
            items=items,
            aspect=aspect
        )
        formatted = result.get("formatted_text", "")
        provider = result.get("provider", "Engine")
        print(f"[WebSearch] Search completed via {provider}.")
        return formatted or "No relevant information found, boss."

    except Exception as ex:
        logger.error(f"[WebSearch] Failed executing multi-provider search: {ex}", exc_info=True)
        return f"Search encountered an error, boss: {ex}"
