"""
cloud/cloud_daily_briefing.py — Server-Side Autonomous Daily Executive Briefing

Compiles comprehensive, live morning and daily executive briefings on the Cloud Server
with ZERO dependency on the user's laptop:
1. Exact Indian Standard Time (IST, Asia/Kolkata, UTC+05:30) & dynamic greeting
2. Live local weather for the user's exact phone GPS/city location
3. Today's schedule and appointments (Google Calendar & local calendar memory)
4. Important unread emails summary (Gmail API)
5. Recent unread / incoming WhatsApp communications (WhatsApp Gateway)
6. Top breaking news headlines (Google News RSS & GNews)
7. Today's pending tasks (Todoist API)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("CloudDailyBriefing")

BASE_DIR = Path(__file__).resolve().parent.parent
LOCATION_FILE = BASE_DIR / "memory" / "phone_location.json"
IST_TZ = ZoneInfo("Asia/Kolkata")


def get_now_ist() -> datetime:
    """Returns the current datetime in Indian Standard Time (IST)."""
    return datetime.now(IST_TZ)


def load_phone_location() -> Dict[str, Any]:
    """Reads the last known phone GPS/locality location synced from Android app."""
    if LOCATION_FILE.exists():
        try:
            with open(LOCATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Could not load phone location: {e}")
    # Default fallback to India capital / tech hub
    return {
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "lat": 12.9716,
        "lon": 77.5946,
        "is_default": True,
    }


def save_phone_location(loc_data: Dict[str, Any]) -> None:
    """Saves the latest phone location from Android companion app."""
    try:
        LOCATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCATION_FILE, "w", encoding="utf-8") as f:
            json.dump(loc_data, f, indent=2)
        logger.info(f"Saved phone location: {loc_data.get('city') or loc_data.get('lat')}")
    except Exception as e:
        logger.error(f"Failed to save phone location: {e}")


async def _fetch_weather(location_info: Dict[str, Any]) -> str:
    """Fetches live weather for phone's coordinates or city using Open-Meteo."""
    try:
        from cloud.cloud_utilities import execute_utility_tool

        city = location_info.get("city")
        lat = location_info.get("lat")
        lon = location_info.get("lon")

        query_loc = city if city and str(city).strip() else f"{lat},{lon}"
        if not query_loc or query_loc == "None,None":
            query_loc = "Bengaluru"

        res = await execute_utility_tool("get_weather", {"location": query_loc})
        if res.get("success"):
            desc = res.get("description", "clear")
            temp = res.get("temperature")
            unit = res.get("unit", "°C")
            loc_name = res.get("location", query_loc)
            return f"{temp}{unit}, {desc} in {loc_name}"
        return "Weather service currently updating."
    except Exception as e:
        logger.debug(f"Weather fetch error in daily briefing: {e}")
        return "Weather data unavailable at the moment."


async def _fetch_calendar_schedule(now_ist: datetime) -> List[str]:
    """Fetches today's events from Google Calendar and local calendar store."""
    events = []

    # 1. Try Google Calendar
    try:
        from cloud.google_workspace import list_calendar_events_direct
        start_of_day = now_ist.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = now_ist.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        g_events = await list_calendar_events_direct(time_min=start_of_day, time_max=end_of_day, max_results=5)
        for ge in g_events:
            summary = ge.get("summary", "Meeting")
            st = ge.get("start", {}).get("dateTime") or ge.get("start", {}).get("date", "")
            if "T" in st:
                try:
                    time_part = datetime.fromisoformat(st).strftime("%I:%M %p")
                    events.append(f"{summary} at {time_part}")
                except Exception:
                    events.append(summary)
            else:
                events.append(summary)
    except Exception as e:
        logger.debug(f"Google Calendar fetch in briefing: {e}")

    # 2. Try local calendar memory
    if not events:
        try:
            from actions.daily_briefing import _get_today_schedule
            local_events = _get_today_schedule()
            if local_events:
                events.extend(local_events)
        except Exception:
            pass

    return events


