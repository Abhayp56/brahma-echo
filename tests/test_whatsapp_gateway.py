import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import unittest
from cloud.whatsapp_conversations import (
    clean_phone_number,
    resolve_phone_number,
    save_contact_number,
)
from cloud.whatsapp_gateway import WhatsAppGateway
from core.tools_schema import TOOL_DECLARATIONS


class TestWhatsAppGateway(unittest.TestCase):
    def test_phone_number_cleaning(self):
        # Formatted with + and spaces
        self.assertEqual(clean_phone_number("+91 98765 43210"), "919876543210")
        
        # Formatted with dashes
        self.assertEqual(clean_phone_number("+1-800-555-0199"), "18005550199")
        
        # Already digits
        self.assertEqual(clean_phone_number("919876543210"), "919876543210")

    def test_contact_saving_and_resolution(self):
        # Save a test contact
        save_contact_number("TestMom", "+91 98765 00001")
        
        # Resolve by name
        resolved = resolve_phone_number("TestMom")
        self.assertEqual(resolved, "919876500001")
        
        # Resolve by direct number
        resolved_num = resolve_phone_number("+91 98765 00001")
        self.assertEqual(resolved_num, "919876500001")

    def test_gateway_modes_and_status(self):
        gw = WhatsAppGateway.get_instance()
        status = gw.get_status()
        self.assertIn("status", status)
        self.assertIn("mode", status)
        self.assertIn("whitelist_count", status)

        # Test mode change
        res = gw.set_mode("whitelist")
        self.assertTrue(res["success"])
        self.assertEqual(gw.mode, "whitelist")

        # Test invalid mode
        res_invalid = gw.set_mode("invalid_mode")
        self.assertFalse(res_invalid["success"])

        # Test whitelist additions
        res_wl = gw.update_whitelist("919876543210", action="add")
        self.assertTrue(res_wl["success"])
        self.assertIn("919876543210", gw.whitelist)

        # Remove from whitelist
        res_rm = gw.update_whitelist("919876543210", action="remove")
        self.assertTrue(res_rm["success"])
        self.assertNotIn("919876543210", gw.whitelist)

        # Reset mode to notify_only
        gw.set_mode("notify_only")

    def test_whatsapp_tool_schema_registered(self):
        wa_schema = next((t for t in TOOL_DECLARATIONS if t.get("name") == "whatsapp_control"), None)
        self.assertIsNotNone(wa_schema, "whatsapp_control schema must be registered in TOOL_DECLARATIONS")
        self.assertIn("action", wa_schema["parameters"]["properties"])
        self.assertIn("recipient", wa_schema["parameters"]["properties"])


if __name__ == "__main__":
    unittest.main()
