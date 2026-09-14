"""
tests/test_contacts_manager.py — Unit & Integration Tests for Multi-Alias Contacts Manager
"""

import sys
import unittest
from pathlib import Path
import tempfile
import shutil

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloud.contacts_manager import (
    ContactsManager,
    ContactProfile,
    clean_phone_number,
)
from cloud.whatsapp_conversations import resolve_phone_number


class TestContactsManager(unittest.TestCase):

    def setUp(self):
        # Create an isolated temporary contacts manager instance for tests
        self.temp_dir = Path(tempfile.mkdtemp())
        self.patch_path = self.temp_dir / "test_contacts.json"

        # Create fresh manager
        self.mgr = ContactsManager()
        self.mgr._profiles.clear()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_phone_number(self):
        self.assertEqual(clean_phone_number("+91 98765 43210"), "919876543210")
        self.assertEqual(clean_phone_number("09876543210"), "09876543210")
        self.assertEqual(clean_phone_number("9876543210"), "919876543210")  # 10 digits -> 91 added
        self.assertEqual(clean_phone_number(""), "")

    def test_phone_sync_and_whatsapp_alias_merging(self):
        """
        Critical User Scenario:
        Saved in Android Contacts as 'Rahul', but on WhatsApp as 'Broski'.
        Must resolve to same phone number regardless of which name is used!
        """
        # 1. Android Companion app syncs phonebook
        raw_phone_contacts = [
            {"name": "Rahul", "phone": "+91 98765 43210"},
            {"name": "Mom", "phone": "+91 98765 00001"},
            {"name": "Vikram Work", "phone": "+91 98765 00002"},
        ]
        count = self.mgr.sync_phone_contacts(raw_phone_contacts)
        self.assertEqual(count, 3)

        # 2. WhatsApp gateway automatically learns WhatsApp chat push name 'Broski' for Rahul's number
        self.mgr.learn_whatsapp_contact("919876543210", "Broski")

        # 3. Verify Rahul's profile contains both aliases
        prof = self.mgr.resolve("Rahul")
        self.assertIsNotNone(prof)
        self.assertEqual(prof.phone, "919876543210")
        self.assertEqual(prof.phone_name, "Rahul")
        self.assertEqual(prof.whatsapp_name, "Broski")
        self.assertIn("rahul", prof.aliases)
        self.assertIn("broski", prof.aliases)

        # 4. Resolve by WhatsApp nickname 'Broski'
        prof_by_wa = self.mgr.resolve("Broski")
        self.assertIsNotNone(prof_by_wa)
        self.assertEqual(prof_by_wa.phone, "919876543210")

        # 5. Resolve by lowercase 'broski'
        self.assertEqual(self.mgr.resolve_phone("broski"), "919876543210")

    def test_voice_alias_addition(self):
        """Test teaching ARYA a nickname: 'Remember that Bhai is Rahul'"""
        self.mgr.sync_phone_contacts([{"name": "Rahul", "phone": "+91 98765 43210"}])

        success = self.mgr.add_alias(target="Rahul", alias="Bhai")
        self.assertTrue(success)

        # Calling 'Bhai' now resolves to Rahul's number!
        resolved = self.mgr.resolve_phone("Bhai")
        self.assertEqual(resolved, "919876543210")

    def test_word_boundary_matching(self):
        """Test matching 'Vikram' when saved as 'Vikram Work'"""
        self.mgr.sync_phone_contacts([{"name": "Vikram Work", "phone": "+91 98765 00002"}])

        prof = self.mgr.resolve("Vikram")
        self.assertIsNotNone(prof)
        self.assertEqual(prof.phone, "919876500002")

    def test_whatsapp_conversations_integration(self):
        """Test that resolve_phone_number() in whatsapp_conversations calls ContactsManager"""
        # Add profile to singleton
        from cloud.contacts_manager import get_contacts_manager
        singleton = get_contacts_manager()
        singleton.sync_phone_contacts([{"name": "Aman", "phone": "919999988888"}])
        singleton.learn_whatsapp_contact("919999988888", "Rockstar")

        # Resolve via whatsapp_conversations.py
        self.assertEqual(resolve_phone_number("Aman"), "919999988888")
        self.assertEqual(resolve_phone_number("Rockstar"), "919999988888")


if __name__ == "__main__":
    unittest.main()
