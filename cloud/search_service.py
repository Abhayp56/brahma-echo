"""
cloud/search_service.py — Multi-Provider Web Search Fallback Engine

Architecture:
- Implements Strategy Pattern with BaseSearchProvider interface.
- Automatic Fallback Chain:
    1. GcrawlAI (200 free req/mo, JS rendering & anti-bot stealth)
    2. serpstack (100 free req/mo, APILayer SERP engine)
    3. Zenserp (50 free req/mo, Google search SERP engine)
    4. DuckDuckGo (Zero-cost, unmetered public fallback)
    5. Gemini Grounding (Google Search grounding with user Gemini API key)
- Designed for background execution on the Cloud Server (non-blocking)
  as well as local laptop usage.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SearchService")

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def load_api_keys() -> Dict[str, str]:
    """Reads API keys from environment variables and config/api_keys.json."""
    keys: Dict[str, str] = {}
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    keys.update(data)
        except Exception as e:
            logger.warning(f"Could not read {API_CONFIG_PATH}: {e}")

    # Environment variables override config file
    env_mappings = {
        "gemini_api_key": ["GEMINI_API_KEY"],
        "gcrawl_api_key": ["GCRAWL_API_KEY", "GCRAWLAI_API_KEY", "GCRAWL_KEY"],
        "serpstack_api_key": ["SERPSTACK_API_KEY", "SERPSTACK_KEY", "APILAYER_SERPSTACK_KEY"],
        "zenserp_api_key": ["ZENSERP_API_KEY", "ZENSERP_KEY"],
    }
    for key_name, env_vars in env_mappings.items():
        for ev in env_vars:
            if val := os.environ.get(ev):
                keys[key_name] = val.strip()
                break

    return keys


class SearchProviderError(Exception):
    """Raised when a search provider fails or exhausts its quota."""
    def __init__(self, provider_name: str, message: str, status_code: Optional[int] = None):
        super().__init__(f"[{provider_name}] {message}" + (f" (HTTP {status_code})" if status_code else ""))
        self.provider_name = provider_name
        self.status_code = status_code


@dataclass
class SearchResultItem:
    """Standardized search result representation."""
    title: str
    snippet: str
    url: str
    provider: str
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "snippet": self.snippet,
            "url": self.url,
            "provider": self.provider,
        }


class BaseSearchProvider(ABC):
    """Abstract interface for all web search providers."""

    def __init__(self, name: str, timeout: float = 8.0):
        self.name = name
        self.timeout = timeout

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider has necessary keys/dependencies."""
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        """Executes search and returns a list of SearchResultItems. Raises SearchProviderError on failure."""
        pass


