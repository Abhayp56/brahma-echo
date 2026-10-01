"""
core/resilient_ai_client.py — Multi-Provider Resilient AI Client with Key Rotation & Cooldown

Provides an unbreakable multi-AI execution pipeline for laptop agent tools:
1. Groq Cloud (Primary — ultra-fast Llama-3 / Qwen / GPT-OSS at 500+ tokens/sec)
2. Google Gemini (Secondary — high-intelligence Flash-Lite models with v1beta endpoint)
3. OpenRouter Free (Tertiary — Qwen / Nemotron / Ling free tier fallback)

Features:
- Smart Key Rotation: Round-robin load balancing across all available API keys.
- Automatic Cooldown: If any key encounters 429 (Rate Limit / Quota Exceeded),
  it is marked with a 60-second cooldown and automatically skips to the next key.
- Provider Waterfall: Automatically cascades from Groq -> Gemini -> OpenRouter.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ResilientAIClient")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

COOLDOWN_SECONDS = 60.0


class KeyPool:
    """Manages a pool of API keys with round-robin rotation and cooldowns."""

    def __init__(self, name: str, keys: List[str]):
        self.name = name
        self.keys = [k.strip() for k in keys if k and k.strip()]
        self._index = 0
        self._cooldowns: Dict[str, float] = {}

    def get_next_key(self) -> Optional[str]:
        if not self.keys:
            return None

        now = time.time()
        # Clean expired cooldowns
        self._cooldowns = {k: cd for k, cd in self._cooldowns.items() if cd > now}

        total_keys = len(self.keys)
        for _ in range(total_keys):
            candidate = self.keys[self._index % total_keys]
            self._index = (self._index + 1) % total_keys

            if candidate not in self._cooldowns:
                return candidate

        # If all keys are in cooldown, pick the one that expires soonest
        soonest_key = min(self.keys, key=lambda k: self._cooldowns.get(k, 0))
        remaining = max(0.0, self._cooldowns.get(soonest_key, 0) - now)
        if remaining > 0:
            logger.warning(f"[{self.name}] All keys in cooldown. Waiting {remaining:.1f}s for key to reset...")
            time.sleep(min(remaining, 3.0))
        return soonest_key

    def mark_rate_limited(self, key: str):
        now = time.time()
        self._cooldowns[key] = now + COOLDOWN_SECONDS
        logger.warning(f"[{self.name}] Key ...{key[-6:]} hit rate limit. Placed on {COOLDOWN_SECONDS}s cooldown.")


class ResilientAIClient:
    """Unified multi-AI client orchestrating Groq, Gemini, and OpenRouter."""

    def __init__(self):
        self.groq_pool = KeyPool("Groq", [])
        self.gemini_pool = KeyPool("Gemini", [])
        self.openrouter_pool = KeyPool("OpenRouter", [])
        self.reload_keys()

    def reload_keys(self):
        if not API_CONFIG_PATH.exists():
            return

        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # Groq keys
            groq_keys = cfg.get("groq_api_keys", [])
            if not groq_keys and cfg.get("groq_api_key"):
                groq_keys = [cfg["groq_api_key"]]
            self.groq_pool = KeyPool("Groq", groq_keys)

            # Gemini keys
            gemini_keys = cfg.get("gemini_api_keys", [])
            if not gemini_keys and cfg.get("gemini_api_key"):
                gemini_keys = [cfg["gemini_api_key"]]
            self.gemini_pool = KeyPool("Gemini", gemini_keys)

            # OpenRouter keys
            openrouter_keys = cfg.get("openrouter_api_keys", [])
            if not openrouter_keys and cfg.get("openrouter_api_key"):
                openrouter_keys = [cfg["openrouter_api_key"]]
            self.openrouter_pool = KeyPool("OpenRouter", openrouter_keys)

            logger.info(
                f"[ResilientAIClient] Initialized Key Pools -> "
                f"Groq: {len(self.groq_pool.keys)} keys, "
                f"Gemini: {len(self.gemini_pool.keys)} keys, "
                f"OpenRouter: {len(self.openrouter_pool.keys)} keys"
            )
        except Exception as e:
            logger.error(f"[ResilientAIClient] Failed to load keys from {API_CONFIG_PATH}: {e}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str:
        """
        Executes generation with automatic multi-key rotation and multi-provider fallback.
        Waterfall order: Groq -> Gemini -> OpenRouter
        """
        # 1. Try Groq (Ultra-fast, high RPM free tier)
        result = self._try_groq(prompt, system_prompt, json_mode, temperature)
        if result is not None:
            return result

        # 2. Fallback to Gemini Flash-Lite
        logger.info("[ResilientAIClient] Groq unavailable or exhausted. Cascading to Gemini...")
        result = self._try_gemini(prompt, system_prompt, json_mode, temperature)
        if result is not None:
            return result

        # 3. Fallback to OpenRouter Free
        logger.info("[ResilientAIClient] Gemini unavailable or exhausted. Cascading to OpenRouter Free...")
        result = self._try_openrouter(prompt, system_prompt, json_mode, temperature)
        if result is not None:
            return result

        raise RuntimeError("All AI providers (Groq, Gemini, OpenRouter) and key pools were exhausted or failed.")

    def _try_groq(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        temperature: float,
    ) -> Optional[str]:
        if not self.groq_pool.keys:
            return None

        from groq import Groq

        models_to_try = [
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        ]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Try across available keys
        for _ in range(len(self.groq_pool.keys) * 2):
            key = self.groq_pool.get_next_key()
            if not key:
                break

            client = Groq(api_key=key)

            for model_name in models_to_try:
                try:
                    kwargs: Dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    resp = client.chat.completions.create(**kwargs)
                    text = resp.choices[0].message.content or ""
                    if text.strip():
                        return text.strip()

                except Exception as exc:
                    err_msg = str(exc)
                    if "429" in err_msg or "rate_limit" in err_msg.lower() or "too many requests" in err_msg.lower():
                        self.groq_pool.mark_rate_limited(key)
                        break  # Move to next key immediately
                    elif "model_not_found" in err_msg or "404" in err_msg:
                        continue  # Try next model on same key
                    else:
                        logger.warning(f"[Groq] Model {model_name} error with key ...{key[-4:]}: {exc}")
                        break

        return None

    def _try_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        temperature: float,
    ) -> Optional[str]:
        if not self.gemini_pool.keys:
            return None

        from google import genai
        from google.genai import types

        # Verified working models on user's API key
        models_to_try = [
            "models/gemini-3.5-flash-lite",
            "models/gemini-flash-lite-latest",
        ]

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        for _ in range(len(self.gemini_pool.keys) * 2):
            key = self.gemini_pool.get_next_key()
            if not key:
                break

            client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})

            for model_name in models_to_try:
                try:
                    config = types.GenerateContentConfig(
                        temperature=temperature,
                    )
                    if json_mode:
                        config.response_mime_type = "application/json"

                    resp = client.models.generate_content(
                        model=model_name,
                        contents=full_prompt,
                        config=config,
                    )
                    if resp and resp.text:
                        return resp.text.strip()

                except Exception as exc:
                    err_msg = str(exc)
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                        self.gemini_pool.mark_rate_limited(key)
                        break
                    elif "404" in err_msg or "not found" in err_msg.lower():
                        continue
                    else:
                        logger.warning(f"[Gemini] Model {model_name} error with key ...{key[-4:]}: {exc}")
                        break

        return None

    def _try_openrouter(
        self,
        prompt: str,
        system_prompt: Optional[str],
        json_mode: bool,
        temperature: float,
    ) -> Optional[str]:
        if not self.openrouter_pool.keys:
            return None

        import requests

        models_to_try = [
            "qwen/qwen3.8-27b:free",
            "inclusionai/ling-3.0-flash-sante:free",
            "liquid/lfm-2.5-2.6b:free",
            "nvidia/nemotron-3.5-lightning:free",
        ]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for _ in range(len(self.openrouter_pool.keys) * 2):
            key = self.openrouter_pool.get_next_key()
            if not key:
                break

            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }

            for model_name in models_to_try:
                try:
                    payload: Dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if json_mode:
                        payload["response_format"] = {"type": "json_object"}

                    r = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=30,
                    )

                    if r.status_code == 200:
                        data = r.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content.strip():
                            return content.strip()
                    elif r.status_code == 429:
                        self.openrouter_pool.mark_rate_limited(key)
                        break
                    elif r.status_code == 404:
                        continue
                    else:
                        logger.warning(f"[OpenRouter] Model {model_name} returned {r.status_code}: {r.text[:100]}")
                        break

                except Exception as exc:
                    logger.warning(f"[OpenRouter] Request failed: {exc}")
                    break

        return None


# Global singleton instance
resilient_ai = ResilientAIClient()
