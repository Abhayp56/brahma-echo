"""
core/distributed/local_tool_dispatcher.py — Local Desktop Action Dispatcher

Executes local OS, application, browser, file, and office automation actions
requested by the Cloud Brain. Runs strictly on the local laptop node.
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
    """Dispatches and executes local tools on the user's desktop."""

    def __init__(self, player: Optional[Any] = None, speak_fn: Optional[Callable[[str], None]] = None):
        self.player = player or HeadlessPlayerShim()
        self.speak_fn = speak_fn or (lambda text: None)

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a local desktop tool and return a structured dictionary:
        { "success": bool, "result": Any, "error": Optional[str] }
        """
        args = dict(args or {})
        loop = asyncio.get_event_loop()
        logger.info(f"Executing local action: '{tool_name}' with args: {args}")

        try:
            handler = self._get_tool_handler(tool_name)
            if not handler:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Tool '{tool_name}' is not registered on this desktop node.",
                }

            # Run in thread pool to avoid blocking async event loop for long OS actions
            result = await loop.run_in_executor(None, lambda: handler(args))
            return {
                "success": True,
                "result": str(result) if result is not None else "Done.",
                "error": None,
            }

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"Error executing local tool '{tool_name}': {err_msg}\n{traceback.format_exc()}")
            return {
                "success": False,
                "result": None,
                "error": err_msg,
            }

    def _get_tool_handler(self, tool_name: str) -> Optional[Callable[[Dict[str, Any]], Any]]:
        """Map tool name to its local Python handler."""
        if tool_name == "open_app":
            from actions.open_app import open_app
            return lambda a: open_app(parameters=a, response=None, player=self.player)

        elif tool_name in {"computer_control", "desktop_control"}:
            from actions.computer_control import computer_control
            return lambda a: computer_control(parameters=a, player=self.player)

        elif tool_name == "computer_settings":
            from actions.computer_settings import computer_settings
            return lambda a: computer_settings(parameters=a, response=None, player=self.player)

        elif tool_name == "browser_control":
            from actions.browser_control import browser_control
            return lambda a: browser_control(parameters=a, player=self.player)

        elif tool_name == "file_controller":
            from actions.file_controller import file_controller
            return lambda a: file_controller(parameters=a, player=self.player)

        elif tool_name == "file_processor":
            from actions.file_processor import file_processor
            def _run_fp(a):
                if not a.get("file_path") and getattr(self.player, "current_file", None):
                    a["file_path"] = self.player.current_file
                return file_processor(parameters=a, player=self.player, speak=self.speak_fn)
            return _run_fp

        elif tool_name == "presentation_builder":
            from actions.office_builder import create_presentation
            return lambda a: create_presentation(parameters=a, player=self.player)

        elif tool_name == "spreadsheet_builder":
            from actions.office_builder import create_spreadsheet
            return lambda a: create_spreadsheet(parameters=a, player=self.player)

        elif tool_name == "word_document":
            from actions.docx_tools import word_document
            return lambda a: word_document(parameters=a, player=self.player, speak=self.speak_fn)

        elif tool_name == "pdf_document":
            from actions.pdf_tools import create_pdf
            return lambda a: create_pdf(parameters=a, player=self.player)

        elif tool_name == "system_manager":
            from actions.system_manager import run as sm_run
            return lambda a: sm_run(parameters=a, player=self.player)

        elif tool_name == "background_monitor":
            from actions.background_monitor import run as bm_run
            return lambda a: bm_run(parameters=a, player=self.player)

        elif tool_name == "clipboard_processor":
            from actions.clipboard_processor import process_clipboard
            return lambda a: process_clipboard(parameters=a, player=self.player)

        elif tool_name == "weather_report":
            from actions.weather_report import weather_action
            return lambda a: weather_action(parameters=a, player=self.player)

        elif tool_name == "youtube_video":
            from actions.youtube_video import youtube_video
            return lambda a: youtube_video(parameters=a, response=None, player=self.player)

        elif tool_name == "spotify_controller":
            from actions.spotify_controller import spotify_controller
            return lambda a: spotify_controller(parameters=a, player=self.player)

        elif tool_name == "calendar_scheduler":
            from actions.calendar_scheduler import calendar_scheduler
            return lambda a: calendar_scheduler(parameters=a, player=self.player)

        elif tool_name == "daily_briefing":
            from actions.daily_briefing import compile_daily_briefing
            return lambda a: compile_daily_briefing(category=a.get("category", "all"))

        elif tool_name == "dev_agent":
            from actions.dev_agent import dev_agent
            return lambda a: dev_agent(parameters=a, player=self.player, speak=self.speak_fn)

        elif tool_name == "website_builder":
            from actions.website_builder import website_builder
            return lambda a: website_builder(parameters=a, player=self.player)

        elif tool_name == "screen_process":
            # Screen process triggers vision capture and processing locally
            from actions.screen_processor import screen_process
            return lambda a: screen_process(parameters=a, response=None, player=self.player, session_memory=None)

        return None
