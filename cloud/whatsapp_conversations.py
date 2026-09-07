"""
cloud/whatsapp_conversations.py — ARYA WhatsApp Contact Resolution & Autonomous Chat Agent

Handles contact phone lookup from memory, contact saving, and intelligent F.R.I.D.A.Y.
autonomous replies on the user's behalf.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.memory_manager import load_memory, update_memory

logger = logging.getLogger("WhatsAppConversations")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    """Retrieve Gemini API key for WhatsApp conversational generation."""
    if env_key := os.environ.get("GEMINI_API_KEY"):
        return env_key.strip()
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gemini_api_key", "").strip()
        except Exception:
            pass
    return ""


def clean_phone_number(raw: str) -> str:
    """Clean phone number string to pure digits without plus, spaces, or dashes."""
    digits = re.sub(r"[^\d]", "", str(raw or ""))
    # If starting with 0 and 11 digits (e.g. UK/Europe standard), format can be cleaned if country known
    return digits


def resolve_phone_number(recipient: str) -> Optional[str]:
    """
    Resolve contact identifier to pure digits.
    Supports direct phone numbers (e.g. '+91 98765 43210' or '9876543210')
    or contact names stored in memory ('Rahul', 'Mom', 'Boss').
    """
    if not recipient:
        return None

    clean = clean_phone_number(recipient)
    # If 7 or more digits and comprises most of the string, treat as direct phone number
    if len(clean) >= 7 and (len(clean) / max(len(recipient.strip()), 1)) > 0.6:
        return clean

    # Otherwise, search permanent memory
    name_clean = recipient.strip().lower()
    mem = load_memory()

    # Search 'contacts' category
    contacts = mem.get("contacts", {})
    if name_clean in contacts:
        val = contacts[name_clean]
        val_str = val.get("value", "") if isinstance(val, dict) else str(val)
        c = clean_phone_number(val_str)
        if c:
            return c

    # Search 'relationships' category
    rel = mem.get("relationships", {})
    if name_clean in rel:
        val = rel[name_clean]
        val_str = val.get("value", "") if isinstance(val, dict) else str(val)
        c = clean_phone_number(val_str)
        if c:
            return c

    # Fuzzy match keys in contacts
    for k, v in {**contacts, **rel}.items():
        if name_clean in k.lower() or k.lower() in name_clean:
            val_str = v.get("value", "") if isinstance(v, dict) else str(v)
            c = clean_phone_number(val_str)
            if c:
                return c

    return None


def save_contact_number(name: str, phone: str):
    """Save contact name and phone number to permanent memory."""
    clean_name = name.strip().lower()
    clean_num = clean_phone_number(phone)
    if clean_name and clean_num:
        update_memory({
            "relationships": {
                clean_name: {
                    "value": clean_num,
                    "display_name": name.strip(),
                    "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            }
        })
        logger.info(f"Saved contact to memory: {name.strip()} -> {clean_num}")


def generate_ai_reply(
    sender_name: str,
    sender_phone: str,
    incoming_text: str,
    owner_name: str = "Abhay",
) -> Optional[str]:
    """
    Uses Gemini to generate an intelligent, courteous F.R.I.D.A.Y.-style response
    on the user's behalf for incoming WhatsApp messages.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""You are ARYA, the personal AI assistant of {owner_name} (inspired by F.R.I.D.A.Y. from Marvel).
A contact named "{sender_name}" ({sender_phone}) just sent this WhatsApp message to {owner_name}:
"{incoming_text}"

TASK:
Write a brief, polite, helpful, and natural response representing {owner_name} or letting them know as his assistant.
RULES:
1. If they ask for {owner_name}'s availability or a favor, politely acknowledge and tell them you've noted it for {owner_name}.
2. Keep it punchy, friendly, and smart: maximum 1 to 2 sentences.
3. Do NOT make definitive financial, legal, or binding commitments.
4. Output ONLY the reply message text (no quotes, no intro, no emojis spam).
"""

        fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for model in fallback_models:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.4),
                )
                if resp and resp.text:
                    return resp.text.strip().strip('"')
            except Exception as e:
                logger.warning(f"AI reply generation with {model} failed: {e}")
                time.sleep(0.5)

    except Exception as exc:
        logger.error(f"Error in generate_ai_reply: {exc}")

    return None
