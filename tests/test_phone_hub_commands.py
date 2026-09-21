import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from cloud_server import CloudPhoneHub, phone_hub
from core.tools_schema import TOOL_DECLARATIONS


class TestPhoneHubCommands(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.hub = CloudPhoneHub()

    async def test_tools_schema_contains_phone_hub_control(self):
        tool = next((t for t in TOOL_DECLARATIONS if t.get("name") == "phone_hub_control"), None)
        self.assertIsNotNone(tool, "phone_hub_control must be declared in TOOL_DECLARATIONS")
        self.assertIn("action", tool["parameters"]["properties"])
        self.assertIn("target", tool["parameters"]["properties"])
        self.assertIn("text", tool["parameters"]["properties"])
        self.assertIn("contact", tool["parameters"]["properties"])
        self.assertIn("query", tool["parameters"]["properties"])
        self.assertIn("media_action", tool["parameters"]["properties"])
        self.assertIn("limit", tool["parameters"]["properties"])
        self.assertIn("enabled", tool["parameters"]["properties"])

    async def test_execute_phone_command_disconnected(self):
        res = await self.hub.execute_phone_command("see_screen", {})
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "PHONE_DISCONNECTED")

    async def test_execute_phone_command_success(self):
        mock_ws = AsyncMock()
        self.hub.register_phone(mock_ws, {"name": "Test Pixel 8"})

        async def simulate_phone_response():
            # Wait briefly for command to be dispatched
            await asyncio.sleep(0.05)
            self.assertEqual(len(self.hub.pending_commands), 1)
            req_id = next(iter(self.hub.pending_commands.keys()))

            # Verify mock_ws received command_request
            self.assertTrue(mock_ws.send_text.called)
            sent_payload = json.loads(mock_ws.send_text.call_args[0][0])
            self.assertEqual(sent_payload["type"], "command_request")
            self.assertEqual(sent_payload["payload"]["action"], "see_screen")

            # Simulate phone reply with result
            fut = self.hub.pending_commands[req_id]
            fut.set_result({
                "success": True,
                "data": {
                    "active_package": "com.whatsapp",
                    "elements": [{"index": 1, "label": "Search"}]
                }
            })

        asyncio.create_task(simulate_phone_response())
        res = await self.hub.execute_phone_command("see_screen", {}, timeout=2.0)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["active_package"], "com.whatsapp")
        self.assertEqual(len(self.hub.pending_commands), 0)

    async def test_execute_phone_command_timeout(self):
        mock_ws = AsyncMock()
        self.hub.register_phone(mock_ws, {"name": "Test Pixel 8"})
        res = await self.hub.execute_phone_command("see_screen", {}, timeout=0.1)
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "TIMEOUT")
        self.assertEqual(len(self.hub.pending_commands), 0)

    async def test_unregister_cleans_pending_commands(self):
        mock_ws = AsyncMock()
        self.hub.register_phone(mock_ws, {"name": "Test Pixel 8"})

        # Start a pending command
        task = asyncio.create_task(self.hub.execute_phone_command("see_screen", {}, timeout=5.0))
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.hub.pending_commands), 1)

        # Unregister phone
        self.hub.unregister_phone(mock_ws)
        res = await task
        self.assertFalse(res["success"])
        self.assertEqual(res["error_code"], "PHONE_DISCONNECTED")
        self.assertEqual(len(self.hub.pending_commands), 0)


if __name__ == "__main__":
    unittest.main()
