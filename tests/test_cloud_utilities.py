"""
tests/test_cloud_utilities.py — Automated Unit Tests for ARYA Live Utility APIs
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
import unittest
from cloud.cloud_utilities import (
    geocode_location_sync,
    get_weather_sync,
    convert_currency_sync,
    get_wikipedia_summary_sync,
    generate_chart_sync,
    get_advice_sync,
    get_joke_sync,
    shorten_url_sync,
    execute_utility_tool,
)
from core.tools_schema import TOOL_DECLARATIONS


class TestCloudUtilities(unittest.TestCase):
    def test_schema_registration(self):
        tool_names = {t["name"] for t in TOOL_DECLARATIONS}
        expected = {
            "get_weather",
            "geocode_location",
            "convert_currency",
            "wikipedia_summary",
            "generate_chart",
            "get_advice",
            "get_joke",
            "shorten_url",
        }
        for name in expected:
            self.assertIn(name, tool_names, f"Tool '{name}' must be registered in TOOL_DECLARATIONS")

    def test_geocoding_nominatim(self):
        res = geocode_location_sync(query="London")
        self.assertTrue(res.get("success"), f"Geocoding failed: {res}")
        self.assertAlmostEqual(res.get("lat"), 51.5, delta=0.5)
        self.assertAlmostEqual(res.get("lon"), -0.1, delta=0.5)

    def test_open_meteo_weather(self):
        # Test with direct lat/lon (e.g. Mumbai)
        res = get_weather_sync(lat=19.076, lon=72.877)
        self.assertTrue(res.get("success"), f"Weather failed: {res}")
        self.assertIsNotNone(res.get("temperature_c"))
        self.assertIn("condition", res)

    def test_currency_conversion(self):
        res = convert_currency_sync(100, "USD", "INR")
        self.assertTrue(res.get("success"), f"Currency conversion failed: {res}")
        self.assertGreater(res.get("converted_amount", 0), 1000)
        self.assertEqual(res.get("from"), "USD")
        self.assertEqual(res.get("to"), "INR")

    def test_wikipedia_summary(self):
        res = get_wikipedia_summary_sync("Albert Einstein")
        self.assertTrue(res.get("success"), f"Wikipedia summary failed: {res}")
        self.assertIn("Einstein", res.get("title", ""))
        self.assertIn("physicist", res.get("summary", "").lower())

    def test_quickchart_generation(self):
        res = generate_chart_sync(
            chart_type="bar",
            labels=["A", "B", "C"],
            data=[10, 20, 30],
            title="Test Chart",
        )
        self.assertTrue(res.get("success"), f"Chart generation failed: {res}")
        self.assertTrue(res.get("chart_url", "").startswith("https://quickchart.io/chart?c="))

    def test_advice_slip(self):
        res = get_advice_sync()
        self.assertTrue(res.get("success"), f"Advice slip failed: {res}")
        self.assertTrue(len(res.get("advice", "")) > 0)

    def test_joke_api(self):
        res = get_joke_sync(category="Programming")
        self.assertTrue(res.get("success"), f"JokeAPI failed: {res}")
        self.assertIn("joke", res)
        self.assertTrue(len(res["joke"]) > 0)

    def test_tinyurl_shorten(self):
        res = shorten_url_sync("https://en.wikipedia.org/wiki/Artificial_intelligence")
        self.assertTrue(res.get("success"), f"TinyURL failed: {res}")
        self.assertTrue(res.get("short_url", "").startswith("https://tinyurl.com/"))

    def test_async_dispatcher(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(
                execute_utility_tool("convert_currency", {"amount": 50, "from_currency": "EUR", "to_currency": "USD"})
            )
            self.assertTrue(res.get("success"))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
