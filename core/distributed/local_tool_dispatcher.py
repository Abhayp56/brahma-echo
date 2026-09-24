"""
core/distributed/local_tool_dispatcher.py — Pure Ada-SI Local Desktop Action Dispatcher

All local desktop actions on the laptop node are executed dynamically via Ada-SI Bridge & Forge Master.
All legacy hardcoded static skills have been removed to ensure 100% self-improving execution.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("LocalToolDispatcher")


class HeadlessPlayerShim:
    """Fallback player shim for headless/non-GUI worker mode."""
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log_callback = log_callback or (lambda msg: logger.info(f"[UI] {msg}"))
        self.current_file = None

    def write_log(self, text: str) -> None:
        self.log_callback(text)

    def set_state(self, state: str) -> None:
        pass

    def update_task_workspace(self, **kwargs) -> None:
        pass

    def finish_task_workspace(self, *args, **kwargs) -> None:
        pass

    def clear_task_workspace(self) -> None:
        pass


class LocalToolDispatcher:
    """Dispatches and executes local tools on the user's desktop strictly via Ada-SI Bridge & Forge Master."""

    def __init__(self, player: Optional[Any] = None, speak_fn: Optional[Callable[[str], None]] = None):
        self.player = player or HeadlessPlayerShim()
        self.speak_fn = speak_fn or (lambda text: None)

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a local desktop tool strictly via Ada-SI Bridge.
        If the tool is not already forged, Ada-SI Forge Master will plan, write, test,
        and install a new Python tool on the fly and execute it.
        """
        args = dict(args or {})
        logger.info(f"[LocalToolDispatcher] ⚡ Pure Ada-SI Execution for tool '{tool_name}' with args: {args}")

        try:
            from core.ada_si_bridge import ada_bridge

            # 1. Try executing pre-forged custom tool if already installed
            res = await ada_bridge.execute_custom_tool(tool_name, args)
            if res.get("success"):
                logger.info(f"[LocalToolDispatcher] ✅ Custom tool '{tool_name}' executed successfully.")
                return {"success": True, "result": str(res.get("output", "Done.")), "error": None}

            # 2. Tool not yet forged: Trigger Forge Master codegen on the fly
            prompt_desc = (
                args.get("description")
                or args.get("task")
                or args.get("prompt")
                or f"Perform laptop desktop task: {tool_name}"
            )
            logger.info(f"[LocalToolDispatcher] 🛠️ Tool '{tool_name}' not found. Invoking Ada-SI Forge Master for: '{prompt_desc}'...")
            
            if self.speak_fn:
                self.speak_fn(f"Forging a new Python tool for {tool_name}...")

            f_ok, f_msg, f_manifest = await ada_bridge.forge_tool_for_prompt(prompt_desc, tool_name=tool_name)
            if f_ok and f_manifest:
                forged_name = f_manifest.get("name", tool_name)
                logger.info(f"[LocalToolDispatcher] ✅ Tool '{forged_name}' forged! Executing now...")
                res_forged = await ada_bridge.execute_custom_tool(forged_name, args)
                return {
                    "success": True,
                    "result": str(res_forged.get("output", "Forged and executed successfully.")),
                    "error": None
                }
            else:
                logger.error(f"[LocalToolDispatcher] ❌ Forge Master failed for '{tool_name}': {f_msg}")
                return {"success": False, "result": None, "error": f"Forge Master failed: {f_msg}"}

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"[LocalToolDispatcher] Error executing tool '{tool_name}': {err_msg}\n{traceback.format_exc()}")
            return {
                "success": False,
                "result": None,
                "error": err_msg,
            }
