import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from telegram_bot import TelegramBotService, load_telegram_config, save_telegram_config
from cloud.cloud_scheduler import CloudScheduler
from cloud_server import CloudPhoneHub


class MockPhoneHub:
    def __init__(self, connected: bool = True, fail_call: bool = False):
        self.is_connected = connected
        self.fail_call = fail_call
        self.calls_made = []

    async def call_phone(self, caller_name: str, reason: str):
        self.calls_made.append({"caller": caller_name, "reason": reason})
        if self.fail_call:
            return {"success": False, "error": "Simulated line busy"}
        return {"success": True, "call_id": "test_call_123"}


class TestTelegramBotIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.scheduler = CloudScheduler(storage_path=self.temp_file.name)
        self.notifications_received = []

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def test_split_message(self):
        svc = TelegramBotService()
        short_msg = "Hello World"
        self.assertEqual(svc._split_message(short_msg), [short_msg])

        long_msg = "Line\n" * 1000
        parts = svc._split_message(long_msg, limit=500)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), 500)

    def test_scheduler_failover_when_phone_offline(self):
        hub = MockPhoneHub(connected=False)
        failover_events = []

        def handle_failover(event_type, reminder, details):
            failover_events.append({
                "type": event_type,
                "reminder": reminder,
                "details": details,
            })

        self.scheduler.register_failover_handler(handle_failover)

        # Schedule reminder due immediately
        now_ts = time.time()
        rem = self.scheduler.schedule_call("in 1 minutes", "Offline phone test")
        # Force target_timestamp to past to simulate due reminder
        reminders = self.scheduler._load_reminders()
        reminders[0]["target_timestamp"] = now_ts - 5
        self.scheduler._save_reminders(reminders)

        async def run_one_loop_tick():
            task = asyncio.create_task(self.scheduler.start_loop(hub, brain=None))
            await asyncio.sleep(0.3)
            self.scheduler.stop()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_one_loop_tick())

        self.assertGreaterEqual(len(failover_events), 1)
        self.assertEqual(failover_events[0]["type"], "phone_disconnected")
        self.assertIn("Offline phone test", failover_events[0]["reminder"]["reason"])

    def test_scheduler_failover_when_call_fails(self):
        hub = MockPhoneHub(connected=True, fail_call=True)
        failover_events = []

        def handle_failover(event_type, reminder, details):
            failover_events.append({
                "type": event_type,
                "reminder": reminder,
                "details": details,
            })

        self.scheduler.register_failover_handler(handle_failover)

        now_ts = time.time()
        rem = self.scheduler.schedule_call("in 1 minutes", "Call busy test")
        reminders = self.scheduler._load_reminders()
        reminders[0]["target_timestamp"] = now_ts - 5
        self.scheduler._save_reminders(reminders)

        async def run_one_loop_tick():
            task = asyncio.create_task(self.scheduler.start_loop(hub, brain=None))
            await asyncio.sleep(0.3)
            self.scheduler.stop()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_one_loop_tick())

        self.assertGreaterEqual(len(failover_events), 1)
        self.assertEqual(failover_events[0]["type"], "call_failed")
        self.assertIn("Call busy test", failover_events[0]["reminder"]["reason"])

    def test_phone_hub_ringing_timeout(self):
        hub = CloudPhoneHub()
        events_emitted = []

        def handle_event(event_type, data):
            events_emitted.append({"type": event_type, "data": data})

        hub.register_call_event_handler(handle_event)

        # Register a call that started 40 seconds ago (exceeding 35s limit)
        call_id = "test_timeout_call"
        hub.active_calls[call_id] = {
            "call_id": call_id,
            "caller": "ARYA",
            "reason": "Unanswered test",
            "status": "ringing",
            "started_at": time.time() - 40.0,
        }

        asyncio.run(hub.check_ringing_timeouts())

        self.assertNotIn(call_id, hub.active_calls)
        self.assertEqual(len(events_emitted), 1)
        self.assertEqual(events_emitted[0]["type"], "call_unanswered")
        self.assertEqual(events_emitted[0]["data"]["reason"], "Unanswered test")

    def test_phone_hub_call_declined(self):
        hub = CloudPhoneHub()
        events_emitted = []

        def handle_event(event_type, data):
            events_emitted.append({"type": event_type, "data": data})

        hub.register_call_event_handler(handle_event)

        call_data = {"call_id": "c1", "reason": "Declined call test"}
        hub._emit_call_event("call_declined", call_data)

        self.assertEqual(len(events_emitted), 1)
        self.assertEqual(events_emitted[0]["type"], "call_declined")
        self.assertEqual(events_emitted[0]["data"]["reason"], "Declined call test")

    def test_telegram_command_bridge_cross_thread(self):
        """Verify cross-thread bridge from Telegram loop to server main_loop without loop errors."""
        import threading

        # Start a mock main_loop on a server background thread
        server_loop = asyncio.new_event_loop()
        server_thread = threading.Thread(target=server_loop.run_forever, daemon=True)
        server_thread.start()

        class MockBrain:
            is_running = True

            async def handle_text_command(self, text, wait_for_response=True, timeout=10.0):
                await asyncio.sleep(0.05)
                return f"Echo from main_loop: {text}"

        mock_brain = MockBrain()

        # Simulate Telegram thread running its own loop
        async def run_on_telegram_loop():
            fut = asyncio.run_coroutine_threadsafe(
                mock_brain.handle_text_command("Hello ARYA", wait_for_response=True, timeout=10.0),
                server_loop
            )
            return await asyncio.wrap_future(fut)

        telegram_result = asyncio.run(run_on_telegram_loop())
        server_loop.call_soon_threadsafe(server_loop.stop)

        self.assertEqual(telegram_result, "Echo from main_loop: Hello ARYA")


if __name__ == "__main__":
    unittest.main()
