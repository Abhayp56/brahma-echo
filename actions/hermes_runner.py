"""
actions/hermes_runner.py — Hermes Agent Runner Integration for Brahma-Echo

Bridge module connecting Brahma-Echo Cloud & Desktop Dispatcher with the local
Hermes Agent framework in `hermes-agent-main`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("HermesRunner")

# Resolve root workspace & hermes-agent-main paths
ACTIONS_DIR = Path(__file__).resolve().parent
BRAHMA_ROOT = ACTIONS_DIR.parent
WORKSPACE_ROOT = BRAHMA_ROOT.parent
HERMES_DIR = WORKSPACE_ROOT / "hermes-agent-main"
if not HERMES_DIR.exists():
    # Fallback to local subdirectory if placed inside Brahma-Echo-main
    HERMES_DIR = BRAHMA_ROOT / "hermes-agent-main"

API_KEY_PATH = BRAHMA_ROOT / "config" / "api_keys.json"


def _ensure_hermes_imports():
    """Ensure hermes-agent-main directory is in sys.path."""
    if HERMES_DIR.exists() and str(HERMES_DIR) not in sys.path:
        sys.path.insert(0, str(HERMES_DIR))


def _load_api_keys() -> Dict[str, str]:
    """Load API keys from Brahma config."""
    if API_KEY_PATH.exists():
        try:
            with open(API_KEY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load api_keys.json: {e}")
    return {}


def run_hermes_agent(
    parameters: Dict[str, Any],
    player: Optional[Any] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Executes a multi-step task using Hermes Agent.

    Parameters:
      - task / description / prompt (str): The instructions for Hermes Agent.
      - model (str): Optional LLM model name (defaults to OpenRouter Hermes 3 or free model).
      - max_iterations (int): Maximum iterations allowed.
    """
    _ensure_hermes_imports()

    task = (
        parameters.get("task")
        or parameters.get("prompt")
        or parameters.get("description")
        or parameters.get("command")
        or ""
    ).strip()

    if not task:
        return {
            "success": False,
            "result": None,
            "error": "No task or prompt provided for Hermes Agent.",
        }

    model = parameters.get("model") or "nousresearch/hermes-3-llama-3.1-405b:free"
    max_iterations = int(parameters.get("max_iterations") or 25)

    api_keys = _load_api_keys()
    openrouter_key = api_keys.get("openrouter_api_key", "").strip() or os.environ.get("OPENROUTER_API_KEY", "")

    def _log_progress(msg: str):
        logger.info(f"[Hermes] {msg}")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[Hermes] {msg}")
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    _log_progress(f"Initializing Hermes Agent for task: '{task[:80]}...'")

    try:
        from run_agent import AIAgent

        # Configure agent with OpenRouter / Web AI backend
        base_url = "https://openrouter.ai/api/v1"
        
        agent_kwargs = {
            "model": model,
            "max_iterations": max_iterations,
            "verbose_logging": True,
            "status_callback": lambda text: _log_progress(f"Status: {text}"),
            "event_callback": lambda event_type, data: _log_progress(f"Event [{event_type}]: {data.get('message', '') if isinstance(data, dict) else data}"),
            "tool_progress_callback": lambda text: _log_progress(f"Tool Progress: {text}"),
        }

        if openrouter_key:
            agent_kwargs["base_url"] = base_url
            agent_kwargs["api_key"] = openrouter_key
            agent_kwargs["provider"] = "openrouter"

        agent = AIAgent(**agent_kwargs)

        _log_progress("Running Hermes conversation loop...")
        response = agent.run_conversation(task)

        _log_progress("Hermes Agent execution finished successfully.")
        return {
            "success": True,
            "result": str(response) if response else "Task completed by Hermes Agent.",
            "error": None,
        }

    except Exception as exc:
        err_msg = str(exc)
        stack = traceback.format_exc()
        logger.error(f"Hermes Agent execution failed: {err_msg}\n{stack}")
        _log_progress(f"Hermes Agent Error: {err_msg}")
        return {
            "success": False,
            "result": None,
            "error": f"Hermes Agent execution failed: {err_msg}",
        }
