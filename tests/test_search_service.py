"""
tests/test_search_service.py — Unit & Integration Tests for Multi-Provider Search Service
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloud.search_service import (
    BaseSearchProvider,
    SearchResultItem,
    SearchProviderError,
    GcrawlAISearchProvider,
    SerpstackSearchProvider,
    ZenserpSearchProvider,
    DuckDuckGoSearchProvider,
    GeminiSearchProvider,
    UnifiedSearchEngine,
    get_search_engine,
)
from actions.web_search import web_search


class MockProvider(BaseSearchProvider):
    """Test double for verifying provider fallback logic."""

    def __init__(self, name: str, should_fail: bool = False, results: list = None, is_avail: bool = True):
        super().__init__(name)
        self.should_fail = should_fail
        self.results = results or []
        self._is_avail = is_avail
        self.call_count = 0

    def is_available(self) -> bool:
        return self._is_avail

    def search(self, query: str, max_results: int = 5):
        self.call_count += 1
        if self.should_fail:
            raise SearchProviderError(self.name, "Simulated quota/network failure", status_code=429)
        return self.results


class TestSearchService(unittest.TestCase):

    def test_search_result_item_structure(self):
        item = SearchResultItem(
            title="Python Official Site",
            snippet="Python is a programming language...",
            url="https://python.org",
            provider="TestProvider",
        )
        d = item.to_dict()
        self.assertEqual(d["title"], "Python Official Site")
        self.assertEqual(d["provider"], "TestProvider")
        self.assertEqual(d["url"], "https://python.org")

    def test_provider_availability(self):
        p1 = GcrawlAISearchProvider(api_key="test_key")
        self.assertTrue(p1.is_available())

        p2 = GcrawlAISearchProvider(api_key="")
        # Without env or config key, it should report unavailable
        with patch("cloud.search_service.load_api_keys", return_value={}):
            self.assertFalse(p2.is_available())

        p3 = SerpstackSearchProvider(api_key="serp_key")
        self.assertTrue(p3.is_available())

        p4 = ZenserpSearchProvider(api_key="zen_key")
        self.assertTrue(p4.is_available())

        p5 = DuckDuckGoSearchProvider()
        self.assertTrue(p5.is_available())

    def test_single_provider_success(self):
        item = SearchResultItem(title="Result 1", snippet="Snippet 1", url="http://example.com", provider="GcrawlAI")
        p1 = MockProvider("GcrawlAI", should_fail=False, results=[item])
        p2 = MockProvider("serpstack", should_fail=False, results=[])

        engine = UnifiedSearchEngine(providers=[p1, p2])
        res = engine.search("test query")

        self.assertEqual(res["provider"], "GcrawlAI")
        self.assertEqual(len(res["results"]), 1)
        self.assertIn("Result 1", res["formatted_text"])
        self.assertEqual(p1.call_count, 1)
        self.assertEqual(p2.call_count, 0)  # Should not be called if p1 succeeds

    def test_provider_fallback_chain(self):
        """Verify that when Provider 1 fails, engine seamlessly falls back to Provider 2."""
        item2 = SearchResultItem(title="Serpstack Item", snippet="Serpstack Snippet", url="http://serpstack.com", provider="serpstack")
        p1 = MockProvider("GcrawlAI", should_fail=True)
        p2 = MockProvider("serpstack", should_fail=False, results=[item2])
        p3 = MockProvider("Zenserp", should_fail=False, results=[])

        engine = UnifiedSearchEngine(providers=[p1, p2, p3])
        res = engine.search("quantum computing")

        self.assertEqual(p1.call_count, 1)
        self.assertEqual(p2.call_count, 1)
        self.assertEqual(p3.call_count, 0)
        self.assertEqual(res["provider"], "serpstack")
        self.assertIn("Serpstack Item", res["formatted_text"])

    def test_all_api_keys_exhausted_fallback_to_ddg(self):
        """Verify that when all 3 free API keys fail, fallback falls through to DuckDuckGo/Gemini."""
        ddg_item = SearchResultItem(title="DDG Result", snippet="DDG snippet text", url="http://duckduckgo.com", provider="DuckDuckGo")
        p1 = MockProvider("GcrawlAI", should_fail=True)
        p2 = MockProvider("serpstack", should_fail=True)
        p3 = MockProvider("Zenserp", should_fail=True)
        p4 = MockProvider("DuckDuckGo", should_fail=False, results=[ddg_item])

        engine = UnifiedSearchEngine(providers=[p1, p2, p3, p4])
        res = engine.search("weather forecast")

        self.assertEqual(p1.call_count, 1)
        self.assertEqual(p2.call_count, 1)
        self.assertEqual(p3.call_count, 1)
        self.assertEqual(p4.call_count, 1)
        self.assertEqual(res["provider"], "DuckDuckGo")
        self.assertIn("DDG Result", res["formatted_text"])

    def test_empty_query_handling(self):
        engine = UnifiedSearchEngine(providers=[])
        res = engine.search("   ")
        self.assertIn("Please provide a search query", res["formatted_text"])

    def test_compare_mode(self):
        item_a = SearchResultItem(title="iPhone 16", snippet="A18 chip, 48MP camera", url="http://apple.com", provider="Mock")
        item_b = SearchResultItem(title="Samsung S24", snippet="Snapdragon 8 Gen 3", url="http://samsung.com", provider="Mock")

        p = MockProvider("MockSearch", should_fail=False, results=[item_a, item_b])
        engine = UnifiedSearchEngine(providers=[p])

        res = engine.execute(mode="compare", items=["iPhone 16", "Samsung S24"], aspect="camera")
        self.assertIn("Comparison", res["formatted_text"])
        self.assertIn("iPhone 16", res["formatted_text"])
        self.assertIn("Samsung S24", res["formatted_text"])

    def test_actions_web_search_backward_compatibility(self):
        """Verify actions.web_search.web_search() still works and returns clean string."""
        with patch.object(UnifiedSearchEngine, "execute") as mock_exec:
            mock_exec.return_value = {
                "formatted_text": "Search results for: 'hello'\n1. Hello World",
                "provider": "Mock",
            }
            res = web_search(parameters={"query": "hello"})
            self.assertIn("Hello World", res)

    def test_cloud_brain_integration(self):
        """Verify CloudBrain routes web_search to search_service natively."""
        import asyncio
        from cloud.cloud_brain import CloudBrain

        class MockFunctionCall:
            name = "web_search"
            args = {"query": "latest technology news"}
            id = "call_test_123"

        brain = CloudBrain()
        fc = MockFunctionCall()

        with patch("cloud.search_service.UnifiedSearchEngine.execute") as mock_exec:
            mock_exec.return_value = {
                "formatted_text": "1. Top Tech News 2026",
                "provider": "GcrawlAI",
            }
            resp = asyncio.run(brain._execute_tool_call(fc))
            self.assertEqual(resp.name, "web_search")
            self.assertEqual(resp.id, "call_test_123")
            self.assertIn("Top Tech News 2026", resp.response["result"])
            self.assertEqual(resp.response["provider"], "GcrawlAI")


if __name__ == "__main__":
    unittest.main()
