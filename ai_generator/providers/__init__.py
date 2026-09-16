from .base import BaseProvider, OpenAICompatProvider
from .anthropic import AnthropicProvider
from .codex_cli import CodexCLIProvider
from .claude_cli import ClaudeCLIProvider


# The Bearer-auth chat-completions providers differ only in endpoint and
# label — declared inline rather than in near-identical files.
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


PROVIDERS = {
    "openai": OpenAIProvider,
    "openrouter": OpenRouterProvider,
    "anthropic": AnthropicProvider,
    "codex_cli": CodexCLIProvider,
    "claude_cli": ClaudeCLIProvider,
}

# Display names for the UI — keys stay as config identifiers.
PROVIDER_LABELS = {
    "openai": "OpenAI",
    "openrouter": "OpenRouter",
    "anthropic": "Anthropic",
    "codex_cli": "Codex CLI (ChatGPT)",
    "claude_cli": "Claude CLI (subskrypcja)",
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
        options=provider_cfg,
    )
