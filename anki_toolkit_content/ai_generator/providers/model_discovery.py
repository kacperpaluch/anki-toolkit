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
# Google Gemini
# ---------------------------------------------------------------------------

def fetch_google_models(api_key: str, force: bool = False) -> list[str]:
    cache_key = ("google", api_key[:8])
    if cache_key in _CACHE and not force:
        return _CACHE[cache_key]

    models = []
    try:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("models", []):
            name = item.get("name", "")
            # Model names are like "models/gemini-2.0-flash"
            mid = name.split("/")[-1]
            if not mid.startswith("gemini"):
                continue
            # Skip non-generative models
            if any(s in mid for s in ["embedding", "aqa", "text-embedding"]):
                continue
            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                models.append(mid)
    except Exception as e:
        logger.warning(f"Failed to fetch Google models: {e}")

    if not models:
        models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
    models.sort()
    _CACHE[cache_key] = models
    return models


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
# Mistral
# ---------------------------------------------------------------------------

def fetch_mistral_models(api_key: str, force: bool = False) -> list[str]:
    return _fetch_simple(
        ("mistral", api_key[:8]),
        "https://api.mistral.ai/v1/models",
        {"Authorization": f"Bearer {api_key}"},
        lambda m: m.startswith("mistral"),
        ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"],
        force,
    )


# ---------------------------------------------------------------------------
# NVIDIA NIM — models endpoint is public, no API key needed
# ---------------------------------------------------------------------------

def fetch_nvidia_models(force: bool = False) -> list[str]:
    return _fetch_simple(
        ("nvidia",),
        "https://integrate.api.nvidia.com/v1/models",
        None,
        lambda m: not any(s in m for s in ("embed", "rerank", "-ocr", "clip")),
        [
            "meta/llama-3.3-70b-instruct",
            "meta/llama-3.1-8b-instruct",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "deepseek-ai/deepseek-r1",
        ],
        force,
    )


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
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        force,
    )


# ---------------------------------------------------------------------------
# CometAPI — public, no API key needed
# ---------------------------------------------------------------------------

def fetch_cometapi_models(force: bool = False) -> list[str]:
    return _fetch_simple(
        ("cometapi",),
        "https://api.cometapi.com/api/models",
        None,
        lambda m: True,
        [
            "grok-4-1-fast-non-reasoning",
            "grok-4-1-fast-reasoning",
            "grok-3-fast-non-reasoning",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "gpt-4o",
            "gpt-4o-mini",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
        force,
    )


# ---------------------------------------------------------------------------
# OpenCode Go
# ---------------------------------------------------------------------------

def fetch_opencode_go_models(api_key: str, force: bool = False) -> list[str]:
    return _fetch_simple(
        ("opencode_go", api_key[:8]),
        "https://opencode.ai/zen/go/v1/models",
        {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (compatible; anki-toolkit/1.0)",
        },
        lambda m: True,
        [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "glm-5",
            "glm-5.1",
            "kimi-k2.5",
            "kimi-k2.6",
            "mimo-v2.5",
            "mimo-v2.5-pro",
            "minimax-m2.5",
            "minimax-m2.7",
            "qwen3.5-plus",
            "qwen3.6-plus",
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
    elif provider == "google":
        return fetch_google_models(api_key, force)
    elif provider == "openrouter":
        return [m["id"] for m in fetch_openrouter_chat_models(force)]
    elif provider == "mistral":
        return fetch_mistral_models(api_key, force)
    elif provider == "anthropic":
        return fetch_anthropic_models(api_key, force)
    elif provider == "cometapi":
        return fetch_cometapi_models(force)
    elif provider == "nvidia":
        return fetch_nvidia_models(force)
    elif provider == "opencode_go":
        return fetch_opencode_go_models(api_key, force)
    return []
