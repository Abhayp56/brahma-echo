"""
Supabase Cloud Memory Adapter for Brahma Echo.

Provides permanent, autonomous storage for AI memories in a hosted Supabase PostgreSQL table.
Supports full CRUD (Create, Read, Update, Delete, Search) using PostgREST HTTP REST endpoints,
ensuring zero extra heavy dependencies and resilience across network hiccups.
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger("SupabaseMemory")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# In-memory cache to minimize latency during live multimodal conversations
_memory_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: float = 0.0
CACHE_TTL_SECONDS = 30.0


def get_supabase_credentials() -> tuple[str, str]:
    """
    Retrieve Supabase URL and API Key from environment variables (Render/production)
    or config/api_keys.json (local development).
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()

    if not url or not key:
        if API_CONFIG_PATH.exists():
            try:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not url:
                        url = data.get("supabase_url", "").strip()
                    if not key:
                        key = data.get("supabase_key", "").strip()
            except Exception as e:
                logger.warning(f"Failed to read {API_CONFIG_PATH}: {e}")

    # Normalize URL format (remove trailing slash)
    if url.endswith("/"):
        url = url[:-1]

    return url, key


def is_supabase_configured() -> bool:
    """Check if valid Supabase credentials are provided."""
    url, key = get_supabase_credentials()
    return bool(url and key and url.startswith("http"))


def _get_headers(key: str) -> Dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def load_all_memories_supabase(user_id: str = "default_user", force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Fetch all active memories for the user from Supabase, organized by category.
    Returns format:
    {
        "identity": {"name": {"value": "Ali", "updated": "2026-09-07"}},
        "preferences": {"favorite_food": {"value": "pizza", "updated": "2026-09-07"}},
        ...
    }
    """
    global _memory_cache, _cache_timestamp

    now = time.time()
    if not force_refresh and _memory_cache is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _memory_cache

    url, key = get_supabase_credentials()
    if not url or not key:
        return None

    endpoint = f"{url}/rest/v1/ai_memories"
    params = {
        "user_id": f"eq.{user_id}",
        "select": "category,key,value,updated_at,confidence",
        "order": "updated_at.desc",
    }

    try:
        resp = requests.get(endpoint, headers=_get_headers(key), params=params, timeout=5)
        if resp.status_code == 200:
            rows = resp.json()
            structured = {
                "identity": {},
                "preferences": {},
                "projects": {},
                "relationships": {},
                "wishes": {},
                "notes": {},
            }
            for row in rows:
                cat = row.get("category", "notes")
                k = row.get("key", "")
                val = row.get("value", "")
                upd = row.get("updated_at", "")[:10]
                conf = row.get("confidence", 5)

                if cat not in structured:
                    structured[cat] = {}

                structured[cat][k] = {
                    "value": val,
                    "updated": upd,
                    "confidence": conf,
                }

            _memory_cache = structured
            _cache_timestamp = now
            return structured
        else:
            logger.warning(f"Supabase GET memories failed: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.warning(f"Error querying Supabase memories: {e}")
        return None


def save_or_update_memory_supabase(
    category: str,
    key_name: str,
    value: str,
    user_id: str = "default_user",
    confidence: int = 5,
) -> bool:
    """
    Upsert memory to Supabase.
    If the (user_id, category, key) exists, it updates the value and updated_at.
    Otherwise, it inserts a new record.
    """
    global _memory_cache, _cache_timestamp

    url, key = get_supabase_credentials()
    if not url or not key:
        return False

    endpoint = f"{url}/rest/v1/ai_memories"
    headers = _get_headers(key)
    # PostgREST merge duplicates on unique constraint
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    payload = {
        "user_id": user_id,
        "category": category,
        "key": key_name,
        "value": value,
        "confidence": confidence,
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=5)
        if resp.status_code in (200, 201):
            logger.info(f"[Supabase Saved] {category}/{key_name} = {value}")
            _memory_cache = None
            _cache_timestamp = 0.0
            return True
        else:
            logger.warning(f"Supabase upsert failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Error saving to Supabase: {e}")
        return False


def delete_memory_supabase(category: str, key_name: str, user_id: str = "default_user") -> bool:
    """
    Permanently delete a specific memory key from Supabase.
    """
    global _memory_cache, _cache_timestamp

    url, key = get_supabase_credentials()
    if not url or not key:
        return False

    endpoint = f"{url}/rest/v1/ai_memories"
    params = {
        "user_id": f"eq.{user_id}",
        "category": f"eq.{category}",
        "key": f"eq.{key_name}",
    }

    try:
        resp = requests.delete(endpoint, headers=_get_headers(key), params=params, timeout=5)
        if resp.status_code in (200, 204):
            logger.info(f"[Supabase Deleted] {category}/{key_name}")
            _memory_cache = None
            _cache_timestamp = 0.0
            return True
        else:
            logger.warning(f"Supabase delete failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Error deleting from Supabase: {e}")
        return False


def search_memories_supabase(search_term: str, user_id: str = "default_user") -> List[Dict[str, Any]]:
    """
    Search memories across category, key, and value using ilike pattern matching.
    """
    url, key = get_supabase_credentials()
    if not url or not key:
        return []

    endpoint = f"{url}/rest/v1/ai_memories"
    params = {
        "user_id": f"eq.{user_id}",
        "or": f"(value.ilike.*{search_term}*,key.ilike.*{search_term}*)",
        "select": "category,key,value,updated_at",
        "order": "updated_at.desc",
    }

    try:
        resp = requests.get(endpoint, headers=_get_headers(key), params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        logger.warning(f"Error searching Supabase: {e}")
        return []
