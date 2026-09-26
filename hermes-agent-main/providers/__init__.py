"""
providers/__init__.py — Provider Profiles & Metadata for Hermes Agent
"""

from typing import Any, Dict, Optional


class ProviderProfile:
    def __init__(self, name: str):
        self.name = name

    def get_model_context_length(self, model: str) -> int:
        return 128000

    def get(self, key: str, default: Any = None) -> Any:
        if key == "context_length":
            return 128000
        return default


def get_provider_profile(provider_name: str, *args, **kwargs) -> ProviderProfile:
    return ProviderProfile(provider_name)
