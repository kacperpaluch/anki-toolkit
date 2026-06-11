from .base import BaseProvider
from .openai import OpenAIProvider
from .cometapi import CometAPIProvider
from .openrouter import OpenRouterProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider
from .mistral import MistralProvider
from .opencode_go import OpenCodeGoProvider

PROVIDERS = {
    "openai": OpenAIProvider,
    "cometapi": CometAPIProvider,
    "openrouter": OpenRouterProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "mistral": MistralProvider,
    "opencode_go": OpenCodeGoProvider,
}

# Display names for the UI — keys stay as config identifiers.
PROVIDER_LABELS = {
    "openai": "OpenAI",
    "cometapi": "CometAPI",
    "openrouter": "OpenRouter",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
    "mistral": "Mistral",
    "opencode_go": "OpenCode Go",
}


def get_provider(provider_name: str, provider_cfg: dict,
                 max_retries: int = 3, timeout: int = 30) -> BaseProvider:
    """Instantiate a provider by name using the given config section."""
    cls = PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown AI provider: '{provider_name}'. Available: {list(PROVIDERS)}")
    raw_tokens = provider_cfg.get("max_tokens")
    max_tokens = int(raw_tokens) if raw_tokens is not None else None
    raw_reasoning_effort = provider_cfg.get("reasoning_effort")
    reasoning_effort = (
        raw_reasoning_effort.strip().lower()
        if isinstance(raw_reasoning_effort, str)
        else None
    )
    return cls(
        api_key=provider_cfg.get("api_key", ""),
        model=provider_cfg.get("model", ""),
        temperature=provider_cfg.get("temperature", 0.7),
        max_retries=max_retries,
        timeout=timeout,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
