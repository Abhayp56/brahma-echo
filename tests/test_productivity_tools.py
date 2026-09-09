"""
tests/test_productivity_tools.py — Unit Tests for News, Calendar, Gmail & Todoist Integrations
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
import unittest
from cloud.news_service import get_news_headlines_sync, get_news_headlines
from cloud.todoist_service import list_tasks_sync, execute_todoist_tool
from cloud.google_workspace import (
    is_google_configured,
    list_calendar_events_sync,
    list_emails_sync,
    execute_calendar_tool,
    execute_gmail_tool,
)
from core.tools_schema import TOOL_DECLARATIONS


class TestProductivityTools(unittest.TestCase):
    def test_schema_registration(self):
        tool_names = {t["name"] for t in TOOL_DECLARATIONS}
        expected = ["get_news", "calendar_control", "gmail_control", "todoist_control"]
        for name in expected:
            self.assertIn(name, tool_names, f"Tool '{name}' must be registered in TOOL_DECLARATIONS")

    def test_news_google_rss_fetch(self):
        # Tests the keyless Google News RSS fallback
        res = get_news_headlines_sync(query="technology", max_results=3)
        self.assertTrue(res.get("success"), f"News fetch failed: {res}")
        self.assertIn("articles", res)
        self.assertGreater(len(res["articles"]), 0)
        top = res["articles"][0]
        self.assertTrue(bool(top.get("title")), "Article must have a title")
        self.assertTrue(bool(top.get("url")), "Article must have a URL")

    def test_news_async_wrapper(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(get_news_headlines(category="science", max_results=2))
            self.assertTrue(res.get("success"))
            self.assertGreater(len(res["articles"]), 0)
        finally:
            loop.close()

    def test_todoist_unconfigured_graceful(self):
        # Without a valid token, Todoist should return configured: False gracefully without throwing an exception
        res = list_tasks_sync()
        self.assertIsInstance(res, dict)
        if not res.get("configured", True):
            self.assertIn("error", res)
            self.assertFalse(res.get("success"))

    def test_todoist_dispatcher(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(execute_todoist_tool("list_tasks", {}))
            self.assertIsInstance(res, dict)

            # Test update_task dispatch
            up_res = loop.run_until_complete(
                execute_todoist_tool("update_task", {"task_name": "non_existent_mock_xyz", "due_date": "tomorrow"})
            )
            self.assertIsInstance(up_res, dict)

            # Test delete_task dispatch
            del_res = loop.run_until_complete(
                execute_todoist_tool("delete_task", {"task_name": "non_existent_mock_xyz"})
            )
            self.assertIsInstance(del_res, dict)
        finally:
            loop.close()

    def test_google_workspace_unconfigured_graceful(self):
        # Without credentials/tokens, Google Workspace operations should report configured: False gracefully
        if not is_google_configured():
            cal_res = list_calendar_events_sync()
            self.assertFalse(cal_res.get("success"))
            self.assertFalse(cal_res.get("configured", True))

            mail_res = list_emails_sync()
            self.assertFalse(mail_res.get("success"))
            self.assertFalse(mail_res.get("configured", True))


if __name__ == "__main__":
    unittest.main()
