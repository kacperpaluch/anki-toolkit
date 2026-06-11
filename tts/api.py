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
        model = config.get("openrouter_model", "openai/gpt-4o-mini-tts-2025-12-15")
        generate = _generate_openrouter
    else:
        model = config.get("model", "kokoro")
        generate = _generate_kokoro
    try:
        data = generate(text, config, voice)
    except Exception:
        _record_tts_stats(provider, model, len(text), error=True)
        raise
    _record_tts_stats(provider, model, len(text), error=False)
    return data


def _record_tts_stats(provider: str, model: str, chars: int, error: bool) -> None:
    """Best-effort usage counting — must never break audio generation.

    Counts the final outcome of one generate_audio() call (retries inside
    the provider functions are not counted separately).
    """
    try:
        from ..ai_generator.stats import record_tts
        record_tts(provider, model, chars, error)
    except Exception:
        logger.debug("TTS stats: pominięto zapis statystyk", exc_info=True)


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
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            logger.debug(
                f"Kokoro TTS OK: voice={voice}, {len(data)} B w {time.time() - t0:.1f}s"
            )
            return data
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    f"Kokoro TTS HTTP {e.code}, ponawiam za {delay}s "
                    f"(próba {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
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
    logger.debug(
        f"OpenRouter TTS: model={model}, voice={voice}, {len(text)} zn., timeout={timeout}s"
    )
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/audio/speech",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            logger.debug(
                f"OpenRouter TTS OK: voice={voice}, {len(data)} B w {time.time() - t0:.1f}s"
            )
            return data
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    f"OpenRouter TTS HTTP {e.code}, ponawiam za {delay}s "
                    f"(próba {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
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
        prompt_price = None
        if price_str:
            try:
                prompt_price = float(price_str)  # USD per character
                pricing_display = f"${prompt_price * 1000:.3f}/1k zn"
            except (ValueError, TypeError):
                pricing_display = "?"
        else:
            pricing_display = "?"
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
