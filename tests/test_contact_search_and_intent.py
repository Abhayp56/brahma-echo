"""
tests/test_contact_search_and_intent.py — Unit Tests for Contact Search, Fuzzy Matching & Intent Guardrails
"""

import unittest
from unittest.mock import MagicMock, patch

from cloud.contacts_manager import ContactsManager, ContactProfile
from core.tools_schema import TOOL_DECLARATIONS
from cloud.whatsapp_conversations import resolve_phone_number


class TestContactSearchAndFuzzyMatching(unittest.TestCase):

    def setUp(self):
        self.mgr = ContactsManager.get_instance()
        # Seed test contacts
        self.mgr._profiles.clear()
        self.mgr._upsert_contact(phone="918217576088", phone_name="Sumit")
        self.mgr._upsert_contact(phone="919876543210", phone_name="Prof. Sharma", aliases=["College Teacher"])
        self.mgr._upsert_contact(phone="919123456789", phone_name="Rahul Verma", whatsapp_name="Broski")
        self.mgr._upsert_contact(phone="919988776655", phone_name="Dr. Gupta", aliases=["Family Physician"])

    def test_exact_contact_search(self):
        matches = self.mgr.find_contacts("Sumit")
        self.assertTrue(len(matches) >= 1)
        self.assertEqual(matches[0]["name"], "Sumit")
        self.assertEqual(matches[0]["phone"], "918217576088")
        self.assertEqual(matches[0]["score"], 1.0)

    def test_fuzzy_honorific_matching_professor_sir(self):
        # User query 'professor sir' should match 'Prof. Sharma'
        matches = self.mgr.find_contacts("professor sir")
        self.assertTrue(len(matches) >= 1)
        self.assertEqual(matches[0]["phone"], "919876543210")
        self.assertEqual(matches[0]["name"], "Prof. Sharma")
        self.assertTrue(matches[0]["score"] >= 0.60)

    def test_resolve_with_fuzzy_query(self):
        prof = self.mgr.resolve("professor sir")
        self.assertIsNotNone(prof)
        self.assertEqual(prof.phone, "919876543210")
        self.assertEqual(prof.phone_name, "Prof. Sharma")

    def test_nickname_and_alias_search(self):
        # Searching 'bro' should find 'Broski'
        matches = self.mgr.find_contacts("bro")
        self.assertTrue(len(matches) >= 1)
        self.assertEqual(matches[0]["phone"], "919123456789")

    def test_nonexistent_contact_returns_empty(self):
        matches = self.mgr.find_contacts("NonExistentPersonXYZ99")
        self.assertEqual(len(matches), 0)

    def test_self_recipient_resolution(self):
        with patch("cloud.whatsapp_gateway.WhatsAppGateway.get_instance") as mock_gw:
            mock_gw.return_value.linked_phone = "919999988888"
            resolved = resolve_phone_number("me")
            self.assertEqual(resolved, "919999988888")

            resolved_boss = resolve_phone_number("boss")
            self.assertEqual(resolved_boss, "919999988888")

    def test_search_contact_schema_registered(self):
        search_schema = next((t for t in TOOL_DECLARATIONS if t.get("name") == "search_contact"), None)
        self.assertIsNotNone(search_schema, "search_contact schema must be registered in TOOL_DECLARATIONS")
        self.assertIn("query", search_schema["parameters"]["properties"])

        wa_schema = next((t for t in TOOL_DECLARATIONS if t.get("name") == "whatsapp_control"), None)
        self.assertIsNotNone(wa_schema)
        action_desc = wa_schema["parameters"]["properties"]["action"]["description"]
        self.assertIn("search_contact", action_desc)


if __name__ == "__main__":
    unittest.main()
