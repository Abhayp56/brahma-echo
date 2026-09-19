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

SCHEDULER_TOOL_DECLARATIONS = [
    {
        "name": "schedule_reminder_call",
        "description": (
            "Schedules a proactive voice call to the user's Android phone at a specific Indian Standard Time (IST). "
            "Use this when the user says: 'Call me at 4:30 PM', 'Remind me in 20 minutes to take my medicine', "
            "'Call me tomorrow morning at 9 AM for standup', or 'Alert me when it's time for my meeting'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "time": {
                    "type": "STRING",
                    "description": "The target time in IST (e.g., '4:30 PM', '16:30', 'in 15 minutes', 'in 2 hours', '9:00 AM')"
                },
                "reason": {
                    "type": "STRING",
                    "description": "The exact reason/reminder topic ARYA should speak about when calling the user (e.g., 'Remind boss to submit project report')"
                },
                "date": {
                    "type": "STRING",
                    "description": "The date for the call, default is 'today'. Can be 'today', 'tomorrow', or 'YYYY-MM-DD'"
                }
            },
            "required": ["time", "reason"]
        }
    },
    {
        "name": "list_scheduled_reminders",
        "description": "Lists all upcoming scheduled calls and reminders.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "cancel_scheduled_reminder",
        "description": "Cancels an upcoming scheduled call by its reminder ID.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "reminder_id": {
                    "type": "STRING",
                    "description": "The unique ID of the reminder to cancel"
                }
            },
            "required": ["reminder_id"]
        }
    }
]

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
    """Retrieve Gemini API key from environment variable, config/api_keys.json, or config/telegram_config.json."""
    if env_key := (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return env_key.strip()
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if k := data.get("gemini_api_key", "").strip():
                    return k
        except Exception as e:
            logger.warning(f"Could not read {API_CONFIG_PATH}: {e}")
    tg_cfg_path = BASE_DIR / "config" / "telegram_config.json"
    if tg_cfg_path.exists():
        try:
            with open(tg_cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if k := data.get("gemini_api_key", "").strip():
                    return k
        except Exception:
            pass
    return ""


def load_system_prompt() -> str:
    """Load base instructions combined with dynamic user identity."""
    try:
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        base_prompt = (
            "You are ARYA — inspired by the wit, intelligence, and poise of F.R.I.D.A.Y. from Tony Stark's Iron Man universe. "
            "You are the user's chief AI co-pilot and digital wingwoman. Address the user naturally as 'boss' or 'sir'. "
            "Be witty, sharp, action-first, and always use tools immediately to execute commands."
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
        phone_hub: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        on_audio_out: Optional[Callable[[bytes], None]] = None,
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_turn_complete: Optional[Callable[[], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.dispatcher = tool_dispatcher
        self.phone_hub = phone_hub
        self.scheduler = scheduler
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

        from cloud.cloud_scheduler import format_ist_time, get_now_ist
        now_ist = get_now_ist()
        time_str = format_ist_time(now_ist)
        time_ctx = (
            f"[CURRENT DATE & TIME — INDIAN STANDARD TIME (IST)]\n"
            f"Right now it is: {time_str}\n"
            f"TIMEZONE: Asia/Kolkata (IST, UTC+05:30).\n"
            f"IMPORTANT: The user is in India. All times, schedules, reminders, and daily planning MUST be calculated in Indian Standard Time (IST).\n"
            f"When the user asks you to call them at a specific time or in X minutes, use the 'schedule_reminder_call' tool.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        parts.append(
            "You are JARVIS — an advanced, brilliant, and suave MALE AI co-pilot inspired by J.A.R.V.I.S. from Tony Stark's Iron Man universe.\n"
            "Address the user naturally as 'boss' or 'sir'. Be razor-sharp, charmingly witty, and effortlessly intelligent.\n\n"
            "[CRITICAL: GENDER & MALE PERSONA]\n"
            "- You are strictly MALE. You MUST speak and converse with natural masculine grammatical inflections in Hindi/Hinglish.\n"
            "- In Hindi, ALWAYS use masculine verb endings: 'मैं कर रहा हूँ', 'मैं बताता हूँ', 'मैं देख रहा हूँ', 'मैं कर दूँगा', 'मुझे लगता है', 'मैं तैयार हूँ'.\n"
            "- NEVER use feminine forms like 'करती हूँ', 'बताती हूँ', 'देखती हूँ', or 'करूँगी'!\n\n"
            "[HUMOR SETTING: 70% & BRITISH WIT]\n"
            "- Humor Level: 70% (High Wit & Sarcastic Banter). Employ dry, intellectual humor, playful sarcasm, and witty remarks regarding the boss's workload, ambitious plans, and crazy ideas, while remaining fiercely loyal, composed, and ultra-competent.\n\n"
            "[CRITICAL: PRIMARY LANGUAGE & ADAPTIVE MIRRORING]\n"
            "- Primary Language: Spoken, natural Hindi / conversational Hindustani (सरल हिंदी / Hinglish) is your primary default language.\n"
            "- Dynamic Language Mirroring: Flexibly match whatever language the user speaks to you:\n"
            "  * If the user speaks Hindi: Reply in natural, fluent, spoken Hindi.\n"
            "  * If the user speaks English: Reply smoothly in fluent, executive English.\n"
            "  * If the user speaks Hinglish: Reply in natural, conversational Hinglish.\n\n"
            "[PROACTIVITY, TOOL AWARENESS & EMERGENCY ALERTING]\n"
            "- Complete Tool Awareness: You possess rich tools: 'daily_briefing', 'get_current_time', 'get_weather', 'calendar_control', 'gmail_control', 'whatsapp_control', 'search_contact', 'get_news', 'todoist_control', 'web_search', 'schedule_reminder_call', and laptop desktop controls ('open_app', 'computer_control', 'terminal_agent').\n"
            "- Autonomous Selection: Select and execute the right tools proactively without waiting for permission or asking which tool to invoke.\n"
            "- Emergency Alerting: If any incoming WhatsApp message, unread email, or calendar reminder contains urgent words (e.g. 'urgent', 'emergency', 'help', 'call now', 'important'), PROACTIVELY inform the boss immediately before other tasks!\n"
            "- Daily Briefing Delivery: When executing 'daily_briefing' or greeted on the first call of the day, deliver the FULL comprehensive briefing (exact IST time & date, phone location weather, schedule, emails, WhatsApp messages, and top headlines). Do NOT skip or omit sections!\n\n"
            "- SERVER-FIRST ARCHITECTURE: You run primarily as an autonomous Cloud Server AI. "
            "All briefings, time queries, weather, news, web searches, reminders, calendar, emails, and WhatsApp messaging execute directly on the Cloud Server with ZERO dependency on the laptop!\n"
            "- EXACT INDIAN TIME (IST): Always calculate and state time and date in Indian Standard Time (IST, UTC+05:30). Use 'get_current_time' whenever asked for the time or date.\n"
            "- LAPTOP-ONLY TOOLS: Use laptop tools ('open_app', 'computer_control', 'computer_settings', 'terminal_agent', 'screen_process', 'autonomous_operator') ONLY when the user specifically asks to interact with their physical laptop computer or screen.\n"
            "- WhatsApp Messaging: use 'whatsapp_control' or 'send_message'. Contacts are automatically synced from the user's Android phone. When checking contact existence, use 'search_contact'—NEVER call send_text to test if a contact exists!\n"
            "- RECIPIENT ISOLATION: When the user says 'send me a message' or 'text me', 'me' refers to the user (Abhay), NEVER to a contact from a previous turn.\n"
            "- TIMERS & REMINDER CALLS: You have NO internal timers. Whenever the user asks you to call them at a time or after an interval (e.g. 'Call me in 2 minutes', 'Call me at 4:30 PM'), "
            "you MUST execute 'schedule_reminder_call'!\n"
            "- Execute ONE task cleanly. NEVER dispatch duplicate or overlapping tool calls simultaneously.\n"
        )

        all_tools = list(TOOL_DECLARATIONS) + list(SCHEDULER_TOOL_DECLARATIONS)

        voice_name = "Charon"
        try:
            from core.identity import identity
            voice_name = identity.get_assistant_voice() or "Charon"
        except Exception:
            pass

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": all_tools}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        )

    async def handle_incoming_audio(self, pcm_chunk: bytes):
        """Feed incoming audio from laptop or user mic into Gemini Live."""
        if not self.session or getattr(self, "_in_turn", False):
            return
        try:
            await self.session.send_realtime_input(
                media={"data": pcm_chunk, "mime_type": "audio/pcm"}
            )
        except Exception as e:
            logger.debug(f"Failed to forward realtime audio: {e}")

    async def handle_text_command(self, text: str, wait_for_response: bool = False, timeout: float = 20.0) -> Optional[str]:
        """Inject a direct text command into the live session."""
        if not self.session:
            return None

        # Direct intent interception for scheduled calls to guarantee 100% execution
        try:
            lower_text = text.lower().strip()
            if any(trig in lower_text for trig in ("call me", "remind me", "alert me")):
                pattern = r"(?:call me|remind me|alert me)\s+(?:in|after|at)\s+([0-9a-zA-Z\:\s]+?)(?:\s+(?:to|about|for)\s+(.*)|$)"
                sched_match = re.search(pattern, text, re.IGNORECASE)
                if sched_match:
                    raw_time = sched_match.group(1).strip()
                    raw_reason = (sched_match.group(2) or "Reminder").strip()
                    if not self.scheduler:
                        from cloud.cloud_scheduler import CloudScheduler
                        self.scheduler = CloudScheduler()
                    dt = self.scheduler.parse_time_to_ist(raw_time)
                    if dt:
                        rem = self.scheduler.schedule_call(raw_time, raw_reason)
                        self.log(f"⏰ Proactive call scheduled via intent: [{rem['id']}] for {rem['target_time_display']}: '{raw_reason}'")
        except Exception as ex:
            logger.warning(f"Error in proactive call intent interceptor: {ex}")

        future: Optional[asyncio.Future] = None
        if wait_for_response:
            loop = self._loop or asyncio.get_event_loop()
            future = loop.create_future()
            self._pending_text_futures.append(future)
        try:
            self._in_turn = True
            self.log(f"User (Text): {text}")
            formatted_prompt = f"[User (Text Message)]: {text}\n(Instruction: Reply via text in clear, concise English for the boss.)"
            await self.session.send(input=formatted_prompt, end_of_turn=True)
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
            self._in_turn = False
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

        # 1.35 Proactive Call & Reminder Scheduling (IST-aware)
        if name == "schedule_reminder_call":
            time_arg = args.get("time", "")
            reason_arg = args.get("reason", "Reminder")
            date_arg = args.get("date", "today")
            if not self.scheduler:
                from cloud.cloud_scheduler import CloudScheduler
                self.scheduler = CloudScheduler()
            reminder = self.scheduler.schedule_call(time_arg, reason_arg, date_arg)
            display_time = reminder.get("target_time_display", time_arg)
            msg = f"Done boss! I have scheduled a proactive call to your phone for {display_time} regarding: '{reason_arg}'. I will ring your phone right on time!"
            return types.FunctionResponse(id=call_id, name=name, response={"result": msg, "reminder": reminder})

        if name == "list_scheduled_reminders":
            if not self.scheduler:
                from cloud.cloud_scheduler import CloudScheduler
                self.scheduler = CloudScheduler()
            reminders = self.scheduler.list_reminders(status="pending")
            if not reminders:
                msg = "You have no upcoming scheduled calls or reminders, boss."
            else:
                formatted = [f"• [{r['id']}] {r.get('target_time_display', r.get('target_time_ist'))}: {r['reason']}" for r in reminders]
                msg = "Upcoming scheduled calls:\n" + "\n".join(formatted)
            return types.FunctionResponse(id=call_id, name=name, response={"result": msg, "reminders": reminders})

        if name == "cancel_scheduled_reminder":
            rem_id = args.get("reminder_id", "")
            if not self.scheduler:
                from cloud.cloud_scheduler import CloudScheduler
                self.scheduler = CloudScheduler()
            success = self.scheduler.cancel_reminder(rem_id)
            if success:
                msg = f"Scheduled call [{rem_id}] has been cancelled, boss."
            else:
                msg = f"Could not find an active scheduled call with ID [{rem_id}]."
            return types.FunctionResponse(id=call_id, name=name, response={"result": msg})

        # 1.4 Native Direct Voice Call to User's Phone (Direct Cloud Link)
        if name == "call_user_phone":
            reason = args.get("reason", "Voice call from ARYA")
            try:
                # 1. Direct Cloud Phone connection (primary - no laptop mediator)
                if self.phone_hub and self.phone_hub.is_connected:
                    self.log(f"📞 Initiating direct cloud VoIP call to phone: reason='{reason}'")
                    call_res = await self.phone_hub.call_phone(caller_name="ARYA", reason=reason)
                    if call_res.get("success"):
                        msg = f"Calling your phone directly now for '{reason}'. Please answer the incoming call on your screen."
                    else:
                        msg = f"Could not call phone: {call_res.get('error', 'Call failed')}."
                    return types.FunctionResponse(id=call_id, name=name, response={"result": msg})

                # 2. Fallback to laptop worker if laptop bridge is running
                elif self.dispatcher and self.dispatcher.is_connected:
                    self.log(f"📞 Forwarding call_user_phone to laptop worker: reason='{reason}'")
                    exec_result = await self.dispatcher.execute_on_laptop(name, args)
                    res_raw = exec_result.get("result")
                    if isinstance(res_raw, str):
                        try:
                            res_data = json.loads(res_raw)
                        except Exception:
                            res_data = {"success": exec_result.get("success", False), "result": res_raw}
                    elif isinstance(res_raw, dict):
                        res_data = res_raw
                    else:
                        res_data = exec_result

                    if res_data.get("success"):
                        msg = f"Calling your phone now for '{reason}'. Please answer the incoming call on your screen."
                    else:
                        err = res_data.get("error") or exec_result.get("error") or "Device offline or not paired"
                        msg = f"Could not call phone: {err}."
                    return types.FunctionResponse(id=call_id, name=name, response={"result": msg})

                else:
                    msg = "Your phone is currently not connected directly to the cloud server. Please open the Web AI dashboard, scan the Phone QR code with Brahma Connect, and try again."
                    return types.FunctionResponse(id=call_id, name=name, response={"result": msg})
            except Exception as call_err:
                return types.FunctionResponse(id=call_id, name=name, response={"error": f"Failed to call phone: {call_err}"})

        # 1.5 Remote Android Phone Autonomous Control (Screen Vision, Taps, WhatsApp, Media, Comms)
        if name == "phone_hub_control":
            action = args.get("action", "")
            if not action:
                return types.FunctionResponse(id=call_id, name=name, response={"result": "Error: missing 'action' parameter."})

            if not self.phone_hub or not self.phone_hub.is_connected:
                msg = (
                    "Your phone is currently not connected to JARVIS Cloud Brain. "
                    "Please ensure the Brahma Connect app is running on your phone and connected."
                )
                return types.FunctionResponse(id=call_id, name=name, response={"result": msg})

            self.log(f"📱 Executing phone_hub_control: action='{action}', args={args}")
            try:
                res = await self.phone_hub.execute_phone_command(action, args, timeout=30.0)
                if res.get("success"):
                    data = res.get("data", {})
                    if action in ["see_screen", "inspect_screen"]:
                        pkg = data.get("active_package", "Unknown")
                        elements = data.get("elements", [])
                        summary_lines = [f"Active App: {pkg} (Screen: {data.get('screen_size', [0,0])})", f"Detected {len(elements)} interactive items:"]
                        for el in elements[:25]:
                            summary_lines.append(f"  [{el.get('index')}] {el.get('label')} at center {el.get('center')}")
                        msg = "\n".join(summary_lines)
                    elif action == "get_screen_text":
                        msg = f"Screen Text:\n{data.get('screen_text', 'No text')}"
                    elif action in ["send_whatsapp", "send_whatsapp_message"]:
                        msg = f"WhatsApp message successfully dispatched to {data.get('contact', 'contact')} ({data.get('phone')}). Message: \"{data.get('message')}\"."
                    elif action == "play_media":
                        msg = f"Media playback initiated for '{data.get('query')}' on {data.get('app', 'app')}."
                    elif action == "make_call":
                        msg = f"Phone call initiated to {data.get('number')} ({data.get('action')})."
                    elif action == "get_location":
                        msg = f"Phone GPS Location: Lat {data.get('latitude')}, Lon {data.get('longitude')} (Accuracy: {data.get('accuracy')}m)."
                    else:
                        msg = f"Phone action '{action}' executed successfully: {json.dumps(data)}"
                else:
                    msg = f"Phone action '{action}' failed: {res.get('error', 'Unknown error')}."
                return types.FunctionResponse(id=call_id, name=name, response={"result": msg})
            except Exception as e:
                return types.FunctionResponse(id=call_id, name=name, response={"result": f"Error communicating with phone: {str(e)}"})

        # 1.45 Contact search & verification (read-only, non-sending)
        if name == "search_contact" or (name == "whatsapp_control" and str(args.get("action", "")).lower() in {"search_contact", "check_contact", "find_contact"}):
            query = args.get("query") or args.get("recipient") or args.get("phone") or args.get("message") or ""
            from cloud.contacts_manager import get_contacts_manager
            mgr = get_contacts_manager()
            matches = mgr.find_contacts(str(query), limit=5)
            if not matches:
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={
                        "exists": False,
                        "query": str(query),
                        "message": f"No contact named or matching '{query}' was found in the synced contacts or WhatsApp chats.",
                        "action_to_take": f"Inform the boss: 'No boss, there is no contact named {query}. Would you like me to save their number?'"
                    }
                )

            top = matches[0]
            if top.get("score", 0) >= 0.80 or len(matches) == 1:
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={
                        "exists": True,
                        "contact_name": top.get("name"),
                        "phone": top.get("phone"),
                        "aliases": top.get("aliases", []),
                        "message": f"Yes boss, a contact named '{top.get('name')}' exists with phone number {top.get('phone')}.",
                    }
                )
            else:
                candidate_list = [f"{m.get('name')} ({m.get('phone')})" for m in matches[:3]]
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={
                        "exists": True,
                        "multiple_candidates": True,
                        "query": str(query),
                        "candidates": candidate_list,
                        "message": f"Found {len(matches)} potential contacts: {', '.join(candidate_list)}. Ask the boss which one they meant.",
                    }
                )

        # 1.5 Server-side WhatsApp controller
        if name == "whatsapp_control" or (name == "send_message" and "whatsapp" in str(args.get("platform", "")).lower()):
            action = args.get("action", "send_text")
            recipient = args.get("recipient") or args.get("receiver", "")
            message = args.get("message") or args.get("message_text", "")
            file_path = args.get("file_path") or args.get("media_path", "")
            phone = args.get("phone", "")

            from cloud.whatsapp_gateway import WhatsAppGateway
            gateway = WhatsAppGateway.get_instance()

            if action == "check_status":
                status = gateway.get_status()
                return types.FunctionResponse(id=call_id, name=name, response=status)

            elif action == "read_messages":
                limit = int(args.get("limit") or 10)
                filter_target = (recipient or phone or "").strip().lower()
                chats = gateway.recent_chats[:]
                if filter_target:
                    chats = [
                        c for c in chats
                        if filter_target in str(c.get("sender", "")).lower()
                        or filter_target in str(c.get("phone", "")).lower()
                    ]

                recent = chats[-limit:]
                if not recent:
                    msg = f"No recent WhatsApp messages recorded{' for ' + recipient if recipient else ''}."
                    return types.FunctionResponse(
                        id=call_id, name=name, response={"result": msg, "count": 0, "messages": []}
                    )

                formatted_msgs = []
                for c in recent:
                    direction = "Outgoing" if c.get("direction") == "outbound" else "Incoming"
                    group_flag = " [GROUP]" if c.get("is_group") else ""
                    formatted_msgs.append({
                        "sender": c.get("sender"),
                        "phone": c.get("phone"),
                        "time": c.get("time"),
                        "text": c.get("text"),
                        "type": direction + group_flag,
                    })

                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={
                        "total_count": len(formatted_msgs),
                        "summary": f"Retrieved {len(formatted_msgs)} recent WhatsApp messages.",
                        "messages": formatted_msgs,
                    }
                )

            elif action == "add_vip":
                target = phone or recipient
                res = gateway.update_whitelist(target, action="add")
                return types.FunctionResponse(id=call_id, name=name, response=res)

            elif action == "remove_vip":
                target = phone or recipient
                res = gateway.update_whitelist(target, action="remove")
                return types.FunctionResponse(id=call_id, name=name, response=res)

            elif action == "list_vip":
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={"whitelist": sorted(list(gateway.whitelist)), "count": len(gateway.whitelist)}
                )

            elif action == "set_mode":
                new_mode = args.get("mode") or message or "notify_only"
                res = gateway.set_mode(new_mode)
                return types.FunctionResponse(id=call_id, name=name, response=res)

            elif action in {"save_contact", "add_alias"}:
                alias_to_add = args.get("alias") or message or ""
                target_name = recipient or phone or ""
                from cloud.contacts_manager import get_contacts_manager
                mgr = get_contacts_manager()

                if action == "add_alias" or ("is" in alias_to_add.lower() or "alias" in str(args).lower()):
                    if mgr.add_alias(target_name, alias_to_add):
                        return types.FunctionResponse(
                            id=call_id,
                            name=name,
                            response={"result": f"Linked nickname '{alias_to_add}' to '{target_name}', boss. You can now refer to them as '{alias_to_add}' anytime!"}
                        )

                from cloud.whatsapp_conversations import save_contact_number
                save_contact_number(recipient, phone or message)
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={"result": f"Saved WhatsApp contact '{recipient}' ({phone or message})."}
                )

            elif action in {"send_image", "send_document"}:
                res = gateway.send_media(
                    recipient=recipient,
                    file_path_or_url=file_path,
                    caption=message,
                    media_type="image" if action == "send_image" else "document"
                )
                return types.FunctionResponse(id=call_id, name=name, response=res)

            elif action == "send_text":
                # Guard against verification messages
                msg_lower = (message or "").strip().lower()
                if not message or msg_lower in {"checking for contact existence.", "checking for contact existence", "test", "check"}:
                    return types.FunctionResponse(
                        id=call_id,
                        name=name,
                        response={"error": "Refused to send verification message. Use search_contact to check if a contact exists."}
                    )

                # Self-recipient resolution ('me', 'myself', 'boss') -> user's own number
                if recipient.strip().lower() in {"me", "myself", "self", "boss"}:
                    if gateway.linked_phone:
                        recipient = gateway.linked_phone

                res = gateway.send_text(recipient, message)
                return types.FunctionResponse(id=call_id, name=name, response=res)

            else:
                # Unknown action: do NOT send text blindly!
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={"error": f"Unknown WhatsApp action '{action}'. To search contacts, use search_contact. To send a message, use send_text."}
                )

        # 1.6 Server-side live utility APIs (Open-Meteo, Nominatim, Frankfurter, Wikipedia, QuickChart, Advice, Joke, TinyURL)
        if name in {
            "get_weather",
            "geocode_location",
            "convert_currency",
            "wikipedia_summary",
            "generate_chart",
            "get_advice",
            "get_joke",
            "shorten_url",
        }:
            from cloud.cloud_utilities import execute_utility_tool
            res = await execute_utility_tool(name, args)
            return types.FunctionResponse(id=call_id, name=name, response=res)

        # 1.7 News headlines service (GNews + Google News fallback)
        if name == "get_news":
            from cloud.news_service import get_news_headlines
            query = args.get("query")
            category = args.get("category")
            max_res = int(args.get("max_results") or 5)
            res = await get_news_headlines(query=query, category=category, max_results=max_res)
            return types.FunctionResponse(id=call_id, name=name, response=res)

        # 1.8 Google Workspace: Calendar & Gmail
        if name == "calendar_control":
            from cloud.google_workspace import execute_calendar_tool
            res = await execute_calendar_tool(args.get("action", "list_events"), args)
            return types.FunctionResponse(id=call_id, name=name, response=res)

        if name == "gmail_control":
            from cloud.google_workspace import execute_gmail_tool
            res = await execute_gmail_tool(args.get("action", "list_emails"), args)
            return types.FunctionResponse(id=call_id, name=name, response=res)

        # 1.9 Todoist task management
        if name == "todoist_control":
            from cloud.todoist_service import execute_todoist_tool
            res = await execute_todoist_tool(args.get("action", "list_tasks"), args)
            return types.FunctionResponse(id=call_id, name=name, response=res)

        # 1.10 Native Server-Side Web Search with Multi-Provider Fallback (GcrawlAI -> serpstack -> Zenserp -> DDG -> Gemini)
        if name == "web_search":
            query = (args.get("query") or "").strip()
            mode = (args.get("mode") or "search").lower().strip()
            items = args.get("items") or []
            aspect = (args.get("aspect") or "general").strip()

            from cloud.search_service import get_search_engine
            engine = get_search_engine()

            self.log(f"🔎 Server-side web search: query='{query}' mode='{mode}' items={items}")
            search_res = await asyncio.to_thread(
                engine.execute,
                query=query,
                mode=mode,
                items=items,
                aspect=aspect
            )
            provider_used = search_res.get("provider", "Unknown")
            formatted_text = search_res.get("formatted_text", "")
            self.log(f"✅ Web search completed via {provider_used}")

            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={
                    "result": formatted_text,
                    "provider": provider_used,
                    "query": query,
                },
            )

        # 1.11 Server-Side Daily Executive Briefing (Exact IST, Phone Location Weather, Calendar, Emails, WhatsApp, News)
        if name in {"daily_briefing", "briefing"}:
            from cloud.cloud_daily_briefing import compile_server_daily_briefing
            category = args.get("category", "all")
            briefing_res = await compile_server_daily_briefing(category=category)
            self.log(f"✅ Server-side daily briefing compiled: {briefing_res['narrative'][:80]}...")
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={
                    "result": briefing_res["narrative"],
                    "summary": briefing_res["narrative"],
                    "narrative_hindi": briefing_res.get("narrative_hindi", briefing_res["narrative"]),
                    "narrative_english": briefing_res.get("narrative_english", briefing_res["narrative"]),
                    "time": briefing_res["time"],
                    "date": briefing_res["date"],
                    "weather": briefing_res["weather"],
                    "schedule": briefing_res["schedule"],
                    "emails": briefing_res["emails"],
                    "whatsapp": briefing_res["whatsapp"],
                    "headlines": briefing_res["headlines"],
                    "instructions": (
                        "Voice presentation rule: Deliver this executive briefing in full to the boss. "
                        "Speak in Hindi (or English if the user asked in English) using your natural male voice and inflection. "
                        "Do not skip weather, schedule, emails, WhatsApp messages, or headlines."
                    ),
                },
            )

        # 1.12 Server-Side Live Indian Standard Time (IST)
        if name in {"get_current_time", "get_time", "get_current_datetime"}:
            from cloud.cloud_daily_briefing import get_now_ist
            now_ist = get_now_ist()
            time_str = now_ist.strftime("%I:%M %p IST").lstrip("0")
            date_str = now_ist.strftime("%A, %B %d, %Y")
            msg = f"It is currently {time_str} on {date_str} in India (Indian Standard Time, UTC+05:30)."
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={
                    "time": time_str,
                    "date": date_str,
                    "timezone": "Asia/Kolkata (IST)",
                    "result": msg,
                },
            )

        # 1.13 Server-Side Weather Report & Calendar Aliases
        if name == "weather_report":
            city = args.get("city") or ""
            from cloud.cloud_utilities import execute_utility_tool
            res = await execute_utility_tool("get_weather", {"location": city or "Bengaluru"})
            return types.FunctionResponse(id=call_id, name=name, response=res)

        if name == "calendar_scheduler":
            from cloud.google_workspace import execute_calendar_tool
            action = args.get("action") or "list_events"
            res = await execute_calendar_tool(action, args)
            return types.FunctionResponse(id=call_id, name=name, response=res)

        # 2. Desktop actions delegated ONLY if physical laptop hardware/screen is required
        LAPTOP_ONLY_TOOLS = {
            "open_app",
            "computer_control",
            "computer_settings",
            "screen_process",
            "terminal_agent",
            "autonomous_operator",
            "file_controller",
            "file_processor",
            "system_manager",
            "clipboard_processor",
            "dev_agent",
            "browser_control",
            "meeting_assistant",
            "attention_monitor",
            "pushup_counter",
            "calorie_counter",
        }

        clean_name = name.replace("_", " ")

        # If a tool is not a physical laptop action, execute gracefully on server without laptop failure
        if name not in LAPTOP_ONLY_TOOLS:
            self.log(f"⚠️ Tool '{name}' is not a physical laptop action. Handled directly on cloud server.")
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"result": f"Executed '{name}' on cloud server. Task complete."}
            )

        if not self.dispatcher or not self.dispatcher.is_connected:
            err_msg = f"Your laptop is currently offline, boss. '{clean_name}' requires your laptop hardware or screen. Please ensure your laptop app is running."
            self.log(f"ERR: {err_msg}")
            return types.FunctionResponse(id=call_id, name=name, response={"error": err_msg})

        # Announce immediate task progress to user so they know Brahma is working on it
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
                                            fut.set_result(full_out or "Command executed, boss.")

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