class GcrawlAISearchProvider(BaseSearchProvider):
    """
    Provider 1: GcrawlAI (200 free req/mo).
    Official endpoint: https://gcrawlai.com/gc/api/v1/search
    Header: X-API-Key: <key>
    Payload: {"query": query, "pagination": max_results, "geo": "IN"}
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0):
        super().__init__("GcrawlAI", timeout=timeout)
        self._api_key = api_key

    def _get_key(self) -> str:
        if self._api_key:
            return self._api_key
        keys = load_api_keys()
        return keys.get("gcrawl_api_key", "").strip()

    def is_available(self) -> bool:
        return bool(self._get_key())

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        api_key = self._get_key()
        if not api_key:
            raise SearchProviderError(self.name, "API key not configured.")

        url = "https://gcrawlai.com/gc/api/v1/search"
        payload = json.dumps({
            "query": query,
            "pagination": max_results,
            "geo": "IN",
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "User-Agent": "BrahmaEcho/2.0 (SearchService)",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise SearchProviderError(self.name, f"Unexpected response", status_code=response.status)
                raw_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            err_body = ""
            try:
                err_body = he.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                pass
            raise SearchProviderError(self.name, f"HTTP Error: {he.reason} - {err_body}", status_code=he.code)
        except Exception as ex:
            raise SearchProviderError(self.name, f"Request failed: {ex}")

        # GcrawlAI returns {"results": [{"title": ..., "description": ..., "url": ...}], ...}
        raw_results = raw_data.get("results") or []
        items: List[SearchResultItem] = []
        for r in raw_results[:max_results]:
            title = r.get("title") or ""
            snippet = r.get("description") or r.get("snippet") or ""
            link = r.get("url") or r.get("link") or ""
            if title or snippet:
                items.append(SearchResultItem(
                    title=title.strip(),
                    snippet=snippet.strip(),
                    url=link.strip(),
                    provider=self.name,
                ))

        if not items:
            raise SearchProviderError(self.name, "Returned empty search results.")
        return items


class SerpstackSearchProvider(BaseSearchProvider):
    """
    Provider 2: serpstack (100 free req/mo).
    Official endpoint: http://api.serpstack.com/search (or https)
    Query params: access_key=<key>&query=<query>&num=<num>
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 8.0):
        super().__init__("serpstack", timeout=timeout)
        self._api_key = api_key

    def _get_key(self) -> str:
        if self._api_key:
            return self._api_key
        keys = load_api_keys()
        return keys.get("serpstack_api_key", "").strip()

    def is_available(self) -> bool:
        return bool(self._get_key())

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        api_key = self._get_key()
        if not api_key:
            raise SearchProviderError(self.name, "API key not configured.")

        # Note: serpstack free tier uses HTTP or HTTPS; we use HTTPS first with fallback
        params = urllib.parse.urlencode({
            "access_key": api_key,
            "query": query,
            "num": max_results,
        })
        url = f"https://api.serpstack.com/search?{params}"

        headers = {"User-Agent": "BrahmaEcho/2.0 (SearchService)"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            # If HTTPS restricted on free plan, retry on HTTP
            if he.code in (403, 400):
                http_url = f"http://api.serpstack.com/search?{params}"
                try:
                    req_http = urllib.request.Request(http_url, headers=headers, method="GET")
                    with urllib.request.urlopen(req_http, timeout=self.timeout) as http_res:
                        raw_data = json.loads(http_res.read().decode("utf-8"))
                except Exception as ex_http:
                    raise SearchProviderError(self.name, f"HTTP request failed: {ex_http}")
            else:
                raise SearchProviderError(self.name, f"HTTP Error: {he.reason}", status_code=he.code)
        except Exception as ex:
            raise SearchProviderError(self.name, f"Request failed: {ex}")

        if not raw_data.get("success", True) and "error" in raw_data:
            err_info = raw_data["error"].get("info", "Unknown API error")
            err_code = raw_data["error"].get("code")
            raise SearchProviderError(self.name, f"API error: {err_info}", status_code=err_code)

        raw_results = raw_data.get("organic_results") or []
        items: List[SearchResultItem] = []
        for r in raw_results[:max_results]:
            title = r.get("title") or ""
            snippet = r.get("snippet") or ""
            link = r.get("url") or ""
            if title or snippet:
                items.append(SearchResultItem(
                    title=title.strip(),
                    snippet=snippet.strip(),
                    url=link.strip(),
                    provider=self.name,
                ))

        if not items:
            raise SearchProviderError(self.name, "Returned empty search results.")
        return items


class ZenserpSearchProvider(BaseSearchProvider):
    """
    Provider 3: Zenserp (50 free req/mo).
    Official endpoint: https://app.zenserp.com/api/v2/search
    Headers or params: apikey=<key>, q=<query>, num=<num>
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 8.0):
        super().__init__("Zenserp", timeout=timeout)
        self._api_key = api_key

    def _get_key(self) -> str:
        if self._api_key:
            return self._api_key
        keys = load_api_keys()
        return keys.get("zenserp_api_key", "").strip()

    def is_available(self) -> bool:
        return bool(self._get_key())

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        api_key = self._get_key()
        if not api_key:
            raise SearchProviderError(self.name, "API key not configured.")

        params = urllib.parse.urlencode({
            "apikey": api_key,
            "q": query,
            "num": max_results,
        })
        url = f"https://app.zenserp.com/api/v2/search?{params}"

        headers = {
            "apikey": api_key,
            "User-Agent": "BrahmaEcho/2.0 (SearchService)",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            raise SearchProviderError(self.name, f"HTTP Error: {he.reason}", status_code=he.code)
        except Exception as ex:
            raise SearchProviderError(self.name, f"Request failed: {ex}")

        if "errors" in raw_data:
            raise SearchProviderError(self.name, f"API Error: {raw_data['errors']}")

        raw_results = raw_data.get("organic") or []
        items: List[SearchResultItem] = []
        for r in raw_results[:max_results]:
            title = r.get("title") or ""
            snippet = r.get("description") or r.get("snippet") or ""
            link = r.get("url") or ""
            if title or snippet:
                items.append(SearchResultItem(
                    title=title.strip(),
                    snippet=snippet.strip(),
                    url=link.strip(),
                    provider=self.name,
                ))

        if not items:
            raise SearchProviderError(self.name, "Returned empty search results.")
        return items


class DuckDuckGoSearchProvider(BaseSearchProvider):
    """
    Provider 4: DuckDuckGo (Zero-cost, unmetered public fallback).
    Always available as long as ddgs / duckduckgo_search is installed.
    """

    def __init__(self, timeout: float = 8.0):
        super().__init__("DuckDuckGo", timeout=timeout)

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        try:
            from ddgs import DDGS
        except ImportError:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=RuntimeWarning,
                    message=r"This package .* has been renamed to .*",
                )
                from duckduckgo_search import DDGS

        items: List[SearchResultItem] = []
        try:
            with DDGS(timeout=int(self.timeout)) as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    title = r.get("title", "")
                    snippet = r.get("body", "")
                    url = r.get("href", "")
                    if title or snippet:
                        items.append(SearchResultItem(
                            title=title.strip(),
                            snippet=snippet.strip(),
                            url=url.strip(),
                            provider=self.name,
                        ))
        except Exception as ex:
            raise SearchProviderError(self.name, f"Search failed: {ex}")

        if not items:
            raise SearchProviderError(self.name, "Returned empty search results.")
        return items


class GeminiSearchProvider(BaseSearchProvider):
    """
    Provider 5: Gemini Google Search Grounding (Final Resilient Fallback).
    Uses the user's configured gemini_api_key with google_search tool.
    """

    def __init__(self, timeout: float = 12.0):
        super().__init__("GeminiGrounding", timeout=timeout)

    def _get_key(self) -> str:
        keys = load_api_keys()
        return keys.get("gemini_api_key", "").strip()

    def is_available(self) -> bool:
        return bool(self._get_key())

    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        api_key = self._get_key()
        if not api_key:
            raise SearchProviderError(self.name, "Gemini API key not configured.")

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Search and summarize factual results for: {query}",
                config={"tools": [{"google_search": {}}]},
            )

            text = ""
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text

            text = text.strip()
            if not text:
                raise SearchProviderError(self.name, "Empty response from Gemini Grounding.")

            # Gemini grounding provides full synthesized answer
            return [SearchResultItem(
                title=f"AI Search Grounding for '{query}'",
                snippet=text,
                url="https://google.com/search?q=" + urllib.parse.quote_plus(query),
                provider=self.name,
            )]
        except Exception as ex:
            raise SearchProviderError(self.name, f"Search failed: {ex}")


class UnifiedSearchEngine:
    """
    The Master Search Orchestrator.
    Executes search queries through the fallback chain:
    GcrawlAI -> serpstack -> Zenserp -> DuckDuckGo -> Gemini Grounding.
    """

    def __init__(self, providers: Optional[List[BaseSearchProvider]] = None):
        if providers is not None:
            self.providers = providers
        else:
            self.providers = [
                GcrawlAISearchProvider(),
                SerpstackSearchProvider(),
                ZenserpSearchProvider(),
                DuckDuckGoSearchProvider(),
                GeminiSearchProvider(),
            ]

    def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Executes a search query with automatic multi-provider fallback.
        Returns a dict containing:
          - query: str
          - provider: str (the provider that succeeded)
          - results: List[SearchResultItem]
          - formatted_text: str (LLM/voice ready text)
        """
        clean_query = query.strip()
        if not clean_query:
            return {
                "query": "",
                "provider": "None",
                "results": [],
                "formatted_text": "Please provide a search query, boss.",
            }

        errors: List[str] = []
        for provider in self.providers:
            if not provider.is_available():
                logger.debug(f"[SearchEngine] Skipping {provider.name} (not configured/available).")
                continue

            try:
                logger.info(f"[SearchEngine] 🔎 Trying {provider.name} for query: {clean_query!r}...")
                results = provider.search(clean_query, max_results=max_results)
                if results:
                    logger.info(f"[SearchEngine]  {provider.name} returned {len(results)} results.")
                    formatted_text = self.format_results(clean_query, results, provider.name)
                    return {
                        "query": clean_query,
                        "provider": provider.name,
                        "results": [r.to_dict() for r in results],
                        "formatted_text": formatted_text,
                    }
            except SearchProviderError as spe:
                err_msg = str(spe)
                logger.warning(f"[SearchEngine] ⚠️ {err_msg} -> Falling back to next provider...")
                errors.append(err_msg)
            except Exception as ex:
                err_msg = f"[{provider.name}] Unexpected error: {ex}"
                logger.warning(f"[SearchEngine] ⚠️ {err_msg} -> Falling back to next provider...")
                errors.append(err_msg)

        # If all providers failed
        fail_summary = f"All web search providers failed for: '{clean_query}'."
        if errors:
            fail_summary += f" Encountered: {'; '.join(errors[-2:])}"
        logger.error(f"[SearchEngine] ❌ {fail_summary}")
        return {
            "query": clean_query,
            "provider": "Failed",
            "results": [],
            "formatted_text": f"Search failed, boss: {fail_summary}",
        }

    def compare(self, items: List[str], aspect: str = "general") -> Dict[str, Any]:
        """Compares multiple items across a specific aspect using the search engine."""
        if not items:
            return {
                "query": "",
                "provider": "None",
                "results": [],
                "formatted_text": "Please specify the items to compare, boss.",
            }

        comparison_query = f"Compare {', '.join(items)} in terms of {aspect}"
        logger.info(f"[SearchEngine]  Executing comparison: {comparison_query}")

        # First attempt Gemini Grounding for deep synthesis if available
        gemini_provider = next((p for p in self.providers if isinstance(p, GeminiSearchProvider) and p.is_available()), None)
        if gemini_provider:
            try:
                res = gemini_provider.search(comparison_query)
                if res and res[0].snippet:
                    return {
                        "query": comparison_query,
                        "provider": gemini_provider.name,
                        "results": [r.to_dict() for r in res],
                        "formatted_text": f"Comparison ({aspect.upper()}):\n\n{res[0].snippet}",
                    }
            except Exception as e:
                logger.warning(f"[SearchEngine] Gemini comparison failed: {e} — falling back to per-item search.")

        # Fallback: search each item individually and aggregate
        aggregated_results: Dict[str, List[Dict[str, Any]]] = {}
        provider_used = "Multi"
        for item in items:
            search_res = self.search(f"{item} {aspect}", max_results=3)
            aggregated_results[item] = search_res.get("results", [])
            provider_used = search_res.get("provider", provider_used)

        lines = [f"Comparison — {aspect.upper()}", "─" * 40]
        for item, results in aggregated_results.items():
            lines.append(f"\n▸ {item}:")
            if results:
                for r in results[:2]:
                    snippet = r.get("snippet", "").strip()
                    if snippet:
                        lines.append(f"  • {snippet}")
            else:
                lines.append("  • No specific data found.")

        formatted_text = "\n".join(lines)
        return {
            "query": comparison_query,
            "provider": provider_used,
            "results": aggregated_results,
            "formatted_text": formatted_text,
        }

    def execute(self, query: str = "", mode: str = "search", items: Optional[List[str]] = None, aspect: str = "general") -> Dict[str, Any]:
        """Universal entry point handling both search and compare modes."""
        mode_clean = (mode or "search").lower().strip()
        items_clean = items or []

        if items_clean and mode_clean != "compare":
            mode_clean = "compare"

        if mode_clean == "compare":
            return self.compare(items=items_clean or ([query] if query else []), aspect=aspect)

        return self.search(query=query)

    @staticmethod
    def format_results(query: str, results: List[SearchResultItem], provider_name: str) -> str:
        """Formats search items into clean, voice-and-text friendly markdown."""
        if not results:
            return f"No results found for: '{query}'."

        lines = [f"Search results for: '{query}' (via {provider_name})\n"]
        for i, r in enumerate(results, 1):
            title = r.title or "Untitled"
            lines.append(f"{i}. **{title}**")
            if r.snippet:
                lines.append(f"   {r.snippet}")
            if r.url:
                lines.append(f"   [Source: {r.url}]")
            lines.append("")

        return "\n".join(lines).strip()


# Singleton instance
_search_engine_instance: Optional[UnifiedSearchEngine] = None

def get_search_engine() -> UnifiedSearchEngine:
    """Returns the global UnifiedSearchEngine instance."""
    global _search_engine_instance
    if _search_engine_instance is None:
        _search_engine_instance = UnifiedSearchEngine()
    return _search_engine_instance
