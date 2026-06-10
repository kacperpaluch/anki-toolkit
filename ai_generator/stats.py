"""Local AI usage statistics — tokens, requests, generated fields and notes.

Counters are bucketed per calendar day, so the dashboard can aggregate over
a chosen range (today / 7 days / 30 days / all time).

Stored in usage_stats.json next to this file (gitignored, like the audio
normalizer history). Thread-safe: record functions are called from
background threads (editor task, batch, workflow).
"""

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Optional

_LOCK = threading.Lock()
_PATH = os.path.join(os.path.dirname(__file__), "usage_stats.json")

_MODEL_KEYS = ("requests", "errors", "input_tokens", "output_tokens", "fields")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _empty() -> dict:
    return {
        "since": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "days": {},
    }


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


def get_stats(days: Optional[int] = None) -> dict:
    """Aggregate stats over the last `days` calendar days (None = all time).

    Returns {"since": str, "notes_processed": int, "models": {name: {counters}}}.
    """
    with _LOCK:
        data = _load()

    cutoff = None
    if days is not None:
        cutoff = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    models: dict = {}
    notes = 0
    for day, entry in data.get("days", {}).items():
        if cutoff and day < cutoff:
            continue
        notes += int(entry.get("notes_processed", 0))
        for name, m in entry.get("models", {}).items():
            agg = models.setdefault(name, {k: 0 for k in _MODEL_KEYS})
            for k in _MODEL_KEYS:
                agg[k] += int(m.get(k, 0))

    return {
        "since": data.get("since", "?"),
        "notes_processed": notes,
        "models": models,
    }


def reset_stats() -> None:
    with _LOCK:
        _save(_empty())
