import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from cloud.cloud_scheduler import CloudScheduler, get_now_ist, format_ist_time, IST_TZ


class MockPhoneHub:
    def __init__(self, connected: bool = True):
        self.is_connected = connected
        self.calls_made = []

    async def call_phone(self, caller_name: str, reason: str):
        self.calls_made.append({"caller": caller_name, "reason": reason})
        return {"success": True, "call_id": "test_call_id"}


class TestCloudScheduler(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.scheduler = CloudScheduler(storage_path=self.temp_file.name)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def test_ist_time_format(self):
        now = get_now_ist()
        self.assertEqual(now.tzinfo, IST_TZ)
        formatted = format_ist_time(now)
        self.assertIn("IST", formatted)

    def test_parse_relative_time(self):
        parsed = self.scheduler.parse_time_to_ist("in 15 minutes")
        self.assertIsNotNone(parsed)
        now = get_now_ist()
        diff = (parsed - now).total_seconds()
        self.assertAlmostEqual(diff, 15 * 60, delta=5)

    def test_schedule_and_list_call(self):
        rem = self.scheduler.schedule_call("in 30 minutes", "Take vitamins")
        self.assertIn("id", rem)
        self.assertEqual(rem["status"], "pending")
        self.assertEqual(rem["reason"], "Take vitamins")

        active = self.scheduler.list_reminders(status="pending")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], rem["id"])

    def test_cancel_call(self):
        rem = self.scheduler.schedule_call("in 20 minutes", "Team meeting")
        cancelled = self.scheduler.cancel_reminder(rem["id"])
        self.assertTrue(cancelled)

        pending = self.scheduler.list_reminders(status="pending")
        self.assertEqual(len(pending), 0)

    def test_urgent_whatsapp_trigger(self):
        hub = MockPhoneHub(connected=True)
        coro = self.scheduler.check_urgent_message_alert(
            phone_hub=hub,
            sender="Alex (Boss)",
            message_text="URGENT: Production server down, please check immediately!"
        )
        res = asyncio.run(coro)
        self.assertTrue(res)
        self.assertEqual(len(hub.calls_made), 1)
        self.assertIn("Urgent", hub.calls_made[0]["caller"])
        self.assertIn("Production server down", hub.calls_made[0]["reason"])

    def test_parse_after_x_minutes(self):
        parsed = self.scheduler.parse_time_to_ist("after 5 minutes")
        self.assertIsNotNone(parsed)
        now = get_now_ist()
        diff = (parsed - now).total_seconds()
        self.assertAlmostEqual(diff, 5 * 60, delta=5)

        parsed_short = self.scheduler.parse_time_to_ist("2 mins")
        self.assertIsNotNone(parsed_short)
        diff_short = (parsed_short - now).total_seconds()
        self.assertAlmostEqual(diff_short, 2 * 60, delta=5)

    def test_deduplicate_schedule_call(self):
        rem1 = self.scheduler.schedule_call("in 10 minutes", "Drink water")
        rem2 = self.scheduler.schedule_call("in 10 minutes", "Drink water")
        self.assertEqual(rem1["id"], rem2["id"])
        all_reminders = self.scheduler.list_reminders()
        self.assertEqual(len(all_reminders), 1)

    def test_non_urgent_whatsapp_no_call(self):
        hub = MockPhoneHub(connected=True)
        coro = self.scheduler.check_urgent_message_alert(
            phone_hub=hub,
            sender="Friend",
            message_text="Hey, what are you doing this weekend?"
        )
        res = asyncio.run(coro)
        self.assertFalse(res)
        self.assertEqual(len(hub.calls_made), 0)


if __name__ == "__main__":
    unittest.main()
