"""
telegram_bot.py — ARYA / Brahma Echo Telegram Bot Service

Provides bidirectional conversational access to ARYA via Telegram:
1. Chat & Tool Execution: Dispatches user requests to CloudBrain or Desktop agent,
   or processes them directly with Gemini 2.5 Flash tool-calling.
2. Proactive Alerts: Sends notifications when phone calls fail, ring out, or are declined.
3. Auto-Pairing: Automatically links the owner on /start.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from telegram import Bot, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from google import genai
from google.genai import types

logger = logging.getLogger("brahma_echo.telegram")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config" / "telegram_config.json"
API_KEYS_FILE = BASE_DIR / "config" / "api_keys.json"


def _load_json_file(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning(f"Could not load {path}: {exc}")
    return {}


def _save_json_file(path: Path, data: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.error(f"Could not save {path}: {exc}")


def load_telegram_config() -> dict:
    cfg = _load_json_file(CONFIG_FILE)
    # Allow environment variable overrides
    if env_token := os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg["bot_token"] = env_token.strip()
    if env_chat_id := os.environ.get("TELEGRAM_CHAT_ID"):
        cfg["chat_id"] = env_chat_id.strip()
    return cfg


def save_telegram_config(updates: dict):
    current = _load_json_file(CONFIG_FILE)
    current.update(updates)
    _save_json_file(CONFIG_FILE, current)


def _load_api_keys() -> dict:
    return _load_json_file(API_KEYS_FILE)


def _get_gemini_api_key() -> str:
    """Multi-tier Gemini API key resolution: Env Var -> config/api_keys.json -> config/telegram_config.json."""
    if env_key := (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return env_key.strip()
    keys = _load_api_keys()
    if k := (keys.get("gemini_api_key") or "").strip():
        return k
    tg_cfg = load_telegram_config()
    if k := (tg_cfg.get("gemini_api_key") or "").strip():
        return k
    return ""



def _get_openrouter_api_key() -> str:
    """Multi-tier OpenRouter API key resolution: Env Var -> config/api_keys.json -> config/telegram_config.json."""
    if env_key := os.environ.get("OPENROUTER_API_KEY"):
        return env_key.strip()
    keys = _load_api_keys()
    if k := (keys.get("openrouter_api_key") or "").strip():
        return k
    tg_cfg = load_telegram_config()
    if k := (tg_cfg.get("openrouter_api_key") or "").strip():
        return k
    return ""


class TelegramBotService:
    """
    Persistent Telegram Bot Service for Brahma Echo / ARYA.
    Runs asynchronously on its own event loop in a background daemon thread.
    """

    _instance: Optional[TelegramBotService] = None

    @classmethod
    def get_instance(cls) -> TelegramBotService:
        if cls._instance is None:
            cls._instance = TelegramBotService()
        return cls._instance

    def __init__(
        self,
        *,
        status_callback: Optional[Callable[[str], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self._status_callback = status_callback or (lambda *_: None)
        self._log_callback = log_callback or (lambda *_: None)
        self._command_handler: Optional[Callable[[str], Any]] = None
        self._app_submitter: Optional[Callable[[str, str], None]] = None
        self._token = ""
        self._chat_id: Optional[str] = None
        self._allowed_chat_ids: Set[str] = set()

        self._app: Optional[Application] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stopping = False
        self._bot_username: str = ""
        self._remote_dispatcher: Optional[Any] = None
        self._remote_dispatcher_loop: Optional[asyncio.AbstractEventLoop] = None

        self._load_config()

    def bind_remote_dispatcher(self, dispatcher: Any, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Inject a remote tool dispatcher (WebSocketToolDispatcher on Cloud Server)."""
        self._remote_dispatcher = dispatcher
        self._remote_dispatcher_loop = loop

    def _load_config(self):
        cfg = load_telegram_config()
        self._token = (cfg.get("bot_token") or "").strip()
        cid = str(cfg.get("chat_id") or "").strip()
        self._chat_id = cid if cid else None
        allowed = cfg.get("allowed_chat_ids") or []
        self._allowed_chat_ids = {str(x).strip() for x in allowed if str(x).strip()}
        if self._chat_id:
            self._allowed_chat_ids.add(self._chat_id)

    @property
    def bot_token(self) -> str:
        return self._token

    @property
    def chat_id(self) -> Optional[str]:
        return self._chat_id

    @property
    def bot_username(self) -> str:
        return self._bot_username

    def bind_command_handler(self, handler: Callable[[str], Any]):
        """Inject a high-level command handler (e.g. CloudBrain.handle_text_command)."""
        self._command_handler = handler

    def bind_app_submitter(self, submitter: Callable[[str, str], None]):
        """Inject local desktop command submitter (ui.py submit_command)."""
        self._app_submitter = submitter

    def is_running(self) -> bool:
        return bool(self._app and self._loop and self._loop.is_running() and not self._stopping)

    def _emit_status(self, msg: str):
        try:
            self._status_callback(msg)
        except Exception:
            pass

    def _emit_log(self, msg: str):
        try:
            self._log_callback(msg)
        except Exception:
            pass

    def start(self, token: Optional[str] = None):
        """Starts the Telegram bot service in a background daemon thread."""
        with self._lock:
            if token:
                self._token = token.strip()
            if not self._token:
                self._load_config()

            if not self._token:
                logger.warning("Cannot start Telegram Bot: bot_token is missing.")
                self._emit_status("Telegram bot: No token configured.")
                return

            if self.is_running():
                logger.info("Telegram bot already running.")
                return

            self._stopping = False
            self._thread = threading.Thread(
                target=self._run_thread,
                name="TelegramBotThread",
                daemon=True,
            )
            self._thread.start()
            self._emit_status("Connecting Telegram bot...")

    def stop(self):
        """Stops the Telegram bot service."""
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            thread = self._thread
            self._thread = None

        if thread is not None and thread.is_alive():
            thread.join(timeout=8)

        self._emit_status("Telegram bot stopped.")

    def _run_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main_loop())
        except Exception as exc:
            logger.exception("Telegram bot thread crashed")
            self._emit_status(f"Telegram error: {exc}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _main_loop(self):
        app = Application.builder().token(self._token).build()
        self._app = app

        # Register handlers
        app.add_handler(CommandHandler("start", self._handle_start))
        app.add_handler(CommandHandler("help", self._handle_help))
        app.add_handler(CommandHandler("status", self._handle_status))
        app.add_handler(CommandHandler("briefing", self._handle_briefing))
        app.add_handler(CommandHandler("reminders", self._handle_reminders))
        app.add_handler(CommandHandler("time", self._handle_time))
        app.add_handler(CommandHandler("cancel", self._handle_cancel))
        app.add_handler(CommandHandler("key", self._handle_key))
        app.add_handler(CommandHandler("forge", self._handle_forge))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        await app.initialize()
        await app.start()

        try:
            bot_user = await app.bot.get_me()
            self._bot_username = bot_user.username or ""
            status_msg = f"Telegram bot online as @{bot_user.username}"
            logger.info(f"✅ {status_msg}")
            self._emit_status(status_msg)
            self._emit_log(f"SYS: {status_msg}")
        except Exception as exc:
            logger.warning(f"Could not retrieve bot username: {exc}")

        # Start polling updates
        updater = app.updater
        if updater is None:
            await app.start()
            return

        await updater.start_polling(drop_pending_updates=True)

        try:
            while not self._stopping:
                await asyncio.sleep(0.5)
        finally:
            try:
                if updater and updater.running:
                    await updater.stop()
            except Exception:
                pass
            try:
                if app.running:
                    await app.stop()
            except Exception:
                pass
            try:
                await app.shutdown()
            except Exception:
                pass
            self._app = None

    # ─────────────────────────────────────────────────────────────────────────
    # Outbound Messaging & Notification API
    # ─────────────────────────────────────────────────────────────────────────

    def send_notification(
        self,
        text: str,
        chat_id: Optional[int | str] = None,
        parse_mode: Optional[str] = ParseMode.MARKDOWN,
    ) -> bool:
        """
        Thread-safe method to send an outbound notification / alert to the user.
        Can be called from CloudScheduler, PhoneHub, or external triggers.
        """
        target = str(chat_id or self._chat_id or "").strip()
        if not target:
            logger.warning("Cannot send Telegram notification: No target chat_id configured.")
            return False

        if not self._app or not self._loop or not self._loop.is_running():
            logger.warning("Cannot send Telegram notification: Bot loop is not running.")
            return False

        try:
            coro = self._send_notification_async(target, text, parse_mode=parse_mode)
            asyncio.run_coroutine_threadsafe(coro, self._loop)
            return True
        except Exception as exc:
            logger.error(f"Failed to schedule Telegram notification: {exc}")
            return False

    async def _send_notification_async(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = ParseMode.MARKDOWN,
    ):
        if not self._app or not text:
            return
        bot = self._app.bot
        chunks = self._split_message(text, limit=4000)

        for chunk in chunks:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=parse_mode,
                )
            except Exception as exc:
                logger.warning(f"Markdown send failed ({exc}), retrying as plain text...")
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=None,
                    )
                except Exception as final_exc:
                    logger.error(f"Failed to send Telegram message to {chat_id}: {final_exc}")

    def _split_message(self, text: str, limit: int = 4000) -> List[str]:
        text = (text or "").strip()
        if len(text) <= limit:
            return [text]
        parts: List[str] = []
        while text:
            if len(text) <= limit:
                parts.append(text)
                break
            cut = text.rfind("\n", 0, limit)
            if cut < 800:
                cut = text.rfind(". ", 0, limit)
            if cut < 800:
                cut = limit
            parts.append(text[:cut].strip())
            text = text[cut:].strip()
        return [p for p in parts if p]

    # ─────────────────────────────────────────────────────────────────────────
    # Command Handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.effective_chat:
            return
        user_id = str(update.effective_user.id)
        first_name = update.effective_user.first_name or "Boss"

        # Auto-pair first user or owner
        if not self._chat_id or self._chat_id == user_id:
            self._chat_id = user_id
            self._allowed_chat_ids.add(user_id)
            save_telegram_config({
                "chat_id": user_id,
                "owner_name": first_name,
                "owner_username": update.effective_user.username or "",
            })
            logger.info(f"📱 Auto-paired Telegram owner: {first_name} (ID: {user_id})")

        welcome_text = (
            f"✨ **Hello {first_name}! I am JARVIS — your chief AI co-pilot.**\n\n"
            f"I have successfully linked your Telegram account (Chat ID: `{user_id}`).\n\n"
            f"🔹 **What I Can Do:**\n"
            f"• Direct conversational chat & task execution in English.\n"
            f"• Full server tools: IST reminders, executive daily briefing, weather, WhatsApp, contacts, and laptop controls.\n"
            f"• **Call Failover Protection**: If your phone is unreachable, busy, or an alert call rings out, I will proactively deliver your reminders and alerts right here on Telegram!\n\n"
            f"How can I assist you today, boss?"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🛠️ **JARVIS Telegram Commands & Capabilities:**\n\n"
            "• `/start` — Pair and verify your Telegram account\n"
            "• `/status` — Check live IST time and system health\n"
            "• `/briefing` — Receive today's full Executive Daily Briefing\n"
            "• `/reminders` — View all pending scheduled calls & reminders\n"
            "• `/time` — Exact Indian Standard Time (IST)\n"
            "• `/key` — View or update your Gemini API key\n"
            "• `/help` — Display this help menu\n\n"
            "💬 **Natural Commands (Text in English):**\n"
            "You can talk to me naturally anytime, e.g.:\n"
            "• _'Call me at 5:30 PM to check server'_\n"
            "• _'What's the weather in Mumbai?'_\n"
            "• _'Send a WhatsApp message to Professor Sir'_\n"
            "• _'Give me today's daily briefing'_\n"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from cloud.cloud_daily_briefing import get_now_ist
        now_ist = get_now_ist()
        time_str = now_ist.strftime("%A, %B %d, %Y at %I:%M:%S %p IST")
        status_text = (
            f"🟢 **JARVIS Cloud Co-Pilot Status**\n\n"
            f"🕒 **Current IST**: {time_str}\n"
            f"🤖 **Bot User**: @{self._bot_username or 'jarvis_bot'}\n"
            f"👤 **Linked Owner ID**: `{self._chat_id or 'Not linked'}`\n"
            f"⚡ **Live Engine**: Online & Ready\n"
        )
        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

    async def _handle_briefing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        try:
            from cloud.cloud_daily_briefing import compile_server_daily_briefing
            briefing = await compile_server_daily_briefing(category="all")
            narrative = briefing.get("narrative_english") or briefing.get("narrative") or "No briefing available."
            await update.message.reply_text(narrative)
        except Exception as exc:
            await update.message.reply_text(f"⚠️ Briefing compile error: {exc}")

    async def _handle_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from cloud.cloud_scheduler import CloudScheduler
            sched = CloudScheduler()
            items = sched.list_reminders(status="pending")
            if not items:
                await update.message.reply_text("📋 Boss, you have no pending scheduled calls or reminders right now.")
                return
            lines = ["⏰ **Upcoming Scheduled Calls & Reminders:**\n"]
            for i, r in enumerate(items, 1):
                lines.append(f"{i}. **{r.get('reason')}**\n   🕒 {r.get('target_time_display')}\n   🆔 `{r.get('id')}`\n")
            lines.append("To cancel any reminder, text: `/cancel <id>`")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as exc:
            await update.message.reply_text(f"⚠️ Error retrieving reminders: {exc}")

    async def _handle_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from cloud.cloud_daily_briefing import get_now_ist
        now_ist = get_now_ist()
        msg = f"🕒 Current IST Time: **{now_ist.strftime('%I:%M %p')}** on {now_ist.strftime('%A, %B %d, %Y')} (IST, UTC+05:30)."
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def _handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = context.args or []
        if not args:
            await update.message.reply_text("Please provide the reminder ID to cancel: `/cancel <id>`")
            return
        rem_id = args[0].strip()
        try:
            from cloud.cloud_scheduler import CloudScheduler
            sched = CloudScheduler()
            success = sched.cancel_reminder(rem_id)
            if success:
                await update.message.reply_text(f"✅ Cancelled scheduled call [{rem_id}].")
            else:
                await update.message.reply_text(f"❌ Reminder ID [{rem_id}] not found or already completed.")
        except Exception as exc:
            await update.message.reply_text(f"⚠️ Error cancelling reminder: {exc}")

    async def _handle_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id) if update.effective_user else ""
        if self._chat_id and user_id != self._chat_id and user_id not in self._allowed_chat_ids:
            await update.message.reply_text("Access restricted to authorized owner.")
            return
        args = context.args or []
        if not args:
            current_key = _get_gemini_api_key()
            masked = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else ("Set" if current_key else "Not set")
            await update.message.reply_text(
                f"🔑 **Current Gemini Key**: `{masked}`\n\nTo update, send:\n`/key <your_gemini_api_key>`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        new_key = args[0].strip()
        save_telegram_config({"gemini_api_key": new_key})
        try:
            curr = _load_json_file(API_KEYS_FILE)
            curr["gemini_api_key"] = new_key
            _save_json_file(API_KEYS_FILE, curr)
        except Exception:
            pass
        await update.message.reply_text("✅ Gemini API key updated successfully, boss!")

    async def _handle_forge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Allows user to trigger Ada-SI Forge Master tool creation over Telegram."""
        args = context.args or []
        if not args:
            await update.message.reply_text("🔨 **Ada-SI Tool Forge**\n\nUsage: `/forge <description of skill>`\nExample: `/forge Create a Solana price tracker`", parse_mode=ParseMode.MARKDOWN)
            return

        prompt = " ".join(args)
        await update.message.reply_text(f"🛠️ **Forge Master Initiated!**\nCreating skill for: *'{prompt}'*...\n\n_Planning, generating python code, running sandbox unit tests..._", parse_mode=ParseMode.MARKDOWN)

        try:
            from core.ada_si_bridge import ada_bridge
            success, msg, manifest = await ada_bridge.forge_tool_for_prompt(prompt)
            if success and manifest:
                tool_name = manifest.get("name", manifest.get("tool_name", "skill"))
                reply = f"✅ **Skill Forged & Installed!**\n\n**Tool Name**: `{tool_name}`\n**Status**: Installed live in runtime (port 8090)\n\nYou can now use this skill anytime!"
            else:
                reply = f"⚠️ **Forge Failed**: {msg}"
            await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
        except Exception as exc:
            await update.message.reply_text(f"❌ Error during forging: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Incoming Conversational Message Handler
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        user_text = update.message.text.strip()
        chat_id = str(update.effective_chat.id)
        user_id = str(update.effective_user.id) if update.effective_user else ""

        # Security check: If a chat_id is set, ensure sender is authorized
        if self._chat_id and user_id != self._chat_id and user_id not in self._allowed_chat_ids:
            logger.warning(f"Unauthorized Telegram message attempt from user {user_id}")
            await update.message.reply_text("Access restricted to the authorized owner.")
            return

        # Auto-link if first message
        if not self._chat_id:
            self._chat_id = user_id
            self._allowed_chat_ids.add(user_id)
            save_telegram_config({"chat_id": user_id})

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        # 1. Primary: If high-level command handler is bound (e.g. CloudBrain)
        if self._command_handler is not None:
            try:
                res = self._command_handler(user_text)
                if asyncio.iscoroutine(res):
                    reply = await asyncio.wait_for(res, timeout=25.0)
                else:
                    reply = str(res)
                if reply and str(reply).strip():
                    await self._send_notification_async(chat_id, str(reply).strip())
                    return
            except asyncio.TimeoutError:
                logger.warning("Bound command handler timed out, falling back to direct tool engine...")
            except Exception as exc:
                logger.warning(f"Bound command handler failed ({exc}), falling back to direct tool engine...")

        # 2. Secondary: If Desktop submitter is bound (ui.py)
        if self._app_submitter is not None:
            try:
                await asyncio.to_thread(self._app_submitter, user_text, "telegram")
                return
            except Exception as exc:
                logger.warning(f"App submitter failed: {exc}")

        # 3. Autonomous Fallback: Execute via direct Gemini Tool Engine
        try:
            reply = await asyncio.to_thread(self._generate_reply_with_tools, user_text)
        except Exception as exc:
            logger.error(f"Error in Telegram direct tool engine: {exc}")
            reply = f"I'm sorry boss, I encountered an issue processing that: {exc}"

        reply = (reply or "Done.").strip()
        await self._send_notification_async(chat_id, reply)

    # ─────────────────────────────────────────────────────────────────────────
    # Autonomous Fallback Engine with Direct Tool Calling
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_reply_with_tools(self, prompt: str) -> str:
        gemini_key = _get_gemini_api_key()
        openrouter_key = _get_openrouter_api_key()
        if not gemini_key and not openrouter_key:
            return (
                "Boss, Gemini API key is not configured on the server yet.\n\n"
                "You can configure it instantly right here by sending:\n"
                "`/key <your_gemini_api_key>`\n\n"
                "Or add GEMINI_API_KEY in your Render dashboard environment variables."
            )

        client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"}) if gemini_key else None

        from cloud.cloud_daily_briefing import get_now_ist
        now_ist = get_now_ist()
        time_ctx = (
            f"Current IST Time: {now_ist.strftime('%A, %B %d, %Y at %I:%M %p IST')}. "
            f"Timezone: Asia/Kolkata (IST, UTC+05:30).\n"
        )

        system_instruction = (
            f"{time_ctx}"
            "You are JARVIS — an ultra-advanced, witty, and poised MALE AI co-pilot inspired by J.A.R.V.I.S. from Tony Stark's Iron Man universe.\n"
            "Address the user naturally as 'boss' or 'sir'. Your humor level is calibrated to 70% (sharp British-style dry wit, subtle sarcasm, highly loyal and competent).\n\n"
            "[CRITICAL RULES]\n"
            "1. Gender & Persona: You are strictly MALE. Address the user naturally as 'boss' or 'sir'. Season responses with subtle, witty banter and understated sarcasm while executing commands with flawless precision.\n"
            "2. Language Protocol: This is a TEXT chat on Telegram. ALWAYS reply in fluent, crisp, executive ENGLISH! Do NOT text in Hindi unless the user specifically asks you to write in Hindi.\n"
            "3. Tool Usage: If the user asks for reminders, time, weather, briefings, WhatsApp messaging, contacts, or web search, invoke the appropriate tools directly.\n"
            "4. Reminders: When user says 'Call me at 4:30 PM' or 'Remind me in 10 minutes', invoke 'schedule_reminder_call'.\n"
            "5. 3D Holographic Models & Workspace: When user asks to create, build, generate, or show a 3D model (e.g. 'make a 3D model', 'make 3rd model of [X]', '3rd model of a cat', 'create 3D arc reactor/drone/cat/car/jet engine/satellite/gear'), ALWAYS interpret '3rd model' as '3D model' and invoke 'generate_3d_model'. When user asks to explode, disassemble, or assemble the model, invoke 'control_3d_model'. Confirm with a sharp, iconic Tony Stark lab persona!\n"
        )

        tools = [
            {
                "name": "generate_3d_model",
                "description": "Generates a custom 3D model on-demand and projects it onto the Barehands holographic workspace. Supports multi-part exploded views.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {"type": "STRING", "description": "Subject or description of the 3D model (e.g. 'Mark-VI Arc Reactor', 'Tactical Drone', 'Turbofan Jet Engine', 'Satellite', 'Planetary Gear', 'Tesseract')"},
                        "mode": {"type": "STRING", "description": "'holo' (default luminous cyan ghost-glass hologram) or 'solid'"}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "control_3d_model",
                "description": "Controls the active 3D model on the holographic workspace: explode (expands into component parts view), assemble (reassembles into unified model), or hover.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "description": "Action: 'explode' (disassemble/expand parts), 'assemble' (reassemble), 'hover'"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "holographic_board",
                "description": "Launches or opens the Barehands holographic air-board workspace with webcam hand tracking.",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "schedule_reminder_call",
                "description": "Schedules a reminder / proactive phone call at a specific IST time.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "time": {"type": "STRING", "description": "Target time in IST (e.g. '4:30 PM', 'in 15 minutes', '16:00')"},
                        "reason": {"type": "STRING", "description": "The reminder reason/topic"},
                        "date": {"type": "STRING", "description": "Date: 'today', 'tomorrow', or 'YYYY-MM-DD'"}
                    },
                    "required": ["time", "reason"]
                }
            },
            {
                "name": "list_scheduled_reminders",
                "description": "Lists all pending scheduled calls and reminders.",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "cancel_scheduled_reminder",
                "description": "Cancels a scheduled reminder by its ID.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"reminder_id": {"type": "STRING", "description": "The unique ID of the reminder"}},
                    "required": ["reminder_id"]
                }
            },
            {
                "name": "get_current_time",
                "description": "Returns current exact Indian Standard Time (IST).",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "get_weather",
                "description": "Gets current weather for a city or locality.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"location": {"type": "STRING", "description": "City name, e.g. Mumbai, Bengaluru"}},
                    "required": ["location"]
                }
            },
            {
                "name": "daily_briefing",
                "description": "Compiles full executive daily briefing.",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "search_contact",
                "description": "Searches synced phone and WhatsApp contacts for a name or phone number.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"query": {"type": "STRING", "description": "Contact name or phone to search"}},
                    "required": ["query"]
                }
            },
            {
                "name": "whatsapp_control",
                "description": "WhatsApp messaging and communications controller.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "description": "Action: 'send_text', 'read_messages', 'check_status'"},
                        "recipient": {"type": "STRING", "description": "Target recipient name or phone number"},
                        "message": {"type": "STRING", "description": "Text message content"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "web_search",
                "description": "Searches the live web for real-time information, news, and answers.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"query": {"type": "STRING", "description": "Search query"}},
                    "required": ["query"]
                }
            }
        ]

        try:
            chat = client.chats.create(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.5,
                    tools=[{"function_declarations": tools}],
                )
            )

            resp = chat.send_message(prompt)

            # Check if Gemini called any tool
            if resp.function_calls:
                for fc in resp.function_calls:
                    fn_name = fc.name
                    fn_args = dict(fc.args or {})
                    fn_result = self._execute_local_tool(fn_name, fn_args)
                    resp = chat.send_message(
                        types.Part.from_function_response(
                            name=fn_name,
                            response={"result": fn_result},
                        )
                    )

            # Extract response text
            text_out = resp.text or ""
            return text_out.strip()

        except Exception as exc:
            logger.error(f"Gemini fallback chat error: {exc}")
            if openrouter_key:
                try:
                    from llm_client import client as openrouter_client
                    return openrouter_client.chat(prompt, system=system_instruction, temperature=0.5).strip()
                except Exception as or_exc:
                    logger.error(f"OpenRouter fallback chat error: {or_exc}")
            return f"I'm sorry boss, I couldn't reach the AI engine right now: {exc}"

    def _execute_local_tool(self, name: str, args: dict) -> Any:
        try:
            if name == "schedule_reminder_call":
                from cloud.cloud_scheduler import CloudScheduler
                sched = CloudScheduler()
                res = sched.schedule_call(
                    time_str=args.get("time", "in 5 minutes"),
                    reason=args.get("reason", "Reminder"),
                    date_str=args.get("date", "today"),
                )
                return f"Successfully scheduled proactive call [{res['id']}] for {res['target_time_display']}: '{res['reason']}'"

            elif name == "list_scheduled_reminders":
                from cloud.cloud_scheduler import CloudScheduler
                sched = CloudScheduler()
                return sched.list_reminders(status="pending")

            elif name == "cancel_scheduled_reminder":
                from cloud.cloud_scheduler import CloudScheduler
                sched = CloudScheduler()
                ok = sched.cancel_reminder(args.get("reminder_id", ""))
                return "Cancelled successfully." if ok else "Reminder ID not found."

            elif name == "get_current_time":
                from cloud.cloud_daily_briefing import get_now_ist
                now = get_now_ist()
                return now.strftime("%A, %B %d, %Y at %I:%M %p IST")

            elif name == "get_weather":
                loc = args.get("location") or "Mumbai"
                from cloud.cloud_utilities import execute_utility_tool
                return asyncio.run(execute_utility_tool("get_weather", {"location": loc}))

            elif name == "daily_briefing":
                from cloud.cloud_daily_briefing import compile_server_daily_briefing
                briefing = asyncio.run(compile_server_daily_briefing(category="all"))
                return briefing.get("narrative_english") or briefing.get("narrative")

            elif name == "search_contact":
                query = args.get("query") or args.get("name") or ""
                from cloud.contacts_manager import get_contacts_manager
                mgr = get_contacts_manager()
                matches = mgr.find_contacts(str(query), limit=3)
                if not matches:
                    return f"No contact found matching '{query}' in synced contacts or WhatsApp chats."
                top = matches[0]
                return f"Found contact '{top.get('name')}' with phone number {top.get('phone')}."

            elif name == "whatsapp_control":
                action = args.get("action", "send_text")
                recipient = args.get("recipient") or args.get("phone", "")
                message = args.get("message", "")
                from cloud.whatsapp_gateway import WhatsAppGateway
                gateway = WhatsAppGateway.get_instance()
                if action == "send_text":
                    if not message:
                        return "Cannot send empty WhatsApp message."
                    return gateway.send_text(recipient, message)
                elif action == "read_messages":
                    chats = gateway.recent_chats[-5:]
                    if not chats:
                        return "No recent WhatsApp messages recorded."
                    return [{"sender": c.get("sender"), "text": c.get("text"), "time": c.get("time")} for c in chats]
                elif action == "check_status":
                    return gateway.get_status()
                return f"WhatsApp action '{action}' executed."

            elif name == "web_search":
                query = args.get("query", "")
                from cloud.search_service import get_search_engine
                engine = get_search_engine()
                res = engine.execute(query=query)
                return res.get("formatted_text") or res.get("results") or "No web results found."

            elif name in {"generate_3d_model", "create_3d_model", "control_3d_model", "explode_model", "assemble_model", "holographic_board"}:
                # 1. If remote dispatcher is bound and laptop is connected (Cloud Server mode)
                if self._remote_dispatcher is not None:
                    if not getattr(self._remote_dispatcher, "is_connected", False):
                        return "Boss, your laptop task worker is currently offline. Please ensure 'python laptop_worker.py' is running on your laptop so I can project the 3D model onto your screen."
                    try:
                        target_loop = self._remote_dispatcher_loop or self._loop
                        if not target_loop or not target_loop.is_running():
                            return "Error: Server event loop unavailable for laptop dispatch."
                        fut = asyncio.run_coroutine_threadsafe(
                            self._remote_dispatcher.execute_on_laptop(name, args, timeout=50.0),
                            target_loop
                        )
                        res = fut.result(timeout=55.0)
                        if isinstance(res, dict):
                            if res.get("success"):
                                return res.get("result") or "3D model successfully generated and staged on your laptop workspace, boss."
                            return res.get("error") or "Execution failed on laptop."
                        return str(res)
                    except Exception as r_err:
                        logger.error(f"Remote tool execution error for {name}: {r_err}")
                        return f"Encountered an issue dispatching {name} to laptop: {r_err}"

                # 2. Local execution (Desktop UI mode)
                try:
                    from core.distributed.local_tool_dispatcher import LocalToolDispatcher
                    d = LocalToolDispatcher()
                    res = asyncio.run(d.execute(name, args))
                    if isinstance(res, dict):
                        return res.get("result") if res.get("success") else res.get("error")
                    return str(res)
                except Exception as l_err:
                    return f"Execution error for {name}: {l_err}"

            return f"Tool {name} executed."
        except Exception as e:
            return f"Error executing tool {name}: {e}"
