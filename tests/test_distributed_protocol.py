"""
Unit tests for core/distributed/protocol.py (compatible with standard unittest)
"""

import unittest
from core.distributed.protocol import (
    ProtocolTypes,
    MessageEnvelope,
    build_message,
    parse_message,
    new_request_id,
)


class TestDistributedProtocol(unittest.TestCase):
    def test_build_and_parse_message(self):
        req_id = new_request_id()
        payload = {"tool_name": "open_app", "args": {"app_name": "notepad"}}
        msg = build_message(ProtocolTypes.EXECUTE_TOOL, payload=payload, request_id=req_id)

        self.assertEqual(msg.type, ProtocolTypes.EXECUTE_TOOL)
        self.assertEqual(msg.request_id, req_id)
        self.assertEqual(msg.payload, payload)

        # Test serialization to JSON
        raw_json = msg.to_json()
        parsed = parse_message(raw_json)

        self.assertEqual(parsed.type, ProtocolTypes.EXECUTE_TOOL)
        self.assertEqual(parsed.request_id, req_id)
        self.assertEqual(parsed.payload["tool_name"], "open_app")
        self.assertEqual(parsed.payload["args"]["app_name"], "notepad")

    def test_auth_envelope(self):
        auth_msg = build_message(
            ProtocolTypes.AUTH,
            payload={"token": "test_token_123", "device_name": "My-PC"},
        )
        self.assertEqual(auth_msg.type, "auth")
        dict_repr = auth_msg.to_dict()
        self.assertEqual(dict_repr["payload"]["token"], "test_token_123")

        parsed = parse_message(dict_repr)
        self.assertEqual(parsed.payload["device_name"], "My-PC")

    def test_tool_result_envelope(self):
        res_msg = build_message(
            ProtocolTypes.TOOL_RESULT,
            payload={"success": True, "result": "Opened notepad.", "error": None},
        )
        raw = res_msg.to_json()
        parsed = parse_message(raw)
        self.assertEqual(parsed.type, ProtocolTypes.TOOL_RESULT)
        self.assertTrue(parsed.payload["success"])
        self.assertEqual(parsed.payload["result"], "Opened notepad.")


if __name__ == "__main__":
    unittest.main()
