"""
tests/test_whatsapp_session_sync.py — Unit tests for WhatsApp session persistence and CloudPhoneHub secret.
"""

import base64
import gzip
import os
import sqlite3
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloud.whatsapp_gateway import WhatsAppGateway


class TestWhatsAppSessionSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.session_db = self.temp_path / "whatsapp_session.db"

        # Create a real test SQLite DB
        conn = sqlite3.connect(str(self.session_db))
        conn.execute("CREATE TABLE test_session (id INT PRIMARY KEY, token TEXT);")
        conn.execute("INSERT INTO test_session VALUES (1, 'mock_token_12345');")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("cloud.whatsapp_gateway.SESSION_PATH")
    @patch("memory.supabase_memory.save_or_update_memory_supabase")
    def test_backup_session_to_supabase(self, mock_save, mock_path):
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = self.session_db.stat().st_size
        mock_path.read_bytes.return_value = self.session_db.read_bytes()
        mock_path.__str__.return_value = str(self.session_db)
        mock_save.return_value = True

        gw = WhatsAppGateway.get_instance()
        ok = gw.backup_session_to_supabase()
        self.assertTrue(ok)
        self.assertTrue(mock_save.called)
        args, kwargs = mock_save.call_args
        self.assertEqual(kwargs.get("category"), "system_session")
        self.assertEqual(kwargs.get("key_name"), "whatsapp_session")

        # Verify decoding the backup yields the original SQLite content
        encoded_val = kwargs.get("value")
        decompressed = gzip.decompress(base64.b64decode(encoded_val))
        self.assertEqual(decompressed, self.session_db.read_bytes())

    @patch("cloud.whatsapp_gateway.SESSION_PATH")
    @patch("cloud.whatsapp_gateway.SESSION_DIR")
    @patch("requests.get")
    @patch("memory.supabase_memory.get_supabase_credentials")
    def test_restore_session_from_supabase(self, mock_creds, mock_get, mock_dir, mock_path):
        mock_creds.return_value = ("https://mock.supabase.co", "mock-key")
        raw_db = self.session_db.read_bytes()
        compressed = gzip.compress(raw_db)
        encoded_val = base64.b64encode(compressed).decode("ascii")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"value": encoded_val, "updated_at": "2026-09-14"}]
        mock_get.return_value = mock_resp

        target_file = self.temp_path / "restored_session.db"
        mock_path.write_bytes.side_effect = lambda b: target_file.write_bytes(b)

        gw = WhatsAppGateway.get_instance()
        ok = gw.restore_session_from_supabase()
        self.assertTrue(ok)
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_bytes(), raw_db)

        # Confirm valid SQLite query on restored db
        conn = sqlite3.connect(str(target_file))
        cur = conn.cursor()
        cur.execute("SELECT token FROM test_session WHERE id = 1;")
        row = cur.fetchone()
        self.assertEqual(row[0], "mock_token_12345")
        conn.close()

    def test_phone_device_secret_persistence(self):
        from cloud_server import CloudPhoneHub
        hub1 = CloudPhoneHub()
        secret1 = hub1.device_secret
        self.assertTrue(len(secret1) >= 24)

        hub2 = CloudPhoneHub()
        secret2 = hub2.device_secret
        # Must be identical across instances / reboots!
        self.assertEqual(secret1, secret2)


if __name__ == "__main__":
    unittest.main()
