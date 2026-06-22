from .base import BaseProvider, OpenAICompatProvider
from .anthropic import AnthropicProvider
from .google import GoogleProvider
from .opencode_go import OpenCodeGoProvider


# The Bearer-auth chat-completions providers differ only in endpoint, label
# and (for Mistral) reasoning_effort support — declared inline rather than in
# four near-identical files.
class OpenAIProvider(OpenAICompatProvider):
    API_URL = "https://api.openai.com/v1/chat/completions"
    LABEL = "OpenAI"


class OpenRouterProvider(OpenAICompatProvider):
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    LABEL = "OpenRouter"
    # App attribution — shows up in OpenRouter rankings/stats.
    EXTRA_HEADERS = {
        "HTTP-Referer": "https://github.com/kacperpaluch/anki-toolkit",
        "X-Title": "Anki Toolkit",
    }


class CometAPIProvider(OpenAICompatProvider):
    API_URL = "https://api.cometapi.com/v1/chat/completions"
    LABEL = "CometAPI"


class MistralProvider(OpenAICompatProvider):
    API_URL = "https://api.mistral.ai/v1/chat/completions"
    LABEL = "Mistral"
    SUPPORTS_REASONING_EFFORT = False

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
