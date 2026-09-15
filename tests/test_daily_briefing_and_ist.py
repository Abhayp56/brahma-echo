import unittest
import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock
from cloud.cloud_daily_briefing import (
    get_now_ist,
    save_phone_location,
    load_phone_location,
    compile_server_daily_briefing
)

class TestDailyBriefingAndIST(unittest.TestCase):
    def test_ist_now_timezone(self):
        now_ist = get_now_ist()
        self.assertIsNotNone(now_ist.tzinfo)
        # Verify UTC offset is +05:30 (19800 seconds)
        offset = now_ist.utcoffset()
        self.assertEqual(offset.total_seconds(), 19800)

    def test_format_ist_datetime(self):
        now_ist = get_now_ist()
        dt_str = now_ist.strftime("%A, %B %d, %Y, %I:%M %p IST")
        self.assertIn("IST", dt_str)

    def test_phone_location_save_load(self):
        loc = {
            "latitude": 12.9716,
            "longitude": 77.5946,
            "city": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
            "address": "MG Road, Bengaluru"
        }
        save_phone_location(loc)
        loaded = load_phone_location()
        self.assertEqual(loaded.get("city"), "Bengaluru")
        self.assertAlmostEqual(loaded.get("latitude"), 12.9716)

    @patch("cloud.cloud_daily_briefing._fetch_weather")
    def test_compile_server_daily_briefing(self, mock_weather):
        import asyncio
        async def fake_weather(loc):
            return "28°C, Clear in Bengaluru"
        mock_weather.side_effect = fake_weather

        res = asyncio.run(compile_server_daily_briefing("all"))
        self.assertTrue(res.get("success"))
        self.assertIn("IST", res.get("time", ""))
        self.assertIn("Bengaluru", res.get("narrative_hindi", ""))
        self.assertIn("मदद", res.get("narrative_hindi", ""))
        self.assertIn("What are your orders", res.get("narrative_english", ""))

if __name__ == "__main__":
    unittest.main()
