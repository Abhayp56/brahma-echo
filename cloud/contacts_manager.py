"""
cloud/contacts_manager.py — Multi-Alias Contact Resolution Engine for ARYA & WhatsApp

Solves the real-world contact naming dilemma:
- A person may be saved as "Rahul" in your phonebook.
- But on WhatsApp, their chat/push name is "Broski".
- You might speak "Send message to Broski" or "Send message to Rahul".
- Phone number is the immutable anchor; multiple aliases map to the same contact.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("ContactsManager")

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
CONTACTS_FILE = BASE_DIR / "memory" / "contacts.json"
LONG_TERM_MEMORY_FILE = BASE_DIR / "memory" / "long_term.json"


def clean_phone_number(raw: str, default_country_code: str = "91") -> str:
    """
    Normalizes phone numbers to standard pure digit format.
    Handles +91, spaces, dashes, leading zeros, and 10-digit Indian numbers.
    """
    digits = re.sub(r"[^\d]", "", str(raw or "").strip())
    if not digits:
        return ""

    # Remove leading trunk zero (e.g. 09876543210 -> 9876543210)
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # If 10 digits and default country is India, prepend 91 for international WhatsApp format
    if len(digits) == 10 and default_country_code:
        digits = f"{default_country_code}{digits}"

    return digits


@dataclass
class ContactProfile:
    phone: str
    primary_name: str
    phone_name: str = ""
    whatsapp_name: str = ""
    aliases: List[str] = field(default_factory=list)
    notes: str = ""
    updated_at: str = ""
    interaction_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phone": self.phone,
            "primary_name": self.primary_name,
            "phone_name": self.phone_name,
            "whatsapp_name": self.whatsapp_name,
            "aliases": sorted(list(set(self.aliases))),
            "notes": self.notes,
            "updated_at": self.updated_at,
            "interaction_count": self.interaction_count,
        }

    def all_names(self) -> Set[str]:
        """Returns all lowercase normalized names and aliases for this contact."""
        names: Set[str] = set()
        if self.primary_name:
            names.add(self.primary_name.strip().lower())
        if self.phone_name:
            names.add(self.phone_name.strip().lower())
        if self.whatsapp_name:
            names.add(self.whatsapp_name.strip().lower())
        for a in self.aliases:
            if a:
                names.add(a.strip().lower())
        return names


class ContactsManager:
    """
    Manages persistent contacts with multi-alias resolution.
    Thread-safe and synchronized across Cloud Brain, WhatsApp Gateway, and Android Client.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or CONTACTS_FILE
        self._lock = threading.RLock()
        self.contacts: Dict[str, ContactProfile] = {}  # Key: canonical phone number
        self._alias_index: Dict[str, str] = {}         # Key: lowercase alias -> phone number
        self._load()

    def _load(self):
        """Load contacts from disk, migrating legacy memory if necessary."""
        with self._lock:
            self.contacts.clear()
            self._alias_index.clear()

            if self.storage_path.exists():
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        for phone, item in data.items():
                            clean_p = clean_phone_number(phone)
                            if not clean_p:
                                continue
                            aliases = [str(a).strip().lower() for a in item.get("aliases", []) if str(a).strip()]
                            prof = ContactProfile(
                                phone=clean_p,
                                primary_name=item.get("primary_name") or item.get("name") or clean_p,
                                phone_name=item.get("phone_name", ""),
                                whatsapp_name=item.get("whatsapp_name", ""),
                                aliases=aliases,
                                notes=item.get("notes", ""),
                                updated_at=item.get("updated_at", ""),
                                interaction_count=item.get("interaction_count", 0),
                            )
                            self.contacts[clean_p] = prof
                except Exception as ex:
                    logger.error(f"Error loading contacts from {self.storage_path}: {ex}")

            # Bootstrap from long_term.json (legacy contacts & relationships) if empty
            if not self.contacts and LONG_TERM_MEMORY_FILE.exists():
                self._import_from_long_term_memory()

            self._rebuild_alias_index()

    def _import_from_long_term_memory(self):
        """One-time migration of contacts from long_term.json into contacts.json."""
        try:
            with open(LONG_TERM_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return

            contacts_cat = data.get("contacts", {})
            rel_cat = data.get("relationships", {})

            for name, val in {**contacts_cat, **rel_cat}.items():
                val_str = val.get("value", "") if isinstance(val, dict) else str(val)
                phone = clean_phone_number(val_str)
                if phone:
                    clean_name = name.strip()
                    self.save_contact(
                        phone=phone,
                        name=clean_name,
                        aliases=[clean_name.lower()],
                        source="legacy_memory_migration"
                    )
            logger.info(f"Imported {len(self.contacts)} contacts from long-term memory.")
        except Exception as ex:
            logger.warning(f"Could not import legacy contacts: {ex}")

    def _rebuild_alias_index(self):
        """Reconstructs the fast lookup index from all contacts."""
        self._alias_index.clear()
        for phone, prof in self.contacts.items():
            # Add phone number itself
            self._alias_index[phone] = phone
            # Add all names & aliases
            for name in prof.all_names():
                if name:
                    self._alias_index[name] = phone

    def _save(self):
        """Persist contacts to disk."""
        with self._lock:
            try:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                data = {phone: prof.to_dict() for phone, prof in self.contacts.items()}
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as ex:
                logger.error(f"Failed to save contacts to {self.storage_path}: {ex}")

    def save_contact(
        self,
        phone: str,
        name: str = "",
        phone_name: str = "",
        whatsapp_name: str = "",
        aliases: Optional[List[str]] = None,
        notes: str = "",
        source: str = "manual",
    ) -> ContactProfile:
        """
        Saves or merges a contact.
        If a contact with the same phone exists, automatically merges names and aliases!
        """
        clean_p = clean_phone_number(phone)
        if not clean_p:
            raise ValueError(f"Invalid phone number: {phone}")

        with self._lock:
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            existing = self.contacts.get(clean_p)

            new_aliases: Set[str] = set()
            if aliases:
                for a in aliases:
                    if a and str(a).strip():
                        new_aliases.add(str(a).strip().lower())

            if name:
                new_aliases.add(name.strip().lower())
            if phone_name:
                new_aliases.add(phone_name.strip().lower())
            if whatsapp_name:
                new_aliases.add(whatsapp_name.strip().lower())

            if existing:
                # Merge into existing profile
                if name and not existing.primary_name:
                    existing.primary_name = name.strip()
                if phone_name:
                    existing.phone_name = phone_name.strip()
                if whatsapp_name:
                    existing.whatsapp_name = whatsapp_name.strip()
                if notes:
                    existing.notes = notes.strip()

                combined_aliases = set(existing.aliases) | new_aliases
                existing.aliases = sorted(list(combined_aliases))
                existing.updated_at = now_str
                prof = existing
                logger.info(f"Merged contact [{clean_p}]: {prof.primary_name} (aliases: {prof.aliases})")
            else:
                primary = name.strip() or phone_name.strip() or whatsapp_name.strip() or clean_p
                prof = ContactProfile(
                    phone=clean_p,
                    primary_name=primary,
                    phone_name=phone_name.strip(),
                    whatsapp_name=whatsapp_name.strip(),
                    aliases=sorted(list(new_aliases)),
                    notes=notes.strip(),
                    updated_at=now_str,
                    interaction_count=0,
                )
                self.contacts[clean_p] = prof
                logger.info(f"Created new contact [{clean_p}]: {prof.primary_name} (aliases: {prof.aliases})")

            self._rebuild_alias_index()
            self._save()
            return prof

    def add_alias(self, contact_identifier: str, new_alias: str) -> Optional[ContactProfile]:
        """
        Adds a nickname/alias to an existing contact.
        contact_identifier can be phone number, existing contact name, or existing alias.
        """
        clean_alias = new_alias.strip().lower()
        if not clean_alias:
            return None

        with self._lock:
            prof = self.resolve(contact_identifier)
            if not prof:
                logger.warning(f"Cannot add alias '{new_alias}': contact '{contact_identifier}' not found.")
                return None

            if clean_alias not in prof.aliases:
                prof.aliases.append(clean_alias)
                prof.aliases = sorted(list(set(prof.aliases)))
                prof.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
                self._rebuild_alias_index()
                self._save()
                logger.info(f"Added alias '{clean_alias}' to contact '{prof.primary_name}' ({prof.phone}).")
            return prof

    def auto_learn_whatsapp_chat(self, phone: str, push_name: str) -> Optional[ContactProfile]:
        """
        Automatically called when an incoming/outgoing WhatsApp message occurs.
        Registers the sender's WhatsApp Pushname as an alias for their phone number.
        """
        clean_p = clean_phone_number(phone)
        clean_name = push_name.strip() if push_name else ""
        if not clean_p or not clean_name:
            return None

        with self._lock:
            existing = self.contacts.get(clean_p)
            if existing:
                existing.interaction_count += 1
                if clean_name.lower() not in existing.all_names():
                    existing.aliases.append(clean_name.lower())
                    existing.aliases = sorted(list(set(existing.aliases)))
                    if not existing.whatsapp_name:
                        existing.whatsapp_name = clean_name
                    existing.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    self._rebuild_alias_index()
                    self._save()
                    logger.info(f"Auto-learned WhatsApp alias for {clean_p}: '{clean_name}'")
                return existing
            else:
                # Create profile with WhatsApp name
                return self.save_contact(
                    phone=clean_p,
                    whatsapp_name=clean_name,
                    aliases=[clean_name.lower()],
                    source="whatsapp_auto_learn"
                )

    def resolve(self, query: str) -> Optional[ContactProfile]:
        """
        Multi-tier Contact Resolution:
        1. Exact phone number match
        2. Exact alias match (case-insensitive)
        3. Exact name match (primary_name, phone_name, whatsapp_name)
        4. Substring token match (e.g. 'Rahul' in 'Rahul Verma')
        5. Fuzzy string similarity match (e.g. 'Brosky' -> 'Broski')
        """
        clean_q = str(query or "").strip()
        if not clean_q:
            return None

        with self._lock:
            # 1. Direct phone number check
            clean_digits = clean_phone_number(clean_q)
            if clean_digits in self.contacts:
                return self.contacts[clean_digits]

            # If 7+ digits provided, treat as direct phone number even if not in book
            if len(clean_digits) >= 10 and (len(clean_digits) / max(len(clean_q), 1)) > 0.6:
                if clean_digits in self.contacts:
                    return self.contacts[clean_digits]

            lower_q = clean_q.lower()

            # 2. Exact alias index lookup
            if lower_q in self._alias_index:
                target_phone = self._alias_index[lower_q]
                if target_phone in self.contacts:
                    return self.contacts[target_phone]

            # 3. Exact field match
            for prof in self.contacts.values():
                if lower_q in prof.all_names():
                    return prof

            # 4. Substring / Token boundary match (e.g. user says "Rahul", saved as "Rahul College")
            candidates: List[ContactProfile] = []
            for prof in self.contacts.values():
                for name in prof.all_names():
                    # Word boundary match: 'rahul' in ['rahul', 'college']
                    tokens = re.split(r"[\s_\-]+", name)
                    if lower_q in tokens or any(t.startswith(lower_q) for t in tokens):
                        candidates.append(prof)
                        break
                    elif lower_q in name:
                        candidates.append(prof)
                        break

            if len(candidates) == 1:
                return candidates[0]
            elif len(candidates) > 1:
                # Sort by interaction count / recency
                candidates.sort(key=lambda c: c.interaction_count, reverse=True)
                return candidates[0]

            # 5. Fuzzy string similarity matching (handles minor speech-to-text typos like 'Brosky' -> 'Broski')
            best_match: Optional[ContactProfile] = None
            best_score = 0.0

            for prof in self.contacts.values():
                for name in prof.all_names():
                    ratio = difflib.SequenceMatcher(None, lower_q, name).ratio()
                    if ratio > best_score:
                        best_score = ratio
                        best_match = prof

            if best_score >= 0.80 and best_match:
                logger.info(f"Fuzzy matched contact '{query}' -> '{best_match.primary_name}' (score: {best_score:.2f})")
                return best_match

            return None

    def import_vcf_content(self, vcf_text: str) -> int:
        """
        Parses a standard vCard (.vcf) export file and imports all contacts.
        Returns the number of imported/updated contacts.
        """
        imported = 0
        vcard_blocks = re.findall(r"BEGIN:VCARD.*?END:VCARD", vcf_text, re.DOTALL | re.IGNORECASE)

        for block in vcard_blocks:
            fn_match = re.search(r"(?:^|\n)FN(?:;[^:]*)?:(.*)", block, re.IGNORECASE)
            n_match = re.search(r"(?:^|\n)N(?:;[^:]*)?:(.*)", block, re.IGNORECASE)
            tel_matches = re.findall(r"(?:^|\n)TEL(?:;[^:]*)?:(.*)", block, re.IGNORECASE)

            full_name = ""
            if fn_match:
                full_name = fn_match.group(1).strip()
            elif n_match:
                parts = [p.strip() for p in n_match.group(1).split(";") if p.strip()]
                full_name = " ".join(reversed(parts))

            if not tel_matches:
                continue

            for raw_tel in tel_matches:
                phone = clean_phone_number(raw_tel)
                if phone and len(phone) >= 10:
                    self.save_contact(
                        phone=phone,
                        name=full_name or phone,
                        phone_name=full_name,
                        aliases=[full_name.lower()] if full_name else [],
                        source="vcf_import"
                    )
                    imported += 1
                    break

        logger.info(f"Imported {imported} contacts from vCard file.")
        return imported

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns all contacts sorted alphabetically by primary name."""
        with self._lock:
            sorted_contacts = sorted(self.contacts.values(), key=lambda c: c.primary_name.lower())
            return [c.to_dict() for c in sorted_contacts]


# Global singleton instance
_contacts_manager_instance: Optional[ContactsManager] = None

def get_contacts_manager() -> ContactsManager:
    """Returns the global singleton instance of ContactsManager."""
    global _contacts_manager_instance
    if _contacts_manager_instance is None:
        _contacts_manager_instance = ContactsManager()
    return _contacts_manager_instance
