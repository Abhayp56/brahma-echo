"""
CloudScheduler — Proactive, IST-Aware Call & Reminder Scheduler for ARYA Cloud.

Features:
  - Strict Indian Standard Time (IST, Asia/Kolkata, UTC+05:30) calculations.
  - Persistent JSON storage for scheduled calls & reminders across server restarts.
  - Asynchronous background worker that triggers phone_hub.call_phone when due.
  - Urgent alert hook for WhatsApp/Email triggers.
"""

import asyncio
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("CloudScheduler")

IST_TZ = ZoneInfo("Asia/Kolkata")
SCHEDULE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "scheduled_calls.json"
)

# Urgent keywords that trigger immediate proactive calls
URGENT_KEYWORDS = [
    "urgent", "emergency", "asap", "critical", "immediately", 
    "deadline today", "server down", "production issue", "call me now",
    "help needed", "very important", "high priority"
]


def get_now_ist() -> datetime:
    """Returns the current date and time in Indian Standard Time (IST)."""
    return datetime.now(IST_TZ)


def format_ist_time(dt: Optional[datetime] = None) -> str:
    """Formats an IST datetime into a friendly Indian string."""
    if dt is None:
        dt = get_now_ist()
    return dt.strftime("%A, %B %d, %Y at %I:%M %p IST")


