"""
cloud/cloud_utilities.py — ARYA Server-Side Live Utility APIs

Provides 8 keyless, high-speed public web APIs running directly on the Cloud Server:
1. Open-Meteo: Live weather forecasts by lat/lon or city name
2. Nominatim: Forward and reverse geocoding with compliant User-Agent
3. Frankfurter: Real-time currency conversions via European Central Bank
4. Wikipedia REST API: Direct factual summaries and thumbnails
5. QuickChart: Instant chart/graph image generation via Chart.js
6. Advice Slip API: Random or topic-based advice
7. JokeAPI: Safe, filtered programming and general jokes
8. TinyURL: Clean URL shortening for messaging and sharing
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CloudUtilities")

# Required User-Agent per OpenStreetMap / Nominatim usage policy
NOMINATIM_USER_AGENT = "Brahma-Echo-Assistant/2.0 (contact: abhay@brahma.internal)"
DEFAULT_TIMEOUT = 10.0


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
    """Synchronous helper for fetching JSON from an HTTP GET endpoint."""
    req_headers = {"User-Agent": "Brahma-Echo-CloudBrain/2.0"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)


def _http_get_text(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Synchronous helper for fetching raw text from an HTTP GET endpoint."""
    req_headers = {"User-Agent": "Brahma-Echo-CloudBrain/2.0"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8").strip()


# =========================================================================
# 1. Geocoding & Reverse Geocoding (Nominatim / OpenStreetMap)
# =========================================================================

def geocode_location_sync(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    reverse: bool = False,
) -> Dict[str, Any]:
    """
    Forward or reverse geocoding via Nominatim (OpenStreetMap).
    Requires custom User-Agent per OSM usage policy.
    """
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    try:
        if reverse and lat is not None and lon is not None:
            url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
            data = _http_get_json(url, headers=headers)
            if "error" in data:
                return {"success": False, "error": data.get("error")}
            return {
                "success": True,
                "display_name": data.get("display_name", ""),
                "address": data.get("address", {}),
                "lat": float(data.get("lat", lat)),
                "lon": float(data.get("lon", lon)),
            }
        elif query:
            clean_q = urllib.parse.quote(query.strip())
            url = f"https://nominatim.openstreetmap.org/search?q={clean_q}&format=json&limit=1"
            results = _http_get_json(url, headers=headers)
            if not results or not isinstance(results, list):
                return {"success": False, "error": f"No coordinates found for '{query}'."}
            top = results[0]
            return {
                "success": True,
                "query": query,
                "display_name": top.get("display_name", ""),
                "lat": float(top.get("lat", 0.0)),
                "lon": float(top.get("lon", 0.0)),
                "type": top.get("type", ""),
            }
        else:
            return {"success": False, "error": "Either query (for search) or lat/lon (for reverse) must be provided."}
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# 2. Weather Forecast & Current Conditions (Open-Meteo)
# =========================================================================

WMO_WEATHER_CODES = {
    0: "Clear sky ☀️",
    1: "Mainly clear 🌤️",
    2: "Partly cloudy ⛅",
    3: "Overcast ☁️",
    45: "Fog 🌫️",
    48: "Depositing rime fog 🌫️",
    51: "Light drizzle 🌦️",
    53: "Moderate drizzle 🌦️",
    55: "Dense drizzle 🌧️",
    61: "Slight rain 🌧️",
    63: "Moderate rain 🌧️",
    65: "Heavy rain ⛈️",
    71: "Slight snow fall ❄️",
    73: "Moderate snow fall ❄️",
    75: "Heavy snow fall ❄️",
    80: "Slight rain showers 🌦️",
    81: "Moderate rain showers 🌧️",
    82: "Violent rain showers ⛈️",
    95: "Thunderstorm ⛈️",
    96: "Thunderstorm with slight hail ⛈️",
    99: "Thunderstorm with heavy hail ⛈️",
}


def get_weather_sync(
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Fetches real-time weather using Open-Meteo.
    If a city name is given without coordinates, resolves lat/lon via Nominatim first.
    """
    resolved_name = location or "Current Location"
    if (lat is None or lon is None) and location:
        geo = geocode_location_sync(query=location)
        if not geo.get("success"):
            return {"success": False, "error": f"Could not find coordinates for '{location}'."}
        lat = geo.get("lat")
        lon = geo.get("lon")
        resolved_name = geo.get("display_name", location).split(",")[0]

    if lat is None or lon is None:
        return {"success": False, "error": "Please provide a location name or latitude/longitude."}

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current="
            f"temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
            f"&timezone=auto"
        )
        data = _http_get_json(url)
        current = data.get("current", {})
        code = current.get("weather_code", 0)
        condition_str = WMO_WEATHER_CODES.get(code, "Clear / Fair")

        return {
            "success": True,
            "location": resolved_name,
            "lat": lat,
            "lon": lon,
            "temperature_c": current.get("temperature_2m"),
            "temperature_f": round((current.get("temperature_2m", 0) * 9 / 5) + 32, 1) if current.get("temperature_2m") is not None else None,
            "apparent_temperature_c": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
            "condition": condition_str,
            "time": current.get("time"),
        }
    except Exception as e:
        logger.error(f"Open-Meteo weather fetch error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# 3. Currency Conversion (Frankfurter / European Central Bank)
# =========================================================================

def convert_currency_sync(
    amount: float,
    from_currency: str = "USD",
    to_currency: str = "INR",
) -> Dict[str, Any]:
    """
    Converts currency amounts using the Frankfurter live exchange rate API.
    """
    from_c = from_currency.strip().upper()
    to_c = to_currency.strip().upper()

    if from_c == to_c:
        return {
            "success": True,
            "amount": amount,
            "from": from_c,
            "to": to_c,
            "rate": 1.0,
            "converted_amount": amount,
        }

    try:
        url = f"https://api.frankfurter.app/latest?amount={amount}&from={from_c}&to={to_c}"
        data = _http_get_json(url)
        rates = data.get("rates", {})
        converted = rates.get(to_c)

        if converted is None:
            return {"success": False, "error": f"Currency code '{to_c}' not supported or rate not found."}

        unit_rate = round(converted / amount, 4) if amount else 0.0
        return {
            "success": True,
            "amount": amount,
            "from": from_c,
            "to": to_c,
            "converted_amount": converted,
            "rate": unit_rate,
            "date": data.get("date"),
        }
    except Exception as e:
        logger.error(f"Frankfurter currency conversion error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# 4. Wikipedia Summaries (Wikipedia REST API)
# =========================================================================

def get_wikipedia_summary_sync(query: str) -> Dict[str, Any]:
    """
    Fetches verified, factual encyclopedia summary from Wikipedia REST API.
    """
    if not query or not query.strip():
        return {"success": False, "error": "Query cannot be empty."}

    clean_title = query.strip().replace(" ", "_")
    encoded_title = urllib.parse.quote(clean_title)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

    try:
        data = _http_get_json(url)
        if data.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
            return {"success": False, "error": f"No Wikipedia article found for '{query}'."}

        return {
            "success": True,
            "title": data.get("title", query),
            "description": data.get("description", ""),
            "summary": data.get("extract", ""),
            "thumbnail_url": data.get("thumbnail", {}).get("source") if isinstance(data.get("thumbnail"), dict) else None,
            "url": data.get("content_urls", {}).get("desktop", {}).get("page") if isinstance(data.get("content_urls"), dict) else None,
        }
    except Exception as e:
        logger.error(f"Wikipedia summary error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# 5. Chart & Graph Generation (QuickChart)
# =========================================================================

def generate_chart_sync(
    chart_type: str = "bar",
    labels: Optional[List[str]] = None,
    data: Optional[List[float]] = None,
    dataset_label: str = "Values",
    title: str = "",
) -> Dict[str, Any]:
    """
    Generates a direct image URL for a Chart.js visualization using QuickChart.
    Supports: bar, line, pie, doughnut, radar, polarArea.
    """
    valid_types = {"bar", "line", "pie", "doughnut", "radar", "polarArea"}
    c_type = chart_type.lower().strip()
    if c_type not in valid_types:
        c_type = "bar"

    chart_labels = labels or ["A", "B", "C", "D"]
    chart_data = data or [10, 25, 15, 30]

    chart_config = {
        "type": c_type,
        "data": {
            "labels": chart_labels,
            "datasets": [
                {
                    "label": dataset_label,
                    "data": chart_data,
                }
            ],
        },
        "options": {
            "title": {
                "display": bool(title),
                "text": title,
            },
        },
    }

    config_json = json.dumps(chart_config, separators=(",", ":"))
    encoded_config = urllib.parse.quote(config_json)
    chart_url = f"https://quickchart.io/chart?c={encoded_config}&w=600&h=400&bkg=%2312151d"

    return {
        "success": True,
        "chart_url": chart_url,
        "chart_type": c_type,
        "title": title or dataset_label,
        "labels": chart_labels,
        "data": chart_data,
    }


# =========================================================================
# 6. Advice Slip API
# =========================================================================

def get_advice_sync(topic: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches random or topic-filtered advice from Advice Slip API.
    """
    try:
        if topic and topic.strip():
            clean_topic = urllib.parse.quote(topic.strip().lower())
            url = f"https://api.adviceslip.com/advice/search/{clean_topic}"
            data = _http_get_json(url)
            slips = data.get("slips", [])
            if slips and isinstance(slips, list):
                slip = slips[0]
                return {"success": True, "advice": slip.get("advice", ""), "topic": topic}
            # Fallback to random if no exact topic match found
            fallback_data = _http_get_json("https://api.adviceslip.com/advice")
            return {
                "success": True,
                "advice": fallback_data.get("slip", {}).get("advice", ""),
                "note": f"No direct advice found for '{topic}', here is a general thought.",
            }
        else:
            data = _http_get_json("https://api.adviceslip.com/advice")
            return {"success": True, "advice": data.get("slip", {}).get("advice", "")}
    except Exception as e:
        logger.error(f"Advice Slip error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# 7. JokeAPI (Safe Filtered Jokes)
# =========================================================================

def get_joke_sync(category: str = "Programming,Miscellaneous") -> Dict[str, Any]:
    """
    Fetches clean, safe jokes with mandatory safety blacklist flags.
    """
    safe_categories = {"Any", "Programming", "Miscellaneous", "Pun", "Spooky", "Christmas"}
    cat_clean = category.strip()
    if not any(c in safe_categories for c in cat_clean.split(",")):
        cat_clean = "Programming,Miscellaneous"

    url = (
        f"https://v2.jokeapi.dev/joke/{cat_clean}?"
        f"blacklistFlags=nsfw,religious,political,racist,sexist,explicit"
    )

    try:
        data = _http_get_json(url)
        if data.get("error"):
            return {"success": False, "error": data.get("message", "Could not fetch joke.")}

        joke_type = data.get("type", "single")
        if joke_type == "single":
            joke_text = data.get("joke", "")
        else:
            setup = data.get("setup", "")
            delivery = data.get("delivery", "")
            joke_text = f"{setup} ... {delivery}"

        return {
            "success": True,
            "category": data.get("category"),
            "type": joke_type,
            "joke": joke_text,
        }
    except Exception as e:
        logger.error(f"JokeAPI error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# 8. TinyURL (Lightweight URL Shortening)
# =========================================================================

def shorten_url_sync(url: str) -> Dict[str, Any]:
    """
    Shortens any URL using TinyURL's plain-text REST endpoint.
    """
    clean_url = (url or "").strip()
    if not clean_url:
        return {"success": False, "error": "URL cannot be empty."}

    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    try:
        api_url = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(clean_url)}"
        short = _http_get_text(api_url)
        if short.startswith("http"):
            return {"success": True, "original_url": clean_url, "short_url": short}
        return {"success": False, "error": short or "Failed to shorten URL."}
    except Exception as e:
        logger.error(f"TinyURL error: {e}")
        return {"success": False, "error": str(e)}


# =========================================================================
# Asynchronous Unified Dispatcher
# =========================================================================

async def execute_utility_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatches tool calls asynchronously without blocking the CloudBrain event loop.
    """
    if name == "get_weather":
        return await asyncio.to_thread(
            get_weather_sync,
            location=args.get("location"),
            lat=args.get("lat"),
            lon=args.get("lon"),
        )

    elif name == "geocode_location":
        return await asyncio.to_thread(
            geocode_location_sync,
            query=args.get("query"),
            lat=args.get("lat"),
            lon=args.get("lon"),
            reverse=bool(args.get("reverse")),
        )

    elif name == "convert_currency":
        amount = float(args.get("amount", 1.0))
        from_c = str(args.get("from_currency", "USD"))
        to_c = str(args.get("to_currency", "INR"))
        return await asyncio.to_thread(convert_currency_sync, amount, from_c, to_c)

    elif name == "wikipedia_summary":
        query = str(args.get("query") or args.get("topic", ""))
        return await asyncio.to_thread(get_wikipedia_summary_sync, query)

    elif name == "generate_chart":
        return await asyncio.to_thread(
            generate_chart_sync,
            chart_type=args.get("chart_type", "bar"),
            labels=args.get("labels"),
            data=args.get("data"),
            dataset_label=args.get("dataset_label", "Values"),
            title=args.get("title", ""),
        )

    elif name == "get_advice":
        return await asyncio.to_thread(get_advice_sync, topic=args.get("topic"))

    elif name == "get_joke":
        return await asyncio.to_thread(get_joke_sync, category=args.get("category", "Programming,Miscellaneous"))

    elif name == "shorten_url":
        return await asyncio.to_thread(shorten_url_sync, url=args.get("url", ""))

    return {"success": False, "error": f"Unknown utility tool: {name}"}
