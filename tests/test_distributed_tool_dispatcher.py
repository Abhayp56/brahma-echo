"""
Unit tests for core/distributed/local_tool_dispatcher.py (compatible with standard unittest)
"""

import unittest
from core.distributed.local_tool_dispatcher import LocalToolDispatcher, HeadlessPlayerShim


class TestLocalToolDispatcher(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_tool(self):
        dispatcher = LocalToolDispatcher()
        result = await dispatcher.execute("non_existent_tool_xyz", {})
        self.assertFalse(result["success"])
        self.assertIn("not registered", result["error"])

    async def test_headless_shim_does_not_crash(self):
        shim = HeadlessPlayerShim()
        shim.write_log("test log")
        shim.set_state("LISTENING")
        shim.update_task_workspace(status="working")
        shim.finish_task_workspace("done")
        shim.clear_task_workspace()

    async def test_tool_handler_registration(self):
        dispatcher = LocalToolDispatcher()
        known_tools = [
            "open_app",
            "computer_control",
            "computer_settings",
            "browser_control",
            "file_controller",
            "file_processor",
            "presentation_builder",
            "spreadsheet_builder",
            "word_document",
            "pdf_document",
            "system_manager",
            "background_monitor",
            "clipboard_processor",
            "weather_report",
            "youtube_video",
            "spotify_controller",
            "calendar_scheduler",
            "daily_briefing",
            "dev_agent",
            "website_builder",
            "screen_process",
        ]
        for tool_name in known_tools:
            handler = dispatcher._get_tool_handler(tool_name)
            self.assertIsNotNone(handler, f"Handler for {tool_name} should be registered")


if __name__ == "__main__":
    unittest.main()
