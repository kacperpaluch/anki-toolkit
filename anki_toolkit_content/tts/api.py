"""TTS API calls — Kokoro (local) and OpenRouter."""

import json
import logging
import time
import urllib.request
import urllib.parse

from ..common import normalize_float, apply_word_replacements
from ..common.http import post_json

logger = logging.getLogger(__name__)


def generate_audio(text: str, config: dict, voice: str) -> bytes:
    text = apply_word_replacements(text, config.get("replacements") or {})
    provider = config.get("tts_provider", "kokoro")
    if provider == "openrouter":
        generate = _generate_openrouter
    else:
        generate = _generate_kokoro
    return generate(text, config, voice)


def _ensure_audio(raw: bytes, label: str) -> bytes:
    """HTTP 200 z pustym ciałem lub JSON-owym błędem zamiast MP3 nie może trafić
    do mediów — [sound:...] w polu blokuje ponowną generację na zawsze."""
    if not raw or raw.lstrip()[:1] in (b"{", b"["):
        raise Exception(f"{label}: odpowiedź nie jest audio (pusta lub JSON)")
    return raw


def _generate_kokoro(text: str, config: dict, voice: str) -> bytes:
    url = config.get("api_url", "http://localhost:8880/v1/audio/speech")
    payload = {
        "model": config.get("model", "kokoro"),
        "input": text,
        "voice": voice,
        "speed": normalize_float(config.get("speed"), 0.9),
        "response_format": "mp3",
    }
    headers = {"Content-Type": "application/json"}

    max_retries = int(config.get("max_retries", 3))
    timeout = int(config.get("timeout", 60))
    logger.debug(f"Kokoro TTS: voice={voice}, {len(text)} zn., timeout={timeout}s")
    t0 = time.time()
    raw, err = post_json(
        url, json.dumps(payload).encode("utf-8"), headers,
        max_retries=max_retries, timeout=timeout, log=logger,
    )
    if err:
        raise Exception(f"Kokoro API Error: {err}")
    raw = _ensure_audio(raw, "Kokoro API")
    logger.debug(
        f"Kokoro TTS OK: voice={voice}, {len(raw)} B w {time.time() - t0:.1f}s"
    )
    return raw


def _generate_openrouter(text: str, config: dict, voice: str) -> bytes:
    from .config import resolve_openrouter_key

    api_key = resolve_openrouter_key(config)
    if not api_key:
        raise Exception("Brak klucza API OpenRouter w ustawieniach TTS.")

    model = config.get("openrouter_model", "openai/gpt-4o-mini-tts-2025-12-15")
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }
    speed = config.get("speed")
    if speed is not None:
        payload["speed"] = normalize_float(speed, 0.9)

    # An empty value keeps OpenRouter's normal price-weighted routing and
    # provider failover.  A selected provider is intentionally strict: users
    # choose it to control both the host and its price.
    selected_provider = str(config.get("openrouter_provider") or "").strip()
    if selected_provider:
        payload["provider"] = {
            "only": [selected_provider],
            "allow_fallbacks": False,
        }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        # App attribution — pokazuje się w statystykach/rankingach OpenRouter.
        "HTTP-Referer": "https://github.com/kacperpaluch/anki-toolkit",
        "X-Title": "Anki Toolkit",
    }

    max_retries = int(config.get("max_retries", 3))
    timeout = int(config.get("timeout", 60))
    routing = f", provider={selected_provider} (bez fallbacku)" if selected_provider else ""
    logger.debug(
        f"OpenRouter TTS: model={model}, voice={voice}, {len(text)} zn., timeout={timeout}s{routing}"
    )
    t0 = time.time()
    raw, err = post_json(
        "https://openrouter.ai/api/v1/audio/speech",
        json.dumps(payload).encode("utf-8"), headers,
        max_retries=max_retries, timeout=timeout, log=logger,
    )
    if err:
        raise Exception(f"OpenRouter TTS Error: {err}")
    raw = _ensure_audio(raw, "OpenRouter TTS")
    logger.debug(
        f"OpenRouter TTS OK: voice={voice}, {len(raw)} B w {time.time() - t0:.1f}s"
    )
    return raw


# ---------------------------------------------------------------------------
# OpenRouter model/voice discovery
# ---------------------------------------------------------------------------

_OR_MODELS_CACHE = None


def _format_character_price(price) -> tuple[float | None, str]:
    """Return OpenRouter's character price in a compact, human-readable form."""
    try:
        value = float(price)
    except (ValueError, TypeError):
        return None, "?"
    return value, f"${value * 1_000_000:.3f}/1 mln zn"


def fetch_openrouter_tts_models(force: bool = False) -> list[dict]:
    global _OR_MODELS_CACHE
    if _OR_MODELS_CACHE is not None and not force:
        return _OR_MODELS_CACHE

    url = "https://openrouter.ai/api/v1/models?output_modalities=speech"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter TTS models: {e}")
        return []

    models = []
    for item in data.get("data", []):
        pricing_raw = item.get("pricing", {})
        price_str = pricing_raw.get("prompt") or pricing_raw.get("input") or ""
        prompt_price, pricing_display = _format_character_price(price_str)
        models.append({
            "id": item.get("id", ""),
            "name": item.get("name", item.get("id", "")),
            "voices": item.get("supported_voices", []),
            "pricing": pricing_display,
            "prompt_price": prompt_price,
        })
    models.sort(key=lambda m: m["name"].lower())
    _OR_MODELS_CACHE = models
    return models


def fetch_openrouter_tts_providers(model_id: str, api_key: str = "") -> list[dict]:
    """Fetch provider endpoints and their individual TTS prices for one model.

    The models endpoint only exposes the lowest price.  OpenRouter's endpoint
    endpoint contains the per-provider records needed to let a user pin one.
    It requires authentication, hence the optional key for the settings dialog.
    """
    model_id = str(model_id or "").strip()
    if not model_id or "/" not in model_id:
        return []

    url = "https://openrouter.ai/api/v1/models/{}/endpoints".format(
        urllib.parse.quote(model_id, safe="/@:-")
    )
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter TTS providers for {model_id}: {e}")
        return []

    records = data.get("data", data)
    endpoints = records.get("endpoints", []) if isinstance(records, dict) else []
    providers = []
    seen = set()
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        # provider_slug is the routing value; provider_name is only for display.
        slug = str(
            endpoint.get("provider_slug") or endpoint.get("provider_tag")
            or endpoint.get("tag") or ""
        ).strip()
        name = str(endpoint.get("provider_name") or slug).strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        pricing_raw = endpoint.get("pricing") or {}
        if isinstance(pricing_raw, list):
            # Some modality endpoint APIs use a list of billing records.
            price = next(
                (p.get("cost_usd") for p in pricing_raw if isinstance(p, dict)), None
            )
        else:
            price = pricing_raw.get("prompt") or pricing_raw.get("input")
        prompt_price, pricing = _format_character_price(price)
        providers.append({
            "id": slug,
            "name": name,
            "pricing": pricing,
            "prompt_price": prompt_price,
        })
    providers.sort(key=lambda p: (p["prompt_price"] is None, p["prompt_price"] or 0, p["name"].lower()))
    return providers
