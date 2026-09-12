import asyncio
import json
import sys
from pathlib import Path
import unittest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from cloud_server import CloudPhoneHub


class TestCloudPhoneHub(unittest.TestCase):
    def setUp(self):
        self.hub = CloudPhoneHub()

    def test_pairing_offer_creation(self):
        offer = self.hub.create_pairing_offer("brahma-cloud-brain.onrender.com")
        self.assertEqual(offer["service"], "BrahmaCloud")
        self.assertEqual(offer["url"], "wss://brahma-cloud-brain.onrender.com/ws/phone")
        self.assertTrue(offer["ssl"])
        self.assertEqual(offer["port"], 443)
        self.assertTrue(len(offer["pairing_token"]) > 0)
        self.assertTrue(len(offer["pairing_code"]) == 6)

    def test_local_pairing_offer_creation(self):
        offer = self.hub.create_pairing_offer("127.0.0.1:8000")
        self.assertEqual(offer["url"], "ws://127.0.0.1:8000/ws/phone")
        self.assertFalse(offer["ssl"])

    def test_qr_data_url_generation(self):
        qr_url = self.hub.generate_qr_data_url("brahma-cloud-brain.onrender.com")
        self.assertTrue(qr_url.startswith("data:image/png;base64,"))
        self.assertTrue(len(qr_url) > 100)

    def test_call_phone_when_disconnected(self):
        async def _test():
            res = await self.hub.call_phone("ARYA", "Test Call")
            self.assertFalse(res["success"])
            self.assertIn("not connected", res["error"])
        asyncio.run(_test())

    def test_call_lifecycle(self):
        async def _test():
            # Mock a connected websocket
            class MockWebSocket:
                def __init__(self):
                    self.sent_messages = []
                async def send_text(self, text):
                    self.sent_messages.append(json.loads(text))

            mock_ws = MockWebSocket()
            self.hub.register_phone(mock_ws, {"device_name": "Test Pixel 8", "platform": "android"})
            self.assertTrue(self.hub.is_connected)

            # Initiate call
            call_res = await self.hub.call_phone("ARYA", "Briefing test")
            self.assertTrue(call_res["success"])
            call_id = call_res["call_id"]
            self.assertIn(call_id, self.hub.active_calls)
            self.assertEqual(self.hub.active_calls[call_id]["status"], "ringing")

            # Verify message sent to phone
            self.assertEqual(len(mock_ws.sent_messages), 1)
            offer_msg = mock_ws.sent_messages[0]
            self.assertEqual(offer_msg["type"], "call_offer")
            self.assertEqual(offer_msg["payload"]["call_id"], call_id)

            # End call
            end_res = await self.hub.end_call(call_id)
            self.assertTrue(end_res["success"])
            self.assertNotIn(call_id, self.hub.active_calls)

            # Unregister
            self.hub.unregister_phone()
            self.assertFalse(self.hub.is_connected)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
