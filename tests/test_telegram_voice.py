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

    def test_pure_python_resampling(self):
        from cloud.telegram_voice_gateway import resample_24k_to_48k, resample_48k_to_16k
        import cloud.telegram_voice_gateway as tvg

        sample_24k = b"\x01\x00" * 240  # 480 bytes
        res_48k = resample_24k_to_48k(sample_24k)
        self.assertGreater(len(res_48k), 400)

        sample_48k = b"\x01\x00" * 480  # 960 bytes
        res_16k = resample_48k_to_16k(sample_48k)
        self.assertGreater(len(res_16k), 100)

        # Test pure python branch by mocking audioop as None
        orig_audioop = tvg.audioop
        try:
            tvg.audioop = None
            pure_48k = resample_24k_to_48k(sample_24k)
            self.assertEqual(len(pure_48k), len(sample_24k) * 2)
            pure_16k = resample_48k_to_16k(sample_48k)
            self.assertEqual(len(pure_16k), len(sample_48k) // 3)
        finally:
            tvg.audioop = orig_audioop

    def test_stereo_resampling_fidelity(self):
        from cloud.telegram_voice_gateway import (
            resample_24k_mono_to_48k_stereo,
            resample_48k_stereo_to_16k_mono,
        )

        # 1 second of 24kHz mono (24000 samples = 48000 bytes)
        mono_24k = b"\x10\x20" * 24000
        stereo_48k = resample_24k_mono_to_48k_stereo(mono_24k)
        # Should be exactly 4x bytes: 48000 samples * 2 channels * 2 bytes = 192,000 bytes (1 full second)
        self.assertEqual(len(stereo_48k), len(mono_24k) * 4)
        self.assertEqual(len(stereo_48k), 192000)

        # 1 second of 48kHz stereo (192000 bytes) downsampled to 16kHz mono
        # 16000 samples * 2 bytes = 32,000 bytes (1 full second)
        mono_16k = resample_48k_stereo_to_16k_mono(stereo_48k)
        self.assertEqual(len(mono_16k), 32000)

    def test_clear_output_buffer(self):
        gw = TelegramVoiceGateway.get_instance()
        gw.feed_output_audio(b"\x10\x00" * 480)
        with gw._audio_lock:
            self.assertGreater(len(gw._audio_out_buffer), 0)
        cleared = gw.clear_output_buffer()
        self.assertGreater(cleared, 0)
        with gw._audio_lock:
            self.assertEqual(len(gw._audio_out_buffer), 0)

    def test_calculate_rms(self):
        from cloud.telegram_voice_gateway import calculate_rms
        silence = b"\x00" * 1600
        self.assertEqual(calculate_rms(silence), 0)

        # High amplitude signal
        signal = b"\x00\x40" * 800
        self.assertGreater(calculate_rms(signal), 1000)


if __name__ == "__main__":
    unittest.main()


