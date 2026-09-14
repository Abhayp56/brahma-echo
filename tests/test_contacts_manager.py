"""
tests/test_contacts_manager.py — Unit Tests for Multi-Alias Contact Resolution Engine
"""

import sys
import unittest
from pathlib import Path
import tempfile

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloud.contacts_manager import (
    clean_phone_number,
    ContactProfile,
    ContactsManager,
    get_contacts_manager,
)
from cloud.whatsapp_conversations import resolve_phone_number, save_contact_number, add_contact_alias


class TestContactsManager(unittest.TestCase):

    def setUp(self):
        # Create a temporary file for testing ContactsManager
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name) / "test_contacts.json"
        self.cm = ContactsManager(storage_path=self.tmp_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_phone_normalization(self):
        self.assertEqual(clean_phone_number("+91 98765 43210"), "919876543210")
        self.assertEqual(clean_phone_number("09876543210"), "919876543210")
        self.assertEqual(clean_phone_number("9876543210"), "919876543210")
        self.assertEqual(clean_phone_number("+1 (555) 123-4567", default_country_code=""), "15551234567")

    def test_user_scenario_rahul_and_broski_merge(self):
        """
        Tests the user's exact scenario:
        Saved in phonebook as 'Rahul', saved in WhatsApp as 'Broski'.
        Asking ARYA to message 'Broski' or 'Rahul' must resolve to the exact same number.
        """
        # 1. Contact from phonebook: Rahul
        self.cm.save_contact(
            phone="9876543210",
            name="Rahul",
            phone_name="Rahul",
        )

        # 2. Contact from WhatsApp chat: Broski (same phone number)
        self.cm.save_contact(
            phone="9876543210",
            whatsapp_name="Broski",
        )

        # 3. Verify single contact with merged names
        prof = self.cm.resolve("Broski")
        self.assertIsNotNone(prof)
        self.assertEqual(prof.phone, "919876543210")
        self.assertIn("rahul", prof.aliases)
        self.assertIn("broski", prof.aliases)

        # 4. Resolving by 'Rahul'
        prof_by_rahul = self.cm.resolve("Rahul")
        self.assertIsNotNone(prof_by_rahul)
        self.assertEqual(prof_by_rahul.phone, "919876543210")

        # 5. Resolving by lowercase 'broski'
        prof_lower = self.cm.resolve("broski")
        self.assertIsNotNone(prof_lower)
        self.assertEqual(prof_lower.phone, "919876543210")

    def test_add_alias_dynamically(self):
        self.cm.save_contact(phone="9876543210", name="Rahul")

        # User says: "Remember that Broski is Rahul"
        prof = self.cm.add_alias("Rahul", "Broski")
        self.assertIsNotNone(prof)
        self.assertIn("broski", prof.aliases)

        # Now search by 'Broski'
        res = self.cm.resolve("Broski")
        self.assertIsNotNone(res)
        self.assertEqual(res.phone, "919876543210")

    def test_auto_learn_whatsapp_pushname(self):
        # A message arrives from phone '919876500111' with Pushname 'Aman Tech'
        self.cm.auto_learn_whatsapp_chat("919876500111", "Aman Tech")

        # Can now resolve by 'Aman Tech' or 'Aman'
        res = self.cm.resolve("Aman Tech")
        self.assertIsNotNone(res)
        self.assertEqual(res.phone, "919876500111")

        # Substring / first name match
        res_sub = self.cm.resolve("Aman")
        self.assertIsNotNone(res_sub)
        self.assertEqual(res_sub.phone, "919876500111")

    def test_fuzzy_matching_stt_variation(self):
        """If voice-to-text hears 'Brosky' instead of 'Broski', it should still match."""
        self.cm.save_contact(phone="9876543210", name="Rahul", aliases=["broski"])
        res = self.cm.resolve("Brosky")
        self.assertIsNotNone(res)
        self.assertEqual(res.phone, "919876543210")

    def test_vcard_import(self):
        vcf_content = """
BEGIN:VCARD
VERSION:3.0
FN:Vikram Sharma
TEL;TYPE=CELL:+91 98111 22233
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Pooja Verma
TEL;TYPE=CELL:9822233344
END:VCARD
"""
        imported = self.cm.import_vcf_content(vcf_content)
        self.assertEqual(imported, 2)

        res1 = self.cm.resolve("Vikram Sharma")
        self.assertIsNotNone(res1)
        self.assertEqual(res1.phone, "919811122233")

        res2 = self.cm.resolve("Pooja")
        self.assertIsNotNone(res2)
        self.assertEqual(res2.phone, "919822233344")

    def test_whatsapp_conversations_integration(self):
        """Verify resolve_phone_number() uses ContactsManager."""
        cm = get_contacts_manager()
        cm.save_contact(phone="919999988888", name="Boss", aliases=["chief", "boss"])

        phone1 = resolve_phone_number("Boss")
        self.assertEqual(phone1, "919999988888")

        phone2 = resolve_phone_number("chief")
        self.assertEqual(phone2, "919999988888")

        # Test adding alias via whatsapp_conversations helper
        add_contact_alias("Boss", "sir")
        phone3 = resolve_phone_number("sir")
        self.assertEqual(phone3, "919999988888")


if __name__ == "__main__":
    unittest.main()
