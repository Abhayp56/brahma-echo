"""
cloud/news_service.py — ARYA Live News Service

Supports:
1. GNews.io REST API (if GNEWS_API_KEY is configured in environment or config/api_keys.json)
2. Google News RSS Feed (automatic keyless fallback with zero daily quota limits)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("NewsService")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_gnews_api_key() -> str:
    """Read GNews API key from env or config/api_keys.json."""
    if key := os.environ.get("GNEWS_API_KEY"):
        return key.strip()
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gnews_api_key", "").strip()
        except Exception:
            pass
    return ""


def _fetch_gnews_api(
    api_key: str,
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Fetch headlines from official GNews.io API."""
    limit = min(max(max_results, 1), 10)
    if query and query.strip():
        q_enc = urllib.parse.quote(query.strip())
        url = f"https://gnews.io/api/v4/search?q={q_enc}&lang=en&max={limit}&apikey={api_key}"
    else:
        cat = (category or "general").strip().lower()
        url = f"https://gnews.io/api/v4/top-headlines?category={cat}&lang=en&max={limit}&apikey={api_key}"

    req = urllib.request.Request(url, headers={"User-Agent": "Brahma-Echo-News/2.0"})
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    articles = []
    for item in data.get("articles", [])[:limit]:
        articles.append({
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "url": item.get("url", ""),
            "source": item.get("source", {}).get("name", "GNews"),
            "published_at": item.get("publishedAt", ""),
            "image_url": item.get("image", None),
        })

    return {
        "success": True,
        "source": "GNews API",
        "total": len(articles),
        "query": query or category or "top-headlines",
        "articles": articles,
    }


def _clean_html_text(raw_html: str) -> str:
    """Strip HTML markup and entities from RSS descriptions."""
    clean = re.sub(r"<[^>]+>", "", raw_html or "")
    clean = clean.replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
    return clean.strip()


def _fetch_google_news_rss(
    query: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Keyless fallback fetching real-time headlines from Google News RSS.
    100% free, unlimited, and fast.
    """
    limit = min(max(max_results, 1), 10)
    if query and query.strip():
        q_enc = urllib.parse.quote(query.strip())
        url = f"https://news.google.com/rss/search?q={q_enc}&hl=en-IN&gl=IN&ceid=IN:en"
    else:
        url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        xml_content = resp.read()

    root = ET.fromstring(xml_content)
    articles = []

    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub_date = item.findtext("pubDate", "")
        source_elem = item.find("source")
        source_name = source_elem.text if source_elem is not None else "Google News"
        description = _clean_html_text(item.findtext("description", ""))

        # Strip duplicate source name from Google News title (e.g. "Title - NDTV")
        if " - " in title:
            title = title.rsplit(" - ", 1)[0].strip()

        articles.append({
            "title": title,
            "description": description,
            "url": link,
            "source": source_name,
            "published_at": pub_date,
        })

    return {
        "success": True,
        "source": "Google News RSS",
        "total": len(articles),
        "query": query or "Top Headlines",
        "articles": articles,
    }


def get_news_headlines_sync(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Unified synchronous entry point.
    Tries GNews.io API first if key exists, otherwise seamlessly falls back to Google News RSS.
    """
    gnews_key = _get_gnews_api_key()
    if gnews_key:
        try:
            return _fetch_gnews_api(gnews_key, query=query, category=category, max_results=max_results)
        except Exception as e:
            logger.warning(f"GNews API request failed ({e}), falling back to Google News RSS...")

    try:
        return _fetch_google_news_rss(query=query or category, max_results=max_results)
    except Exception as exc:
        logger.error(f"Failed to fetch news from Google News RSS: {exc}")
        return {"success": False, "error": f"Failed to retrieve news: {exc}"}


async def get_news_headlines(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Asynchronous wrapper to prevent blocking the event loop."""
    return await asyncio.to_thread(get_news_headlines_sync, query, category, max_results)
