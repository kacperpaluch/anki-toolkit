"""Fetch available chat models from each provider's own API."""

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

_CACHE = {}


def _fetch_simple(cache_key, url, headers, keep, fallbacks, force):
    """Fetch model ids from a `{"data": [{"id": ...}]}` endpoint.

    `keep(id)` decides which ids survive; `fallbacks` is used when the request
    fails or returns nothing. Results are sorted and cached under `cache_key`.
    """
    if cache_key in _CACHE and not force:
        return _CACHE[cache_key]
    models = []
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [
            mid for item in data.get("data", [])
            if (mid := item.get("id", "")) and keep(mid)
        ]
    except Exception as e:
        logger.warning(f"Failed to fetch models from {url}: {e}")
    if not models:
        models = list(fallbacks)
    models.sort()
    _CACHE[cache_key] = models
    return models


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

_OPENAI_SKIP = ("whisper", "tts", "dall-e", "embedding",
                "moderation", "davinci", "babbage", "curie", "ada")


def fetch_openai_models(api_key: str, force: bool = False) -> list[str]:
    return _fetch_simple(
        ("openai", api_key[:8]),
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {api_key}"},
        lambda m: not any(s in m for s in _OPENAI_SKIP)
        and m.startswith(("gpt-", "o1", "o3", "o4", "ft:")),
        ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini", "o3-mini"],
        force,
    )


# ---------------------------------------------------------------------------
# OpenRouter (public, no API key needed)
# ---------------------------------------------------------------------------

_OR_CHAT_CACHE = None

def fetch_openrouter_chat_models(force: bool = False) -> list[dict]:
    """Return OpenRouter chat models for the provider/model selectors."""
    global _OR_CHAT_CACHE
    if _OR_CHAT_CACHE is not None and not force:
        return _OR_CHAT_CACHE

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    models = []
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            pricing_raw = item.get("pricing", {})
            prompt_price = _to_float(pricing_raw.get("prompt"))
            completion_price = _to_float(pricing_raw.get("completion"))
            if prompt_price is not None:
                pricing_display = f"${prompt_price * 1_000_000:.2f}/1M tok"
            else:
                pricing_display = "?"
            models.append({
                "id": item.get("id", ""),
                "name": item.get("name", item.get("id", "")),
                "pricing": pricing_display,
                "prompt_price": prompt_price,
                "completion_price": completion_price,
                "context_length": item.get("context_length", 0),
            })
    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter models: {e}")

    models.sort(key=lambda m: (m["name"].lower(), m["id"].lower()))
    _OR_CHAT_CACHE = models
    return models


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def fetch_anthropic_models(api_key: str, force: bool = False) -> list[str]:
    return _fetch_simple(
        ("anthropic", api_key[:8]),
        "https://api.anthropic.com/v1/models",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        lambda m: True,
        [
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        ],
        force,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def fetch_models(provider: str, api_key: str = "", force: bool = False) -> list[str]:
    """Fetch available models for a provider. Returns list of model IDs."""
    if provider == "openai":
        return fetch_openai_models(api_key, force)
    elif provider == "openrouter":
        return [m["id"] for m in fetch_openrouter_chat_models(force)]
    elif provider == "anthropic":
        return fetch_anthropic_models(api_key, force)
    elif provider == "claude_cli":
        # CLI nie wystawia listy modeli — aliasy zawsze wskazują na najnowszą
        # wersję rodziny, a pełne nazwy można wpisać ręcznie.
        from .claude_cli import fetch_models as fetch_claude_models
        return fetch_claude_models()
    elif provider == "codex_cli":
        # Lokalny app-server zna modele dostępne dla zalogowanego konta —
        # nie ma tu klucza API ani endpointu do odpytania.
        from .codex_cli import fetch_models as fetch_codex_models
        try:
            return fetch_codex_models()
        except Exception as e:
            logger.error(f"Codex CLI: nie udało się pobrać modeli: {e}")
            return []
    return []
