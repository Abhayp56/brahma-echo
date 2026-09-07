"""
cloud/cloud_brain.py — Cloud Brain & Conversational Voice Engine

Houses the Gemini Multimodal Live API session, conversation state, memory,
and handles remote dispatching of desktop tools to connected laptop workers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai
from google.genai import types

from core.tools_schema import TOOL_DECLARATIONS
from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
    forget,
    search_memory,
)
from core.identity import identity

logger = logging.getLogger("CloudBrain")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"

LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1024


def get_api_key() -> str:
    """Retrieve Gemini API key from environment variable or config/api_keys.json."""
    if env_key := os.environ.get("GEMINI_API_KEY"):
        return env_key.strip()
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gemini_api_key", "").strip()
        except Exception as e:
            logger.warning(f"Could not read {API_CONFIG_PATH}: {e}")
    return ""


def load_system_prompt() -> str:
    """Load base instructions combined with dynamic user identity."""
    try:
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        base_prompt = (
            "You are ARYA, a calm, sharp, and professional AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

    try:
        ast_name = identity.get_assistant_name() or "ARYA"
        own_name = identity.get_owner_name() or "the user"
        role = identity.get_owner_role()
        mode = identity.get_behavior_mode()

        identity_str = f"You are {ast_name}. You are assisting {own_name}"
        if role:
            identity_str += f" (Role: {role}).\n"
        else:
            identity_str += ".\n"
        identity_str += f"Your current behavior mode is: {mode}.\n"

        custom = identity.get_custom_instructions()
        if custom:
            identity_str += f"Custom Instructions: {custom}\n\n"

        return identity_str + base_prompt
    except Exception:
        return base_prompt


class RemoteToolDispatcher:
    """Interface for dispatching actions to a connected laptop task worker."""

    async def execute_on_laptop(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool to connected laptop and awaits result."""
        raise NotImplementedError