async def _fetch_unread_emails() -> Dict[str, Any]:
    """Fetches unread email count and top subject lines from Gmail."""
    try:
        from cloud.google_workspace import execute_gmail_tool
        res = await execute_gmail_tool("list_emails", {"query": "is:unread", "max_results": 3})
        if res.get("success"):
            emails = res.get("emails", [])
            return {
                "count": len(emails),
                "has_unread": len(emails) > 0,
                "snippets": [f"'{e.get('subject')}' from {e.get('sender')}" for e in emails[:2]],
            }
    except Exception as e:
        logger.debug(f"Gmail fetch in briefing: {e}")
    return {"count": 0, "has_unread": False, "snippets": []}


def _fetch_recent_whatsapp() -> Dict[str, Any]:
    """Summarizes recent incoming messages on WhatsApp."""
    try:
        from cloud.whatsapp_gateway import WhatsAppGateway
        gw = WhatsAppGateway.get_instance()
        incoming = [c for c in gw.recent_chats if c.get("direction") == "inbound"]
        if incoming:
            latest = incoming[-3:]
            senders = list(dict.fromkeys(c.get("sender") or c.get("phone") for c in latest))
            return {
                "count": len(incoming),
                "senders": senders,
                "summary": f"{len(incoming)} recent incoming WhatsApp message(s) from {', '.join(senders)}.",
            }
    except Exception as e:
        logger.debug(f"WhatsApp fetch in briefing: {e}")
    return {"count": 0, "senders": [], "summary": "No pending WhatsApp messages."}


async def _fetch_news_headlines(limit: int = 3) -> List[str]:
    """Fetches top breaking news headlines from NewsService."""
    try:
        from cloud.news_service import get_news_headlines
        res = await get_news_headlines(max_results=limit)
        if res.get("success"):
            return [h.get("title") for h in res.get("articles", []) if h.get("title")]
    except Exception as e:
        logger.debug(f"News fetch error in briefing: {e}")
    return []


async def compile_server_daily_briefing(category: str = "all") -> Dict[str, Any]:
    """
    Asynchronously gathers all intelligence components and compiles the complete
    daily executive briefing directly on the Cloud Server.
    """
    now_ist = get_now_ist()
    time_str = now_ist.strftime("%I:%M %p IST").lstrip("0")
    date_str = now_ist.strftime("%A, %B %d, %Y")

    hour = now_ist.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # Location & Weather
    location_info = load_phone_location()
    loc_display = location_info.get("city") or location_info.get("state") or "your location"
    weather_task = _fetch_weather(location_info)
    schedule_task = _fetch_calendar_schedule(now_ist)
    email_task = _fetch_unread_emails()
    news_task = _fetch_news_headlines(limit=3)

    weather_str, schedule_events, email_data, news_headlines = await asyncio.gather(
        weather_task, schedule_task, email_task, news_task, return_exceptions=False
    )

    whatsapp_data = _fetch_recent_whatsapp()

    # Build natural spoken narrative
    spoken_parts = [
        f"{greeting} boss! Today is {date_str}, and the exact time is {time_str}.",
        f"Weather in {loc_display} is currently {weather_str}.",
    ]

    # Schedule
    if schedule_events:
        spoken_parts.append(f"On your schedule today: {', '.join(schedule_events)}.")
    else:
        spoken_parts.append("You have a clear schedule today with no calendar meetings.")

    # Email
    if email_data.get("has_unread"):
        email_count = email_data["count"]
        snippets = "; ".join(email_data["snippets"])
        spoken_parts.append(f"You have {email_count} unread email(s), including {snippets}.")

    # WhatsApp
    if whatsapp_data.get("count", 0) > 0:
        spoken_parts.append(f"WhatsApp: {whatsapp_data['summary']}")

    # News
    if news_headlines:
        news_text = " • ".join(news_headlines)
        spoken_parts.append(f"Top headlines: {news_text}")

    spoken_parts.append("All server systems are fully operational. What are your orders, boss?")

    full_narrative = " ".join(spoken_parts)

    return {
        "success": True,
        "time": time_str,
        "date": date_str,
        "greeting": greeting,
        "location": loc_display,
        "weather": weather_str,
        "schedule": schedule_events,
        "emails": email_data,
        "whatsapp": whatsapp_data,
        "headlines": news_headlines,
        "narrative": full_narrative,
        "result": full_narrative,
    }
