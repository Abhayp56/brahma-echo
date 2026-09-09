"""
cloud/google_workspace.py — ARYA Google Calendar & Gmail Integration

Provides direct, lightweight REST access to Google Calendar and Gmail via OAuth 2.0.
Requires:
  - config/google_credentials.json (Client ID & Client Secret)
  - config/google_token.json (Refresh token & cached access token)
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from email.message import EmailMessage
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("GoogleWorkspace")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CREDENTIALS_PATH = CONFIG_DIR / "google_credentials.json"
TOKEN_PATH = CONFIG_DIR / "google_token.json"

API_CONFIG_PATH = CONFIG_DIR / "api_keys.json"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

_in_memory_access_token: Optional[str] = None
_in_memory_expires_at: float = 0.0


def _load_google_credentials() -> Dict[str, str]:
    """Retrieve client_id, client_secret, and refresh_token from files or environment."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "").strip()

    # Check if raw JSON was provided via environment variable (e.g. Render / Railway)
    if raw_creds := os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip():
        try:
            cdata = json.loads(raw_creds)
            installed = cdata.get("installed") or cdata.get("web") or cdata
            client_id = client_id or installed.get("client_id", "").strip()
            client_secret = client_secret or installed.get("client_secret", "").strip()
        except Exception as e:
            logger.warning(f"Error parsing GOOGLE_CREDENTIALS_JSON: {e}")

    if raw_token := os.environ.get("GOOGLE_TOKEN_JSON", "").strip():
        try:
            tdata = json.loads(raw_token)
            refresh_token = refresh_token or tdata.get("refresh_token", "").strip()
        except Exception as e:
            logger.warning(f"Error parsing GOOGLE_TOKEN_JSON: {e}")

    # Check credentials file
    if CREDENTIALS_PATH.exists():
        try:
            with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                installed = data.get("installed") or data.get("web") or data
                client_id = client_id or installed.get("client_id", "").strip()
                client_secret = client_secret or installed.get("client_secret", "").strip()
        except Exception as e:
            logger.warning(f"Error reading {CREDENTIALS_PATH}: {e}")

    # Check token file
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                tdata = json.load(f)
                refresh_token = refresh_token or tdata.get("refresh_token", "").strip()
        except Exception as e:
            logger.warning(f"Error reading {TOKEN_PATH}: {e}")

    # Check api_keys.json fallback
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                adata = json.load(f)
                client_id = client_id or adata.get("google_client_id", "").strip()
                client_secret = client_secret or adata.get("google_client_secret", "").strip()
                refresh_token = refresh_token or adata.get("google_refresh_token", "").strip()
        except Exception:
            pass

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }


def is_google_configured() -> bool:
    """Check if Google OAuth credentials and refresh token exist."""
    creds = _load_google_credentials()
    return bool(creds.get("client_id") and creds.get("client_secret") and creds.get("refresh_token"))


def get_google_access_token() -> Optional[str]:
    """
    Returns a valid access token.
    Automatically refreshes the token using the refresh_token if expired.
    Uses in-memory cache and file cache.
    """
    global _in_memory_access_token, _in_memory_expires_at

    creds = _load_google_credentials()
    client_id = creds["client_id"]
    client_secret = creds["client_secret"]
    refresh_token = creds["refresh_token"]

    if not client_id or not client_secret or not refresh_token:
        return None

    # Check in-memory cache first
    now = time.time()
    if _in_memory_access_token and now < (_in_memory_expires_at - 60):
        return _in_memory_access_token

    # Check cached access token in TOKEN_PATH
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                tdata = json.load(f)
                cached_token = tdata.get("access_token")
                expires_at = tdata.get("expires_at", 0)
                if cached_token and now < (expires_at - 60):
                    _in_memory_access_token = cached_token
                    _in_memory_expires_at = expires_at
                    return cached_token
        except Exception:
            pass

    # Refresh the token
    logger.info("Refreshing Google OAuth access token...")
    try:
        body_params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        data_encoded = urllib.parse.urlencode(body_params).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=data_encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        new_access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        new_expires_at = time.time() + expires_in

        # Cache in memory
        _in_memory_access_token = new_access_token
        _in_memory_expires_at = new_expires_at

        # Try updating TOKEN_PATH if possible
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            token_dict = {
                "refresh_token": refresh_token,
                "access_token": new_access_token,
                "expires_at": new_expires_at,
            }
            with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                json.dump(token_dict, f, indent=2)
        except Exception as err:
            logger.debug(f"Note: Could not persist token to disk: {err}")

        return new_access_token
    except Exception as e:
        logger.error(f"Failed to refresh Google access token: {e}")
        return None


