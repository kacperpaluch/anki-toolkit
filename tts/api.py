"""TTS API calls — Kokoro (local) and OpenRouter."""

import json
import logging
import time
import urllib.error
import urllib.request

from ..common import normalize_float, extract_http_error
from ..common.http import RETRYABLE_STATUS_CODES

logger = logging.getLogger(__name__)


def generate_audio(text: str, config: dict, voice: str) -> bytes:
    provider = config.get("tts_provider", "kokoro")
    if provider == "openrouter":
        return _generate_openrouter(text, config, voice)
    return _generate_kokoro(text, config, voice)


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
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise Exception(f"Kokoro API Error: {extract_http_error(e)}")
        except urllib.error.URLError as e:
            raise Exception(f"Kokoro Connection Error: {e}")

    raise Exception("Kokoro API request failed after retries.")


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

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    max_retries = int(config.get("max_retries", 3))
    timeout = int(config.get("timeout", 60))
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/audio/speech",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise Exception(f"OpenRouter TTS Error: {extract_http_error(e)}")
        except urllib.error.URLError as e:
            raise Exception(f"OpenRouter Connection Error: {e}")

    raise Exception("OpenRouter TTS request failed after retries.")


# ---------------------------------------------------------------------------
# OpenRouter model/voice discovery
# ---------------------------------------------------------------------------

_OR_MODELS_CACHE = None


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
        if price_str:
            try:
                price_per_1k = float(price_str) * 1000
                pricing_display = f"${price_per_1k:.3f}/1k zn"
            except (ValueError, TypeError):
                pricing_display = "?"
        else:
            pricing_display = "?"
        models.append({
            "id": item.get("id", ""),
            "name": item.get("name", item.get("id", "")),
            "voices": item.get("supported_voices", []),
            "pricing": pricing_display,
        })
    models.sort(key=lambda m: m["name"].lower())
    _OR_MODELS_CACHE = models
    return models
