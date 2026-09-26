"""
providers/__init__.py — Provider Profiles & Metadata for Hermes Agent
"""

from typing import Any, Dict, Optional


class ProviderProfile:
    def __init__(self, name: str = "openrouter"):
        self.name = name
        self.aliases = [name]
        self.default_aux_model = "nousresearch/hermes-3-llama-3.1-405b:free"
        self.default_fast_aux_model = "nousresearch/hermes-3-llama-3.1-8b:free"
        self.api_mode = "openai"
        self.auth_mode = "api_key"
        self.context_length = 128000
        self.max_tokens = 4096

    def get_model_context_length(self, model: str = "") -> int:
        return 128000

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getattr__(self, name: str) -> Any:
        if name == "aliases":
            return [self.name]
        return None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key, None)


def get_provider_profile(provider_name: str = "openrouter", *args, **kwargs) -> ProviderProfile:
    return ProviderProfile(provider_name)
