import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import unittest
from cloud.telegram_voice_gateway import TelegramVoiceGateway
from core.tools_schema import TOOL_DECLARATIONS


class TestTelegramVoiceGateway(unittest.TestCase):
    def test_gateway_configuration_loaded(self):
        gw = TelegramVoiceGateway.get_instance()
        self.assertIsNotNone(gw.api_id, "Telegram api_id must be loaded")
        self.assertEqual(gw.api_id, 32041635)
        self.assertIsNotNone(gw.api_hash, "Telegram api_hash must be loaded")
        self.assertIsNotNone(gw.session_string, "Telegram session_string must be loaded")
        self.assertTrue(gw.is_configured, "Gateway must report is_configured = True")
        self.assertEqual(gw.target_group_id, -1004215913257)

    def test_gateway_status_structure(self):
        gw = TelegramVoiceGateway.get_instance()
        status = gw.get_status()
        self.assertIn("status", status)
        self.assertIn("is_configured", status)
        self.assertIn("in_call", status)
        self.assertIn("group_id", status)
        self.assertIn("group_title", status)
        self.assertTrue(status["is_configured"])
        self.assertEqual(status["group_id"], -1004215913257)

    def test_tool_declaration_registered(self):
        tg_tool = next((t for t in TOOL_DECLARATIONS if t.get("name") == "telegram_call"), None)
        self.assertIsNotNone(tg_tool, "telegram_call must be registered in TOOL_DECLARATIONS")
        self.assertIn("action", tg_tool["parameters"]["properties"])
        desc = tg_tool["description"]
        self.assertIn("Telegram", desc)
        self.assertIn("voice call", desc.lower())

    def test_audio_buffering_and_resampling(self):
        gw = TelegramVoiceGateway.get_instance()
        # Feed 240 samples of 24kHz 16-bit PCM audio (480 bytes)
        fake_24k_pcm = b"\x00\x01" * 240
        gw.feed_output_audio(fake_24k_pcm)
        
        # Audio buffer should now contain 48kHz audio (approx double length)
        with gw._audio_lock:
            buf_len = len(gw._audio_out_buffer)
            self.assertGreater(buf_len, 0)
            # Clear buffer after test
            gw._audio_out_buffer.clear()


if __name__ == "__main__":
    unittest.main()