class CloudScheduler:
    def __init__(self, storage_path: str = SCHEDULE_FILE):
        self.storage_path = storage_path
        self._ensure_storage()
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if not os.path.exists(self.storage_path) or os.path.getsize(self.storage_path) == 0:
            try:
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump({"reminders": []}, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to initialize scheduler file: {e}")

    def _load_reminders(self) -> List[Dict[str, Any]]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("reminders", [])
        except Exception as e:
            logger.error(f"Failed to load reminders: {e}")
            return []

    def _save_reminders(self, reminders: List[Dict[str, Any]]):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"reminders": reminders}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}")

    def parse_time_to_ist(self, time_str: str, date_str: str = "today") -> Optional[datetime]:
        """
        Parses human natural speech or formal time into an exact IST datetime.
        Examples:
          - "4:30 PM", "16:30", "4:30pm"
          - "in 15 minutes", "in 2 hours", "in 30 mins"
          - "tomorrow at 9:00 AM"
        """
        now = get_now_ist()
        clean = time_str.strip().lower()

        # 1. Check relative offsets: "in X minutes", "in X mins", "in X hours"
        rel_match = re.search(r"in\s+(\d+)\s*(minute|min|m|hour|hr|h)s?", clean)
        if rel_match:
            amount = int(rel_match.group(1))
            unit = rel_match.group(2)
            if unit in ("minute", "min", "m"):
                return now + timedelta(minutes=amount)
            elif unit in ("hour", "hr", "h"):
                return now + timedelta(hours=amount)

        # 2. Determine target base date (today, tomorrow, or YYYY-MM-DD)
        target_date = now.date()
        date_clean = (date_str or "today").strip().lower()
        if "tomorrow" in clean or "tomorrow" in date_clean:
            target_date = now.date() + timedelta(days=1)
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", date_clean):
            try:
                target_date = datetime.strptime(date_clean, "%Y-%m-%d").date()
            except ValueError:
                pass

        # 3. Time format: "4:30 PM", "04:30 pm", "4 PM", "4pm", "16:30"
        time_clean = clean.replace("tomorrow", "").replace("today", "").replace("at", "").strip()

        # Try standard 12-hour AM/PM formats
        for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M"):
            try:
                parsed_t = datetime.strptime(time_clean, fmt).time()
                candidate = datetime.combine(target_date, parsed_t, tzinfo=IST_TZ)
                # If parsed time is today but already passed, and user didn't say tomorrow,
                # if within 12 hours earlier, user might mean tomorrow or next 12h cycle
                if candidate < now and "today" in date_clean and not ("tomorrow" in clean):
                    if (now - candidate).total_seconds() > 3600:
                        candidate += timedelta(days=1)
                return candidate
            except ValueError:
                continue

        return None

    def schedule_call(self, time_str: str, reason: str, date_str: str = "today") -> Dict[str, Any]:
        """Schedules a proactive phone call to the user."""
        target_dt = self.parse_time_to_ist(time_str, date_str)
        if not target_dt:
            # Fallback: 5 minutes from now if parsing failed
            target_dt = get_now_ist() + timedelta(minutes=5)
            logger.warning(f"Could not parse '{time_str}'. Defaulted to 5 mins from now: {target_dt}")

        reminder_id = secrets.token_hex(6)
        reminder = {
            "id": reminder_id,
            "target_timestamp": target_dt.timestamp(),
            "target_time_ist": target_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
            "target_time_display": target_dt.strftime("%I:%M %p on %A, %b %d (%Z)"),
            "reason": reason.strip(),
            "created_at_ist": get_now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
            "status": "pending",
        }

        reminders = self._load_reminders()
        reminders.append(reminder)
        self._save_reminders(reminders)
        logger.info(f"⏰ Scheduled proactive call [{reminder_id}] for {reminder['target_time_display']}: '{reason}'")
        return reminder

    def list_reminders(self, status: str = "pending") -> List[Dict[str, Any]]:
        """Returns list of reminders matching the status."""
        reminders = self._load_reminders()
        if not status:
            return reminders
        return [r for r in reminders if r.get("status") == status]

    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancels a pending reminder by ID."""
        reminders = self._load_reminders()
        found = False
        for r in reminders:
            if r.get("id") == reminder_id and r.get("status") == "pending":
                r["status"] = "cancelled"
                found = True
                break
        if found:
            self._save_reminders(reminders)
            logger.info(f"🚫 Cancelled scheduled call [{reminder_id}]")
        return found

    async def check_urgent_message_alert(self, phone_hub: Any, sender: str, message_text: str) -> bool:
        """
        Inspects an incoming message (WhatsApp / Email).
        If high urgency is detected, immediately initiates a proactive alert call.
        """
        if not message_text or not phone_hub or not phone_hub.is_connected:
            return False

        lower_msg = message_text.lower()
        is_urgent = any(kw in lower_msg for kw in URGENT_KEYWORDS)

        if is_urgent:
            reason = f"Urgent WhatsApp message from {sender}: '{message_text[:60]}...'"
            logger.warning(f"🚨 URGENT MESSAGE DETECTED! Initiating proactive call for: {reason}")
            try:
                res = await phone_hub.call_phone(
                    caller_name="ARYA (Urgent Alert)",
                    reason=reason
                )
                return res.get("success", False)
            except Exception as e:
                logger.error(f"Failed to trigger urgent alert call: {e}")
        return False

    async def start_loop(self, phone_hub: Any, brain: Any):
        """Dedicated background task checking for due reminders every 4 seconds."""
        if self._is_running:
            return
        self._is_running = True
        logger.info(f"🚀 CloudScheduler daemon started (Current IST: {format_ist_time()})")

        while self._is_running:
            try:
                now_ts = get_now_ist().timestamp()
                reminders = self._load_reminders()
                changed = False

                for r in reminders:
                    if r.get("status") == "pending" and now_ts >= r.get("target_timestamp", 0):
                        reminder_id = r.get("id")
                        reason = r.get("reason", "Scheduled reminder")
                        logger.info(f"🔔 Reminder [{reminder_id}] is DUE NOW! Placing proactive call: '{reason}'")

                        if phone_hub and phone_hub.is_connected:
                            r["status"] = "calling"
                            self._save_reminders(reminders)
                            changed = True

                            call_res = await phone_hub.call_phone(
                                caller_name="ARYA (Reminder)",
                                reason=f"Scheduled reminder: {reason}"
                            )
                            if call_res.get("success"):
                                r["status"] = "completed"
                                r["completed_at_ist"] = get_now_ist().strftime("%Y-%m-%d %H:%M:%S IST")
                                logger.info(f"✅ Proactive call successfully initiated for reminder [{reminder_id}]")
                            else:
                                r["status"] = "missed_phone_busy"
                                logger.warning(f"⚠️ Phone not available for reminder [{reminder_id}]: {call_res.get('error')}")
                        else:
                            r["status"] = "missed_disconnected"
                            logger.warning(f"⚠️ Phone disconnected. Could not place proactive call for [{reminder_id}].")
                        changed = True

                if changed:
                    self._save_reminders(reminders)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")

            await asyncio.sleep(4)

        logger.info("🛑 CloudScheduler daemon stopped.")

    def stop(self):
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
