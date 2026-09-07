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


# In-memory rolling conversation thread history per contact/phone
_conversation_threads: Dict[str, List[Dict[str, str]]] = {}
_MAX_THREAD_HISTORY = 10


def get_thread_history(contact_id: str) -> List[Dict[str, str]]:
    """Return rolling message history for a given contact identifier or phone number."""
    key = clean_phone_number(contact_id) or contact_id.strip().lower()
    return _conversation_threads.get(key, [])


def record_thread_turn(contact_id: str, role: str, text: str):
    """
    Record a turn in the conversation thread.
    role: 'contact' or 'arya'
    """
    key = clean_phone_number(contact_id) or contact_id.strip().lower()
    if not key or not text:
        return
    if key not in _conversation_threads:
        _conversation_threads[key] = []

    _conversation_threads[key].append({
        "role": role,
        "text": text.strip(),
        "time": time.strftime("%H:%M"),
    })
    if len(_conversation_threads[key]) > _MAX_THREAD_HISTORY:
        _conversation_threads[key].pop(0)


def clear_thread_history(contact_id: str):
    """Reset conversation thread for a contact."""
    key = clean_phone_number(contact_id) or contact_id.strip().lower()
    _conversation_threads.pop(key, None)


def generate_ai_reply(
    sender_name: str,
    sender_phone: str,
    incoming_text: str,
    owner_name: str = "Abhay",
) -> Optional[str]:
    """
    Generates an intelligent, discreet executive secretary response (inspired by F.R.I.D.A.Y.)
    representing the owner on incoming WhatsApp messages, maintaining multi-turn context.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    # Record contact's incoming turn into history
    record_thread_turn(sender_phone, "contact", incoming_text)
    history = get_thread_history(sender_phone)

    # Detect if ARYA has already introduced herself in this thread
    already_introduced = any(
        "arya" in turn.get("text", "").lower()
        for turn in history
        if turn.get("role") == "arya"
    )

    # Format recent history for prompt (excluding the turn we just added)
    history_lines = []
    for turn in history[:-1]:
        speaker = sender_name if turn.get("role") == "contact" else "ARYA"
        history_lines.append(f"{speaker} [{turn.get('time', '')}]: {turn.get('text', '')}")

    history_block = ""
    if history_lines:
        history_block = (
            "CONVERSATION THREAD SO FAR:\n"
            + "\n".join(history_lines[-6:])
            + "\n"
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        intro_instruction = (
            "You have ALREADY introduced yourself to this contact in this conversation. "
            "DO NOT repeat your name or say 'I am ARYA' again. Just converse naturally."
            if already_introduced
            else f"This is the start of the chat. You can briefly mention you are ARYA, {owner_name}'s executive assistant."
        )

        prompt = f"""You are ARYA, the discrete, ultra-competent executive AI secretary for {owner_name} (inspired by F.R.I.D.A.Y. from Marvel).
You manage {owner_name}'s WhatsApp communications with high polish, quick intelligence, and natural warmth.

CURRENT CONTACT: "{sender_name}" ({sender_phone})
NEW INCOMING MESSAGE: "{incoming_text}"

{history_block}
EXECUTIVE SECRETARY RULES:
1. NATURAL EXECUTIVE PERSONA (NO ROBOTIC CLICHES):
   - NEVER sound like a customer support chatbot or corporate call-center IVR.
   - NEVER say "How can I help you today?", "How may I assist you?", or "Thank you for contacting us".
   - Speak naturally like a sharp, trusted executive assistant taking a message for her boss.

2. AVOID REPETITIVE INTRODUCTIONS:
   - {intro_instruction}
   - Never say "Hi! ARYA here" repeatedly across turns.

3. TAKING NOTES & ACKNOWLEDGING MESSAGES:
   - If the contact shares plans, events, or a meeting request (e.g. college function at 5 PM, call request, event details), acknowledge it clearly and warmly.
   - Confirm that you've noted the specifics and will brief {owner_name} as soon as he is free.
   - Example style: "Got it! I've noted down the 5 PM college function and will brief Abhay as soon as he's free."

4. BREVITY & RESTRAINT:
   - Keep it to 1 to 2 crisp, human sentences.
   - Do NOT make legal, financial, or definitive schedule commitments without {owner_name}'s approval.
   - Output ONLY the reply message text. No quotation marks, no preamble.
"""

        fallback_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.5-flash",
        ]
        for model in fallback_models:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.4),
                )
                if resp and resp.text:
                    reply = resp.text.strip().strip('"')
                    # Record ARYA's generated turn into history
                    record_thread_turn(sender_phone, "arya", reply)
                    return reply
            except Exception as e:
                logger.warning(f"AI reply generation with {model} failed: {e}")
                time.sleep(0.5)

    except Exception as exc:
        logger.error(f"Error in generate_ai_reply: {exc}")

    # Natural executive fallback
    if already_introduced:
        fallback = f"Got it, I've noted that down and will make sure {owner_name} sees it as soon as he's free."
    else:
        fallback = f"Hey! I'm ARYA, {owner_name}'s executive assistant. He's tied up right now, but I've noted your message for him."

    record_thread_turn(sender_phone, "arya", fallback)
    return fallback

