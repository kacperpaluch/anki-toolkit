"""Fetch available chat models from each provider's own API."""

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

_CACHE = {}


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def fetch_openai_models(api_key: str, force: bool = False) -> list[str]:
    cache_key = ("openai", api_key[:8])
    if cache_key in _CACHE and not force:
        return _CACHE[cache_key]

    models = []
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            mid = item.get("id", "")
            # Skip non-chat models
            if any(skip in mid for skip in [
                "whisper", "tts", "dall-e", "embedding",
                "moderation", "davinci", "babbage", "curie", "ada",
            ]):
                continue
            if mid.startswith(("gpt-", "o1", "o3", "o4", "ft:")):
                models.append(mid)
    except Exception as e:
        logger.warning(f"Failed to fetch OpenAI models: {e}")

    if not models:
        models = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini", "o3-mini"]
    models.sort()
    _CACHE[cache_key] = models
    return models


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
    """Returns [{id, name, pricing, prompt_price, completion_price, context_length}, ...].

    prompt_price / completion_price are raw USD-per-token floats (or None) —
    used by the stats tab to estimate costs.
    """
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
    cache_key = ("mistral", api_key[:8])
    if cache_key in _CACHE and not force:
        return _CACHE[cache_key]

    models = []
    try:
        req = urllib.request.Request(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            mid = item.get("id", "")
            if mid.startswith("mistral"):
                models.append(mid)
    except Exception as e:
        logger.warning(f"Failed to fetch Mistral models: {e}")

    if not models:
        models = ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"]
    models.sort()
    _CACHE[cache_key] = models
    return models


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def fetch_anthropic_models(api_key: str, force: bool = False) -> list[str]:
    cache_key = ("anthropic", api_key[:8])
    if cache_key in _CACHE and not force:
        return _CACHE[cache_key]

    models = []
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            mid = item.get("id", "")
            if mid:
                models.append(mid)
    except Exception as e:
        logger.warning(f"Failed to fetch Anthropic models: {e}")

    if not models:
        models = [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ]
    models.sort()
    _CACHE[cache_key] = models
    return models


# ---------------------------------------------------------------------------
# CometAPI — public, no API key needed
# ---------------------------------------------------------------------------

_COMETAPI_CACHE = None

def fetch_cometapi_models(force: bool = False) -> list[str]:
    global _COMETAPI_CACHE
    if _COMETAPI_CACHE is not None and not force:
        return _COMETAPI_CACHE

    models = []
    try:
        req = urllib.request.Request("https://api.cometapi.com/api/models")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            mid = item.get("id", "")
            if mid:
                models.append(mid)
    except Exception as e:
        logger.warning(f"Failed to fetch CometAPI models: {e}")

    if not models:
        models = [
            "grok-4-1-fast-non-reasoning",
            "grok-4-1-fast-reasoning",
            "grok-3-fast-non-reasoning",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "gpt-4o",
            "gpt-4o-mini",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ]
    models.sort()
    _COMETAPI_CACHE = models
    return models


# ---------------------------------------------------------------------------
# OpenCode Go
# ---------------------------------------------------------------------------

def fetch_opencode_go_models(api_key: str, force: bool = False) -> list[str]:
    cache_key = ("opencode_go", api_key[:8])
    if cache_key in _CACHE and not force:
        return _CACHE[cache_key]

    models = []
    try:
        req = urllib.request.Request(
            "https://opencode.ai/zen/go/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0 (compatible; anki-toolkit/1.0)",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            mid = item.get("id", "")
            if mid:
                models.append(mid)
    except Exception as e:
        logger.warning(f"Failed to fetch OpenCode Go models: {e}")

    if not models:
        models = [
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
        ]
    models.sort()
    _CACHE[cache_key] = models
    return models


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
    elif provider == "opencode_go":
        return fetch_opencode_go_models(api_key, force)
    return []