def _google_api_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    """Helper for authenticated Google REST API requests."""
    access_token = get_google_access_token()
    if not access_token:
        return {
            "success": False,
            "configured": False,
            "error": "Google Calendar and Gmail are not configured yet. Please configure OAuth credentials in config/google_credentials.json and config/google_token.json.",
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "Brahma-Echo-Assistant/2.0",
    }
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            if resp.status == 204:
                return {"success": True, "status": 204}
            content = resp.read().decode("utf-8")
            if not content:
                return {"success": True}
            return json.loads(content)
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8") if he.fp else str(he)
        logger.error(f"Google API HTTP {he.code}: {err_body}")
        return {"success": False, "error": f"Google API Error {he.code}: {err_body}"}
    except Exception as e:
        logger.error(f"Google API Request error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# Google Calendar Operations
# =========================================================================

def list_calendar_events_sync(
    max_results: int = 10,
    time_min: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve upcoming events from Google Calendar."""
    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()

    url = (
        f"{CALENDAR_API_BASE}/events?"
        f"timeMin={urllib.parse.quote(time_min)}&"
        f"maxResults={max_results}&"
        f"singleEvents=true&"
        f"orderBy=startTime"
    )

    res = _google_api_request(url, method="GET")
    if isinstance(res, dict) and not res.get("success", True):
        return res

    events = []
    for item in res.get("items", []):
        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
        end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
        events.append({
            "id": item.get("id"),
            "summary": item.get("summary", "(No Title)"),
            "start": start,
            "end": end,
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "link": item.get("htmlLink"),
        })

    return {
        "success": True,
        "configured": True,
        "total": len(events),
        "events": events,
    }


def create_calendar_event_sync(
    summary: str,
    start_time: str,
    end_time: Optional[str] = None,
    description: str = "",
    location: str = "",
) -> Dict[str, Any]:
    """Create a new event on primary Google Calendar."""
    if not summary or not start_time:
        return {"success": False, "error": "Summary and start_time are required."}

    # If end_time is not provided, default to 1 hour after start
    if not end_time:
        try:
            st = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            from datetime import timedelta
            end_time = (st + timedelta(hours=1)).isoformat()
        except Exception:
            end_time = start_time

    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start_time} if "T" in start_time else {"date": start_time},
        "end": {"dateTime": end_time} if "T" in end_time else {"date": end_time},
    }

    url = f"{CALENDAR_API_BASE}/events"
    res = _google_api_request(url, method="POST", payload=body)
    if isinstance(res, dict) and res.get("id"):
        return {
            "success": True,
            "configured": True,
            "event_id": res.get("id"),
            "summary": res.get("summary"),
            "start": res.get("start"),
            "end": res.get("end"),
            "link": res.get("htmlLink"),
        }
    return res


def delete_calendar_event_sync(event_id: str) -> Dict[str, Any]:
    """Delete an event from Google Calendar."""
    if not event_id:
        return {"success": False, "error": "Missing event_id."}

    url = f"{CALENDAR_API_BASE}/events/{event_id}"
    res = _google_api_request(url, method="DELETE")
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "message": f"Deleted calendar event '{event_id}'."}
    return res


# =========================================================================
# Gmail Operations
# =========================================================================

def list_emails_sync(
    query: str = "is:unread",
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search and list emails from Gmail."""
    url = f"{GMAIL_API_BASE}/messages?q={urllib.parse.quote(query)}&maxResults={max_results}"
    res = _google_api_request(url, method="GET")

    if isinstance(res, dict) and not res.get("success", True):
        return res

    messages_summary = []
    for msg in res.get("messages", [])[:max_results]:
        mid = msg.get("id")
        m_url = f"{GMAIL_API_BASE}/messages/{mid}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date"
        m_data = _google_api_request(m_url, method="GET")
        if isinstance(m_data, dict) and m_data.get("id"):
            headers = {
                h.get("name", ""): h.get("value", "")
                for h in m_data.get("payload", {}).get("headers", [])
            }
            messages_summary.append({
                "id": mid,
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(No Subject)"),
                "date": headers.get("Date", ""),
                "snippet": m_data.get("snippet", ""),
            })

    return {
        "success": True,
        "configured": True,
        "query": query,
        "total": len(messages_summary),
        "messages": messages_summary,
    }


def get_email_details_sync(message_id: str) -> Dict[str, Any]:
    """Retrieve full content and snippet of an email."""
    if not message_id:
        return {"success": False, "error": "Missing message_id."}

    url = f"{GMAIL_API_BASE}/messages/{message_id}?format=full"
    res = _google_api_request(url, method="GET")
    if isinstance(res, dict) and res.get("id"):
        headers = {
            h.get("name", ""): h.get("value", "")
            for h in res.get("payload", {}).get("headers", [])
        }
        return {
            "success": True,
            "configured": True,
            "id": res.get("id"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": res.get("snippet", ""),
        }
    return res


def send_email_sync(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send an email on the user's behalf through Gmail."""
    if not to or not subject or not body:
        return {"success": False, "error": "To, subject, and body are required to send an email."}

    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["Subject"] = subject

    raw_bytes = message.as_bytes()
    encoded_raw = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    url = f"{GMAIL_API_BASE}/messages/send"
    res = _google_api_request(url, method="POST", payload={"raw": encoded_raw})

    if isinstance(res, dict) and res.get("id"):
        return {
            "success": True,
            "configured": True,
            "message_id": res.get("id"),
            "to": to,
            "subject": subject,
            "status": "Sent",
        }
    return res


# =========================================================================
# Asynchronous Dispatchers
# =========================================================================

async def execute_calendar_tool(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous entry point for Google Calendar."""
    act = (action or args.get("action", "list_events")).lower().strip()
    if act in {"list_events", "list", "get_events", "events"}:
        max_res = int(args.get("max_results") or 10)
        return await asyncio.to_thread(list_calendar_events_sync, max_results=max_res, time_min=args.get("time_min"))
    elif act in {"create_event", "create", "add_event", "schedule"}:
        return await asyncio.to_thread(
            create_calendar_event_sync,
            summary=args.get("summary") or args.get("title", "Meeting"),
            start_time=args.get("start_time") or args.get("start", ""),
            end_time=args.get("end_time") or args.get("end"),
            description=args.get("description", ""),
            location=args.get("location", ""),
        )
    elif act in {"delete_event", "delete", "cancel"}:
        return await asyncio.to_thread(delete_calendar_event_sync, event_id=args.get("event_id", ""))

    return {"success": False, "error": f"Unknown calendar action: '{action}'."}


async def execute_gmail_tool(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous entry point for Gmail."""
    act = (action or args.get("action", "list_emails")).lower().strip()
    if act in {"list_emails", "list", "unread", "search"}:
        q = args.get("query") or "is:unread"
        max_res = int(args.get("max_results") or 5)
        return await asyncio.to_thread(list_emails_sync, query=q, max_results=max_res)
    elif act in {"read_email", "read", "get_email", "details"}:
        return await asyncio.to_thread(get_email_details_sync, message_id=args.get("message_id", ""))
    elif act in {"send_email", "send"}:
        return await asyncio.to_thread(
            send_email_sync,
            to=args.get("to") or args.get("recipient", ""),
            subject=args.get("subject", ""),
            body=args.get("body") or args.get("message", ""),
        )

    return {"success": False, "error": f"Unknown Gmail action: '{action}'."}
