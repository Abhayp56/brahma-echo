"""
Tests for God's Eye View Tactical Reconnaissance Integration into ARYA.
Validates:
1. Tool schema in core/tools_schema.py
2. Tool execution in cloud/cloud_brain.py
3. Broadcast mechanism in cloud_server.py
4. Web UI markup and bridge integration
"""
import unittest
import json
import os
from unittest.mock import MagicMock, patch

from core.tools_schema import TOOL_DECLARATIONS


class TestGodsEyeIntegration(unittest.TestCase):

    def test_tool_schema_registration(self):
        """Verify that gods_eye_control tool is registered in TOOL_DECLARATIONS."""
        tool_names = [t["name"] for t in TOOL_DECLARATIONS if "name" in t]
        self.assertIn("gods_eye_control", tool_names)

        gev_tool = next(t for t in TOOL_DECLARATIONS if t.get("name") == "gods_eye_control")
        self.assertIn("parameters", gev_tool)
        self.assertIn("action", gev_tool["parameters"]["properties"])
        self.assertIn("query", gev_tool["parameters"]["properties"])

    def test_cloud_brain_gev_action_callback(self):
        """Verify that CloudBrain executes gods_eye_control and triggers on_gev_action callback."""
        import asyncio
        from cloud.cloud_brain import CloudBrain

        received_actions = []

        def mock_on_gev(action, args):
            received_actions.append({"action": action, "args": args})

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key_for_test"}):
            brain = CloudBrain(on_gev_action=mock_on_gev)
            
            mock_fc = MagicMock()
            mock_fc.name = "gods_eye_control"
            mock_fc.args = {"action": "fly_to", "query": "Tokyo"}
            mock_fc.id = "test_call_1"

            result = asyncio.run(brain._execute_tool_call(mock_fc))

            self.assertEqual(result.name, "gods_eye_control")
            self.assertEqual(len(received_actions), 1)
            self.assertEqual(received_actions[0]["action"], "fly_to_location")
            self.assertEqual(received_actions[0]["args"]["query"], "Tokyo")

    def test_web_ui_has_tactical_recon(self):
        """Verify cloud/web_ui.html contains Tactical Recon button, modal, and event handling."""
        web_ui_path = os.path.join(os.path.dirname(__file__), "..", "cloud", "web_ui.html")
        self.assertTrue(os.path.exists(web_ui_path))

        with open(web_ui_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("openTacticalBtn", content)
        self.assertIn("tacticalModal", content)
        self.assertIn("gevIframe", content)
        self.assertIn("/tactical", content)
        self.assertIn("gev_action", content)
        self.assertIn("forwardGevActionToIframe", content)

    def test_cloud_server_tactical_proxy_routes(self):
        """Verify cloud_server.py registers tactical reverse-proxy endpoints."""
        import cloud_server
        self.assertTrue(hasattr(cloud_server, "start_gev_background_process"))
        self.assertTrue(hasattr(cloud_server, "proxy_to_gev"))
        self.assertTrue(hasattr(cloud_server, "tactical_status"))

        routes = [r.path for r in cloud_server.app.routes]
        self.assertIn("/tactical", routes)
        self.assertIn("/tactical/{path:path}", routes)
        self.assertIn("/api/tactical-status", routes)

    def test_arya_bridge_exists_in_gev(self):
        """Verify aryaBridge.js exists and is imported in GEV src/main.js."""
        bridge_path = os.path.join(os.path.dirname(__file__), "..", "gods-eye-view-main", "src", "aryaBridge.js")
        main_js_path = os.path.join(os.path.dirname(__file__), "..", "gods-eye-view-main", "src", "main.js")

        self.assertTrue(os.path.exists(bridge_path))
        with open(bridge_path, "r", encoding="utf-8") as f:
            bridge_content = f.read()
        self.assertIn("initAryaBridge", bridge_content)
        self.assertIn("gev_action", bridge_content)

        with open(main_js_path, "r", encoding="utf-8") as f:
            main_content = f.read()
        self.assertIn("initAryaBridge", main_content)


if __name__ == "__main__":
    unittest.main()
