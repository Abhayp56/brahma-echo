"""
cloud/contacts_manager.py — Multi-Alias Contact Engine & Address Book Manager

Merges phone address book contacts (from Android auto-sync) with WhatsApp chat/profile names.
Enables cross-name resolution so users can refer to contacts by their phonebook name (e.g. 'Rahul'),
their WhatsApp chat name (e.g. 'Broski'), or custom voice-taught nicknames (e.g. 'Bhai').
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("ContactsManager")

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
CONTACTS_PATH = BASE_DIR / "memory" / "contacts_book.json"
LONG_TERM_MEMORY_PATH = BASE_DIR / "memory" / "long_term.json"


def clean_phone_number(raw: str) -> str:
    """Extract pure digits from phone string, stripping formatting characters."""
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    # If 10 digits starting with 6,7,8,9, default to India +91 prefix if no country code provided
    if len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    return digits


@dataclass
class ContactProfile:
    """A unified contact profile linking a phone number to multiple names and aliases."""
    phone: str
    phone_name: str = ""
    whatsapp_name: str = ""
    aliases: Set[str] = field(default_factory=set)
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phone": self.phone,
            "phone_name": self.phone_name,
            "whatsapp_name": self.whatsapp_name,
            "aliases": sorted(list(self.aliases)),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContactProfile:
        aliases = set(str(a).strip().lower() for a in data.get("aliases", []) if a)
        return cls(
            phone=clean_phone_number(data.get("phone", "")),
            phone_name=str(data.get("phone_name", "")).strip(),
            whatsapp_name=str(data.get("whatsapp_name", "")).strip(),
            aliases=aliases,
            updated_at=str(data.get("updated_at", "")),
        )

    def add_alias(self, alias: str):
        c = alias.strip().lower()
        if c:
            self.aliases.add(c)


class ContactsManager:
    """
    Central repository for contacts, supporting phonebook auto-sync,
    WhatsApp chat name learning, and multi-alias resolution.
    """

    _instance: Optional[ContactsManager] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ContactsManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._profiles: Dict[str, ContactProfile] = {}  # phone -> ContactProfile
        self._load()

    def _load(self):
        """Loads contacts from contacts_book.json and seeds from long_term.json if available."""
        if CONTACTS_PATH.exists():
            try:
                with open(CONTACTS_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for item in raw.get("contacts", []):
                        prof = ContactProfile.from_dict(item)
                        if prof.phone:
                            self._profiles[prof.phone] = prof
                logger.info(f"Loaded {len(self._profiles)} unified contact profiles from {CONTACTS_PATH.name}")
            except Exception as e:
                logger.warning(f"Failed to read {CONTACTS_PATH}: {e}")

        # Also import any contacts/relationships present in long_term.json
        if LONG_TERM_MEMORY_PATH.exists():
            try:
                with open(LONG_TERM_MEMORY_PATH, "r", encoding="utf-8") as f:
                    lt = json.load(f)
                    for cat in ("contacts", "relationships"):
                        cat_data = lt.get(cat, {})
                        if isinstance(cat_data, dict):
                            for name, val in cat_data.items():
                                val_str = val.get("value", "") if isinstance(val, dict) else str(val)
                                phone = clean_phone_number(val_str)
                                if phone:
                                    self._upsert_contact(phone=phone, phone_name=name, aliases=[name])
            except Exception as e:
                logger.debug(f"Could not seed from long_term.json: {e}")

    def save(self):
        """Persists contacts to memory/contacts_book.json and long_term.json."""
        try:
            CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONTACTS_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "version": "1.0",
                    "total": len(self._profiles),
                    "contacts": [p.to_dict() for p in self._profiles.values()]
                }, f, indent=2, ensure_ascii=False)

            # Sync back into long_term.json under 'contacts'
            if LONG_TERM_MEMORY_PATH.exists():
                try:
                    with open(LONG_TERM_MEMORY_PATH, "r", encoding="utf-8") as f:
                        lt = json.load(f)
                    if "contacts" not in lt or not isinstance(lt["contacts"], dict):
                        lt["contacts"] = {}
                    for p in self._profiles.values():
                        primary_name = (p.phone_name or p.whatsapp_name or p.phone).lower()
                        lt["contacts"][primary_name] = {
                            "value": p.phone,
                            "display_name": p.phone_name or p.whatsapp_name,
                            "updated": p.updated_at,
                        }
                    with open(LONG_TERM_MEMORY_PATH, "w", encoding="utf-8") as f:
                        json.dump(lt, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    logger.debug(f"Failed to sync to long_term.json: {e}")

        except Exception as e:
            logger.error(f"Failed saving contacts to {CONTACTS_PATH}: {e}")

    def _upsert_contact(
        self,
        phone: str,
        phone_name: str = "",
        whatsapp_name: str = "",
        aliases: Optional[List[str]] = None,
    ) -> ContactProfile:
        clean_num = clean_phone_number(phone)
        if not clean_num:
            raise ValueError("Phone number must contain digits.")

        if clean_num in self._profiles:
            prof = self._profiles[clean_num]
            if phone_name:
                prof.phone_name = phone_name.strip()
                prof.add_alias(phone_name)
            if whatsapp_name:
                prof.whatsapp_name = whatsapp_name.strip()
                prof.add_alias(whatsapp_name)
        else:
            prof = ContactProfile(
                phone=clean_num,
                phone_name=phone_name.strip(),
                whatsapp_name=whatsapp_name.strip(),
            )
            if phone_name:
                prof.add_alias(phone_name)
            if whatsapp_name:
                prof.add_alias(whatsapp_name)
            self._profiles[clean_num] = prof

        if aliases:
            for a in aliases:
                prof.add_alias(a)

        prof.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        return prof

    def sync_phone_contacts(self, contacts: List[Dict[str, Any]]) -> int:
        """
        Receives batch contacts from Android companion app auto-sync.
        Each contact item has 'name' and 'phone'.
        """
        added_or_updated = 0
        with self._lock:
            for item in contacts:
                raw_name = str(item.get("name") or "").strip()
                raw_phone = str(item.get("phone") or "").strip()
                if not raw_phone:
                    continue
                clean_num = clean_phone_number(raw_phone)
                if not clean_num or len(clean_num) < 7:
                    continue

                self._upsert_contact(phone=clean_num, phone_name=raw_name)
                added_or_updated += 1

            self.save()

        logger.info(f"📱 Synced {added_or_updated} contacts from Android phone companion.")
        return added_or_updated

    def learn_whatsapp_contact(self, phone: str, push_name: str) -> Optional[ContactProfile]:
        """
        Automatically learns or enriches a contact with their WhatsApp display name (e.g. 'Broski').
        Called whenever WhatsApp receives or sends a message.
        """
        clean_num = clean_phone_number(phone)
        if not clean_num or not push_name:
            return None

        clean_push = push_name.strip()
        # Ignore generic placeholder names
        if clean_push.lower() in {"user", "friend", "someone", "unknown", clean_num}:
            return None

        with self._lock:
            prof = self._upsert_contact(phone=clean_num, whatsapp_name=clean_push)
            self.save()

        logger.info(f"💬 Learned WhatsApp alias for {clean_num}: '{clean_push}'")
        return prof

    def add_alias(self, target: str, alias: str) -> bool:
        """
        Allows teaching ARYA an alias or nickname explicitly via voice:
        e.g. 'Remember that Broski is Rahul' or 'Add alias Mom to 9876543210'.
        """
        clean_alias = alias.strip().lower()
        if not clean_alias:
            return False

        with self._lock:
            # First check if target is a phone number
            phone = clean_phone_number(target)
            if phone and phone in self._profiles:
                self._profiles[phone].add_alias(clean_alias)
                self.save()
                return True

            # Check if target resolves to an existing contact
            resolved = self._resolve_internal(target)
            if resolved:
                resolved.add_alias(clean_alias)
                self.save()
                return True

        return False

    def _resolve_internal(self, query: str) -> Optional[ContactProfile]:
        """Internal helper for resolving a query without acquiring lock again."""
        q = query.strip().lower()
        if not q:
            return None

        # 1. Direct phone number check
        clean_num = clean_phone_number(q)
        if len(clean_num) >= 7 and clean_num in self._profiles:
            return self._profiles[clean_num]

        # 2. Exact match in aliases
        for prof in self._profiles.values():
            if q in prof.aliases:
                return prof

        # 3. Exact match against phone_name or whatsapp_name
        for prof in self._profiles.values():
            if q == prof.phone_name.lower() or q == prof.whatsapp_name.lower():
                return prof

        # 4. Prefix / Word boundary match (e.g. 'Rahul' matches 'Rahul Verma' or 'Rahul College')
        candidates: List[ContactProfile] = []
        for prof in self._profiles.values():
            names_to_check = [prof.phone_name.lower(), prof.whatsapp_name.lower()] + list(prof.aliases)
            for n in names_to_check:
                if not n:
                    continue
                # If query is full word inside the contact name
                pattern = r"\b" + re.escape(q) + r"\b"
                if re.search(pattern, n):
                    candidates.append(prof)
                    break

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            # Prefer contact with most recent update or closest length
            candidates.sort(key=lambda p: abs(len(p.phone_name or p.whatsapp_name) - len(q)))
            return candidates[0]

        # 5. Substring match fallback (e.g. 'brosk' matches 'broski')
        for prof in self._profiles.values():
            if any(q in alias for alias in prof.aliases):
                return prof

        return None

    def resolve(self, recipient: str) -> Optional[ContactProfile]:
        """
        Public resolver method: maps any recipient identifier (Rahul, Broski, Mom, 9876543210)
        to a unified ContactProfile.
        """
        with self._lock:
            return self._resolve_internal(recipient)

    def resolve_phone(self, recipient: str) -> Optional[str]:
        """Convenience method returning pure phone digits for a recipient string."""
        prof = self.resolve(recipient)
        if prof:
            return prof.phone
        # Fallback to direct digits if string looks like phone number
        clean = clean_phone_number(recipient)
        if len(clean) >= 7:
            return clean
        return None

    def list_contacts(self) -> List[Dict[str, Any]]:
        """Returns all contacts formatted for debugging or Web UI."""
        with self._lock:
            return [p.to_dict() for p in self._profiles.values()]


# Global singleton access
def get_contacts_manager() -> ContactsManager:
    return ContactsManager.get_instance()
