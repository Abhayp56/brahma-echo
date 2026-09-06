"""
End-to-End integration tests for Brahma Distributed Architecture
Tests Cloud Server WebSocket handshake, tool dispatching, and worker response.
"""

import asyncio
import json
import unittest
import websockets
from core.distributed.protocol import (
    ProtocolTypes,
    build_message,
    parse_message,
    new_request_id,
)
from cloud_server import app, dispatcher, server_config
import uvicorn
import socket


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestDistributedE2E(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.token = "test_auth_token_secret"
        server_config["auth_token"] = cls.token
        cls.config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(cls.config)

    async def asyncSetUp(self):
        # Start uvicorn server task in background
        self.server_task = asyncio.create_task(self.server.serve())
        # Give server a moment to start
        await asyncio.sleep(0.5)

    async def asyncTearDown(self):
        self.server.should_exit = True
        await asyncio.sleep(0.2)
        if not self.server_task.done():
            self.server_task.cancel()

    async def test_worker_auth_and_tool_execution(self):
        uri = f"ws://127.0.0.1:{self.port}/ws/node"

        async with websockets.connect(uri) as ws:
            # 1. Send AUTH
            auth = build_message(
                ProtocolTypes.AUTH,
                payload={"token": self.token, "device_name": "Test-Laptop"},
            )
            await ws.send(auth.to_json())

            # 2. Receive AUTH_ACK
            ack_raw = await ws.recv()
            ack = parse_message(ack_raw)
            self.assertEqual(ack.type, ProtocolTypes.AUTH_ACK)
            self.assertEqual(ack.payload.get("status"), "authenticated")
            self.assertTrue(dispatcher.is_connected)

            # 3. Simulate Cloud Brain dispatching a tool call to the laptop
            req_id = new_request_id()
            dispatch_coro = dispatcher.execute_on_laptop("test_echo_tool", {"foo": "bar"}, timeout=5.0)

            # Worker receives the execute_tool request
            worker_task = asyncio.create_task(dispatch_coro)
            exec_raw = await ws.recv()
            exec_msg = parse_message(exec_raw)
            self.assertEqual(exec_msg.type, ProtocolTypes.EXECUTE_TOOL)
            self.assertEqual(exec_msg.payload["tool_name"], "test_echo_tool")
            self.assertEqual(exec_msg.payload["args"], {"foo": "bar"})

            # Worker responds with TOOL_RESULT
            res = build_message(
                ProtocolTypes.TOOL_RESULT,
                payload={"success": True, "result": "Echo: bar", "error": None},
                request_id=exec_msg.request_id,
            )
            await ws.send(res.to_json())

            # Wait for dispatcher to receive and resolve the result
            result = await worker_task
            self.assertTrue(result["success"])
            self.assertEqual(result["result"], "Echo: bar")


if __name__ == "__main__":
    unittest.main()