class CloudBrain:
    """
    The Cloud Conversational Engine.
    Manages the live Gemini Multimodal connection, streams audio to/from users,
    and delegates desktop actions to connected laptop nodes.
    """

    def __init__(
        self,
        tool_dispatcher: Optional[RemoteToolDispatcher] = None,
        on_audio_out: Optional[Callable[[bytes], None]] = None,
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_turn_complete: Optional[Callable[[], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.dispatcher = tool_dispatcher
        self.on_audio_out = on_audio_out
        self.on_transcript = on_transcript
        self.on_turn_complete = on_turn_complete
        self.on_log = on_log or (lambda msg: logger.info(f"[BrainLog] {msg}"))

        self.session = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.audio_out_queue: asyncio.Queue = asyncio.Queue()
        self.is_running = False
        self.is_speaking = False
        self._pending_text_futures: List[asyncio.Future] = []

    def log(self, text: str):
        if self.on_log:
            self.on_log(text)

    def _build_live_config(self) -> types.LiveConnectConfig:
        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_prompt = load_system_prompt()

        now = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        parts.append(
            "You are ARYA, running as a Cloud Brain connected to the user's personal laptop.\n"
            "When the user asks you to open an application, check their screen, manipulate files, "
            "control the browser, or change computer settings, call the appropriate tool. "
            "The system will automatically forward the execution to their connected laptop.\n"
            "TOOL USAGE RULES:\n"
            "- Always use the most direct tool: 'open_app' to open programs, 'computer_control' to type or press hotkeys, "
            "'terminal_agent' for command line/PowerShell, 'browser_control' or 'web_search' for web browsing.\n"
            "- Use 'autonomous_operator' ONLY when explicitly asked for visual/autonomous navigation or when no direct tool exists.\n"
            "- Execute ONE task cleanly. NEVER dispatch duplicate, competing, or overlapping tool calls simultaneously.\n"
        )

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
        )

    async def handle_incoming_audio(self, pcm_chunk: bytes):
        """Feed incoming audio from laptop or user mic into Gemini Live."""
        if not self.session:
            return
        try:
            await self.session.send_realtime_input(
                media={"data": pcm_chunk, "mime_type": "audio/pcm"}
            )
        except Exception as e:
            logger.error(f"Failed to forward realtime audio: {e}")

    async def handle_text_command(self, text: str, wait_for_response: bool = False, timeout: float = 20.0) -> Optional[str]:
        """Inject a direct text command into the live session."""
        if not self.session:
            return None
        future: Optional[asyncio.Future] = None
        if wait_for_response:
            loop = self._loop or asyncio.get_event_loop()
            future = loop.create_future()
            self._pending_text_futures.append(future)
        try:
            self.log(f"User (Text): {text}")
            await self.session.send(input=text, end_of_turn=True)
            if future:
                try:
                    return await asyncio.wait_for(future, timeout=timeout)
                except asyncio.TimeoutError:
                    self.log("Timed out waiting for model turn complete.")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to send text input: {e}")
            return None
        finally:
            if future and future in self._pending_text_futures:
                self._pending_text_futures.remove(future)

    async def _execute_tool_call(self, fc) -> types.FunctionResponse:
        """Route tool call: process cloud-native tools locally, route desktop tools to laptop."""
        name = fc.name
        args = dict(fc.args or {})
        call_id = getattr(fc, "id", None) or getattr(fc, "call_id", None) or "call"

        self.log(f"🔧 Tool Request from Gemini: {name} (args: {args})")

        # 1. Cloud-native Memory tools (Supabase-backed & locally synced)
        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                self.log(f"💾 Memory saved: {category}/{key} = {value}")
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"result": f"Memory '{category}/{key}' saved successfully.", "silent": True},
            )

        if name == "update_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            new_value = args.get("new_value", "")
            if key and new_value:
                update_memory({category: {key: {"value": new_value}}})
                self.log(f"✏️ Memory updated: {category}/{key} = {new_value}")
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"result": f"Memory '{category}/{key}' updated to '{new_value}'.", "silent": True},
            )

        if name == "delete_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            if key:
                forget(key, category)
                self.log(f"🗑️ Memory deleted: {category}/{key}")
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"result": f"Memory '{category}/{key}' deleted.", "silent": True},
            )

        if name == "search_memory":
            query = args.get("query", "")
            results = search_memory(query)
            self.log(f"🔍 Memory searched for '{query}': found {len(results)} items")
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"results": results},
            )

        # 2. Desktop actions delegated to connected laptop worker
        if not self.dispatcher:
            err_msg = f"Cannot execute '{name}': No laptop worker dispatcher configured."
            self.log(f"ERR: {err_msg}")
            return types.FunctionResponse(id=call_id, name=name, response={"error": err_msg})

        # Announce immediate task progress to user so they know Brahma is working on it
        clean_name = name.replace("_", " ")
        if name == "open_app":
            target = args.get("app_name") or "the application"
            progress_msg = f"Opening {target} on your laptop..."
        elif name == "computer_control":
            action = args.get("action", "action")
            progress_msg = f"Executing {action} on your computer..."
        elif name == "browser_control":
            progress_msg = "Controlling the browser on your laptop..."
        elif name == "screen_process":
            progress_msg = "Inspecting your laptop screen..."
        elif name == "autonomous_operator":
            goal = args.get("goal") or "task"
            progress_msg = f"Starting autonomous vision operator for: {goal}..."
        elif name == "terminal_agent":
            cmd = args.get("command") or "command"
            progress_msg = f"Executing terminal engineer: {cmd[:40]}..."
        else:
            progress_msg = f"Working on {clean_name} on your laptop..."

        if self.on_transcript:
            self.on_transcript("task_progress", progress_msg)

        try:
            self.log(f"🚀 Dispatching '{name}' to connected laptop worker...")
            exec_result = await self.dispatcher.execute_on_laptop(name, args)
            success = exec_result.get("success", False)
            result_data = exec_result.get("result")
            error = exec_result.get("error")

            if success:
                response_payload = {"result": result_data or "Task completed on your laptop."}
                self.log(f"✅ Laptop executed '{name}': {result_data}")
            else:
                response_payload = {"error": error or "Laptop execution failed."}
                self.log(f"❌ Laptop reported error for '{name}': {error}")

            return types.FunctionResponse(id=call_id, name=name, response=response_payload)

        except Exception as exc:
            err = f"Failed to dispatch to laptop: {exc}"
            self.log(f"ERR: {err}")
            return types.FunctionResponse(id=call_id, name=name, response={"error": err})

    async def run(self):
        """Main lifecycle loop maintaining the Gemini Multimodal Live session."""
        self._loop = asyncio.get_event_loop()
        api_key = get_api_key()
        if not api_key:
            self.log("CRITICAL: No Gemini API Key found. Please configure GEMINI_API_KEY.")
            return

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        self.is_running = True

        while self.is_running:
            try:
                self.log(f"Connecting to Gemini Live API ({LIVE_MODEL})...")
                config = self._build_live_config()

                async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
                    self.session = session
                    self.log("🟢 Gemini Live API session connected and online.")

                    out_buf, in_buf = [], []
                    while True:
                        async for response in self.session.receive():
                            # Handle audio output from Gemini
                            if response.data:
                                if self.on_audio_out:
                                    self.on_audio_out(response.data)

                            # Handle transcriptions
                            if response.server_content:
                                sc = response.server_content
                                if sc.output_transcription and sc.output_transcription.text:
                                    txt = sc.output_transcription.text.strip()
                                    if txt:
                                        out_buf.append(txt)

                                if sc.model_turn and sc.model_turn.parts:
                                    for part in sc.model_turn.parts:
                                        if getattr(part, "text", None) and not getattr(part, "thought", False):
                                            p_txt = part.text.strip()
                                            if p_txt and p_txt not in out_buf:
                                                out_buf.append(p_txt)

                                if sc.input_transcription and sc.input_transcription.text:
                                    txt = sc.input_transcription.text.strip()
                                    if txt:
                                        in_buf.append(txt)

                                if sc.turn_complete:
                                    full_in = " ".join(in_buf).strip()
                                    if full_in:
                                        self.log(f"User: {full_in}")
                                        if self.on_transcript:
                                            self.on_transcript("user", full_in)
                                    in_buf = []

                                    full_out = " ".join(out_buf).strip()
                                    if full_out:
                                        self.log(f"Brahma: {full_out}")
                                        if self.on_transcript:
                                            self.on_transcript("assistant", full_out)
                                    out_buf = []

                                    # Resolve any waiting HTTP or RPC command callers
                                    for fut in list(self._pending_text_futures):
                                        if not fut.done():
                                            fut.set_result(full_out)

                                    if self.on_turn_complete and not response.tool_call:
                                        try:
                                            self.on_turn_complete()
                                        except Exception:
                                            pass

                            # Handle tool call requests from Gemini
                            if response.tool_call:
                                fn_responses = []
                                for fc in response.tool_call.function_calls:
                                    fr = await self._execute_tool_call(fc)
                                    fn_responses.append(fr)
                                await self.session.send_tool_response(function_responses=fn_responses)

            except Exception as exc:
                self.log(f"⚠️ Gemini Live disconnected: {exc}. Reconnecting in 5s...")
                self.session = None
                await asyncio.sleep(5)
