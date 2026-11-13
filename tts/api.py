"""TTS API calls — OpenRouter."""

import json
import logging
import os
import tempfile
import time
import urllib.request
import urllib.parse
import wave

from ..common import normalize_float, apply_word_replacements
from ..common.http import post_create, urlopen as safe_urlopen

logger = logging.getLogger(__name__)


def generate_audio(text: str, config: dict, voice: str) -> bytes:
    text = apply_word_replacements(text, config.get("replacements") or {})
    return _generate_openrouter(text, config, voice)


def _ensure_audio(raw: bytes, label: str) -> bytes:
    """HTTP 200 z pustym ciałem lub JSON-owym błędem zamiast MP3 nie może trafić
    do mediów — [sound:...] w polu blokuje ponowną generację na zawsze."""
    if not raw or (raw.lstrip()[:1] in (b"{", b"[") and _is_json(raw)):
        raise Exception(f"{label}: odpowiedź nie jest audio (pusta lub JSON)")
    return raw


def _is_json(raw: bytes) -> bool:
    # Raw PCM may start with "{" by chance; only a parseable body is an error.
    try:
        json.loads(raw)
    except ValueError:
        return False
    return True


# Models that answer 400 to anything but raw PCM, with the rate OpenRouter
# reports in Content-Type (checked 2026-11). The audio is encoded to MP3 here.
_PCM_ONLY_RATES = {"google/": 24000, "heygen/": 44100}


def _pcm_to_mp3(pcm: bytes, rate: int) -> bytes:
    """Encode raw PCM with the lame Anki ships for its own recordings."""
    from aqt.sound import _encode_mp3

    with tempfile.TemporaryDirectory() as folder:
        wav_path = os.path.join(folder, "speech.wav")
        mp3_path = os.path.join(folder, "speech.mp3")
        # shortcut: the rate comes from _PCM_ONLY_RATES, not from Content-Type;
        # read the header if a model's rate changes.
        with wave.open(wav_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        _encode_mp3(wav_path, mp3_path)  # deletes the WAV
        with open(mp3_path, "rb") as file:
            return file.read()


def _generate_openrouter(text: str, config: dict, voice: str) -> bytes:
    from .config import resolve_openrouter_key

    api_key = resolve_openrouter_key(config)
    if not api_key:
        raise Exception("Brak klucza API OpenRouter (Ustawienia → Konta i klucze).")

    model = config.get("openrouter_model", "hexgrad/kokoro-82m")
    pcm_rate = next((rate for prefix, rate in _PCM_ONLY_RATES.items() if model.startswith(prefix)), None)
    payload = {
        "model": model,
        "input": text,
        "response_format": "pcm" if pcm_rate else "mp3",
    }
    # No voice = the model's default voice; models without a voice list
    # (Fish Audio, ByteDance) reject an empty string and any foreign name.
    if voice:
        payload["voice"] = voice
    # 1.0 is the API default; omitting it keeps models without speed control
    # (e.g. ElevenLabs answer 400 to any `speed`) usable.
    speed = normalize_float(config.get("speed"), 1.0)
    if speed != 1.0:
        payload["speed"] = speed

    # /audio/speech ignores routing preferences (only, order, ignore, sort) —
    # its schema knows just provider.options — and does not pick the cheapest
    # host on its own.  The preference is still sent in case OpenRouter starts
    # honouring it; real pinning needs a guardrail on the API key.
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
    routing = f", provider={selected_provider} (prośba — OpenRouter może ją zignorować)" if selected_provider else ""
    logger.debug(
        f"OpenRouter TTS: model={model}, voice={voice}, {len(text)} zn., timeout={timeout}s{routing}"
    )
    t0 = time.time()
    # Paid request: a timeout may hide audio the server already billed, so it is
    # not repeated (post_create). A rerun only regenerates the missing audio.
    raw, err, _uncertain = post_create(
        "https://openrouter.ai/api/v1/audio/speech",
        json.dumps(payload).encode("utf-8"), headers,
        max_retries=max_retries, timeout=timeout, log=logger,
    )
    if err:
        raise Exception(f"OpenRouter TTS: {err}")
    raw = _ensure_audio(raw, "OpenRouter TTS")
    if pcm_rate:
        raw = _pcm_to_mp3(raw, pcm_rate)
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
        with safe_urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter TTS models: {e}")
        return []

    models = []
    for item in data.get("data", []):
        pricing_raw = item.get("pricing", {})
        price_str = pricing_raw.get("prompt") or pricing_raw.get("input") or ""
        prompt_price, pricing_display = _format_character_price(price_str)
        if normalize_float(pricing_raw.get("completion"), 0) > 0:
            pricing_display += " + opłata za audio"  # Gemini, ByteDance: billed per output too
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
        with safe_urlopen(req, timeout=15) as resp:
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
