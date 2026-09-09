"""
tests/test_vapi_service.py — Unit Tests for Vapi.ai Phone Calling Service
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
import unittest
from cloud.vapi_service import (
    is_vapi_configured,
    get_vapi_config,
    _format_phone_number,
    make_phone_call_sync,
    get_call_details_sync,
    list_calls_sync,
    execute_vapi_tool,
)
from core.tools_schema import TOOL_DECLARATIONS


class TestVapiService(unittest.TestCase):
    def test_schema_registration(self):
        tool_names = {t["name"] for t in TOOL_DECLARATIONS}
        self.assertIn("make_phone_call", tool_names, "make_phone_call must be registered in TOOL_DECLARATIONS")

        # Verify parameter schema
        tool = next(t for t in TOOL_DECLARATIONS if t["name"] == "make_phone_call")
        props = tool["parameters"]["properties"]
        self.assertIn("action", props)
        self.assertIn("phone_number", props)
        self.assertIn("task_objective", props)

    def test_phone_number_formatting(self):
        self.assertEqual(_format_phone_number("+919876543210"), "+919876543210")
        self.assertEqual(_format_phone_number("9876543210"), "+919876543210")
        self.assertEqual(_format_phone_number("+1 (415) 555-2671"), "+14155552671")
        self.assertEqual(_format_phone_number("14155552671"), "+14155552671")

    def test_vapi_unconfigured_graceful(self):
        if not is_vapi_configured():
            res = make_phone_call_sync(phone_number="+919876543210", task_objective="Test call")
            self.assertIsInstance(res, dict)
            self.assertFalse(res.get("success"))
            self.assertFalse(res.get("configured", True))
            self.assertIn("error", res)

    def test_vapi_dispatcher_async(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Test call_me dispatch
            res = loop.run_until_complete(
                execute_vapi_tool("call_me", {"task_objective": "Morning briefing"})
            )
            self.assertIsInstance(res, dict)

            # Test call_number dispatch
            res_num = loop.run_until_complete(
                execute_vapi_tool("call_number", {"phone_number": "+919876543210", "task_objective": "Check appointment"})
            )
            self.assertIsInstance(res_num, dict)

            # Test check_call_status dispatch
            res_stat = loop.run_until_complete(
                execute_vapi_tool("check_call_status", {"call_id": "test_id_123"})
            )
            self.assertIsInstance(res_stat, dict)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
