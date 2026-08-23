"""Anthropic Batch API wire protocol."""

import json
import logging

from ..common import fetch_url, post_json

logger = logging.getLogger(__name__)

ANTHROPIC_BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"
ANTHROPIC_VERSION = "2023-06-01"


def _retries(config: dict) -> int:
    return int(config.get("max_retries", 3))


def _timeout(config: dict) -> int:
    return int(config.get("request_timeout", 30))


def _headers(config: dict):
    api_key = (config.get("providers", {}).get("anthropic", {}) or {}).get(
        "api_key", ""
    )
    if not api_key or api_key.startswith("YOUR_"):
        return None
    return {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}


def first_text(content):
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            return block["text"]
    return None


def submit_batch(items, config: dict) -> tuple:
    """Submit one Anthropic batch and return (batch_id, error)."""
    headers = _headers(config)
    if headers is None:
        return None, "Brak klucza API Anthropic — uzupełnij w Ustawieniach."
    a_cfg = config.get("providers", {}).get("anthropic", {}) or {}
    raw_max = a_cfg.get("max_tokens")
    max_tokens = int(raw_max) if raw_max is not None else 2048
    requests = [{
        "custom_id": item["custom_id"],
        "params": {
            "model": item["model"],
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": item["prompt"]}],
        },
    } for item in items]
    body = json.dumps({"requests": requests}).encode("utf-8")
    raw, err = post_json(
        ANTHROPIC_BATCHES_URL,
        body,
        dict(headers, **{"content-type": "application/json"}),
        max_retries=_retries(config),
        timeout=_timeout(config),
        log=logger,
    )
    if raw is None:
        return None, err
    try:
        batch_id = json.loads(raw.decode("utf-8")).get("id")
    except ValueError as e:
        return None, f"Nieczytelna odpowiedź API: {e}"
    if not batch_id:
        return None, "Nieoczekiwana odpowiedź API (brak id batcha)."
    logger.info(f"Batch Anthropic wysłany: {batch_id} ({len(items)} zapytań)")
    return batch_id, None


def poll_batch(record: dict, config: dict) -> tuple:
    """Return (status, normalized results) for one Anthropic batch."""
    headers = _headers(config)
    if headers is None:
        return "error", None
    raw = fetch_url(
        f"{ANTHROPIC_BATCHES_URL}/{record['id']}",
        headers=headers,
        timeout=_timeout(config),
    )
    if raw is None:
        return "error", None
    try:
        info = json.loads(raw.decode("utf-8"))
    except ValueError:
        return "error", None
    if info.get("processing_status") != "ended":
        return "pending", None
    results_url = info.get("results_url") or (
        f"{ANTHROPIC_BATCHES_URL}/{record['id']}/results"
    )
    raw_res = fetch_url(results_url, headers=headers, timeout=_timeout(config))
    if raw_res is None:
        return "error", None
    results = []
    for line in raw_res.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        result = entry.get("result", {}) or {}
        message = result.get("message", {}) or {}
        text = first_text(message.get("content")) if result.get("type") == "succeeded" else None
        results.append({
            "custom_id": entry.get("custom_id"),
            "ok": result.get("type") == "succeeded" and bool(text),
            "text": text,
        })
    return "ended", results
