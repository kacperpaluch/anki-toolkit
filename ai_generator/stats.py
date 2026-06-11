"""Local AI usage statistics — tokens, requests, generated fields and notes.

Counters are bucketed per calendar day, so the dashboard can aggregate over
a chosen range (today / 7 days / 30 days / all time).

Stored in user_files/usage_stats.json — Anki preserves the user_files/
directory across addon updates, unlike module directories which are wiped
and re-extracted. Thread-safe: record functions are called from
background threads (editor task, batch, workflow).
"""

import json
import os
import re
import threading
from datetime import datetime, timedelta
from typing import Optional

_LOCK = threading.Lock()
_USER_FILES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_files")
_PATH = os.path.join(_USER_FILES, "usage_stats.json")
# Pre-user_files location — migrated on first load.
_LEGACY_PATH = os.path.join(os.path.dirname(__file__), "usage_stats.json")

_MODEL_KEYS = ("requests", "errors", "input_tokens", "output_tokens", "fields")
_TTS_KEYS = ("requests", "errors", "chars", "files")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _empty() -> dict:
    return {
        "since": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "days": {},
    }


def _migrate_legacy() -> None:
    """One-time move of the stats file into user_files/ (survives addon updates)."""
    try:
        if os.path.exists(_LEGACY_PATH) and not os.path.exists(_PATH):
            os.makedirs(_USER_FILES, exist_ok=True)
            os.replace(_LEGACY_PATH, _PATH)
    except OSError:
        pass


_migrate_legacy()


def _load() -> dict:
    if os.path.exists(_PATH):
        try:
            with open(_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("days"), dict):
                return data
        except Exception:
            pass
    return _empty()


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass  # statystyki nigdy nie mogą blokować generowania


def _day_entry(data: dict) -> dict:
    return data.setdefault("days", {}).setdefault(
        _today(), {"notes_processed": 0, "models": {}}
    )


def record_request(provider: str, model: str, input_tokens: int, output_tokens: int,
                   error: bool, field_generated: bool) -> None:
    key = f"{provider}/{model}" if model else provider
    with _LOCK:
        data = _load()
        day = _day_entry(data)
        m = day["models"].setdefault(key, {k: 0 for k in _MODEL_KEYS})
        m["requests"] += 1
        if error:
            m["errors"] += 1
        m["input_tokens"] += int(input_tokens or 0)
        m["output_tokens"] += int(output_tokens or 0)
        if field_generated:
            m["fields"] += 1
        _save(data)


def record_note() -> None:
    with _LOCK:
        data = _load()
        day = _day_entry(data)
        day["notes_processed"] = int(day.get("notes_processed", 0)) + 1
        _save(data)


def record_tts(provider: str, model: str, chars: int, error: bool) -> None:
    """Count one TTS generation request (Kokoro or OpenRouter).

    chars — length of the synthesized text (TTS APIs bill per character);
    a successful request also bumps the "files" counter.
    """
    key = f"{provider}/{model}" if model else provider
    with _LOCK:
        data = _load()
        day = _day_entry(data)
        t = day.setdefault("tts", {}).setdefault(key, {k: 0 for k in _TTS_KEYS})
        t["requests"] += 1
        if error:
            t["errors"] += 1
        else:
            t["files"] += 1
        t["chars"] += int(chars or 0)
        _save(data)


def get_stats(days: Optional[int] = None,
              start: Optional[str] = None,
              end: Optional[str] = None) -> dict:
    """Aggregate stats over a range of calendar days.

    Either pass `days` (last N days) or `start`/`end` as inclusive
    "YYYY-MM-DD" bounds. No arguments = all time.

    Returns {"since": str, "notes_processed": int,
             "models": {name: {counters}}, "tts": {name: {counters}}}.
    """
    with _LOCK:
        data = _load()

    if days is not None:
        start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    models: dict = {}
    tts: dict = {}
    notes = 0
    for day, entry in data.get("days", {}).items():
        if start and day < start:
            continue
        if end and day > end:
            continue
        notes += int(entry.get("notes_processed", 0))
        for name, m in entry.get("models", {}).items():
            agg = models.setdefault(name, {k: 0 for k in _MODEL_KEYS})
            for k in _MODEL_KEYS:
                agg[k] += int(m.get(k, 0))
        for name, t in entry.get("tts", {}).items():
            agg = tts.setdefault(name, {k: 0 for k in _TTS_KEYS})
            for k in _TTS_KEYS:
                agg[k] += int(t.get(k, 0))

    return {
        "since": data.get("since", "?"),
        "notes_processed": notes,
        "models": models,
        "tts": tts,
    }


def reset_stats() -> None:
    with _LOCK:
        _save(_empty())


# ---------------------------------------------------------------------------
# Pricing — matching stats keys against the OpenRouter model catalog
# ---------------------------------------------------------------------------

def _normalize_model_name(name: str) -> str:
    """Canonical form for fuzzy matching: lowercase, no :suffix, no date, '.'→'-'.

    "claude-3-5-haiku-20241022" and OpenRouter's "claude-3.5-haiku" both
    normalize to "claude-3-5-haiku".
    """
    n = name.strip().lower()
    n = n.split(":", 1)[0]
    n = re.sub(r"-(\d{8}|\d{4}-\d{2}-\d{2})$", "", n)
    return n.replace(".", "-")


def match_pricing(stat_keys, openrouter_models) -> dict:
    """Map stats model keys ("provider/model") to (input, output) USD-per-token.

    openrouter_models: [{id, prompt_price, completion_price}, ...] from
    model_discovery.fetch_openrouter_chat_models(). Unmatched keys are absent
    from the result — the UI shows them without a cost estimate.
    """
    by_id: dict = {}
    by_name: dict = {}
    for m in openrouter_models:
        prompt_price = m.get("prompt_price")
        completion_price = m.get("completion_price")
        if prompt_price is None and completion_price is None:
            continue
        prices = (float(prompt_price or 0.0), float(completion_price or 0.0))
        mid = str(m.get("id", ""))
        if not mid:
            continue
        by_id[mid.lower()] = prices
        name_part = mid.split("/", 1)[1] if "/" in mid else mid
        by_name.setdefault(_normalize_model_name(name_part), prices)

    result: dict = {}
    for key in stat_keys:
        provider, _, model = key.partition("/")
        if not model:
            continue
        prices = None
        if provider == "openrouter":
            # The model field is already an OpenRouter id.
            prices = by_id.get(model.lower())
            name_part = model.split("/", 1)[1] if "/" in model else model
        else:
            prices = by_id.get(f"{provider}/{model}".lower())
            name_part = model
        if prices is None:
            norm = _normalize_model_name(name_part)
            prices = by_name.get(norm)
            if prices is None:
                # Prefix match handles version-suffixed ids
                # (gemini-2-0-flash ↔ gemini-2-0-flash-001).
                for candidate, candidate_prices in by_name.items():
                    if candidate.startswith(norm) or norm.startswith(candidate):
                        prices = candidate_prices
                        break
        if prices is not None:
            result[key] = prices
    return result
