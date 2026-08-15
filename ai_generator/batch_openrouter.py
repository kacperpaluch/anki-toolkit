"""OpenRouter Batch API wire protocol.

Submit is an inline JSON body (no file upload): one batch per model, each
request inherits the batch-level model. Results come back inline in the batch
object's `results` field — there is no separate results-download endpoint, so
polling and applying are a single GET. Result shape matches OpenAI's
chat.completions, so parsing reuses the same extraction as batch_openai.

Model naming: OpenRouter routes the batch endpoint through the model's
`:batch` variant (a distinct slug like `google/gemini-3.7-flash:batch`), so
`_batch_model()` appends `:batch` to whatever model the user configured —
there is no separate batch-model field in the config.
"""

import json
import logging

from ..common import fetch_url, post_json
from .providers.openai_compat import (
    add_reasoning_effort_if_supported,
    add_temperature_if_supported,
)

logger = logging.getLogger(__name__)

OPENROUTER_BATCHES_URL = "https://openrouter.ai/api/beta/batches"
_TERMINAL = {"completed", "failed", "expired", "cancelled"}


def _batch_model(model: str) -> str:
    """OpenRouter's batch endpoint consumes the model's `:batch` variant, which
    is a distinct slug (e.g. `google/gemini-3.7-flash:batch`), not the plain
    model. No config field needed — derive it by appending `:batch`."""
    model = model.strip()
    if not model or model.endswith(":batch"):
        return model
    return model + ":batch"


def _retries(config: dict) -> int:
    return int(config.get("max_retries", 3))


def _timeout(config: dict) -> int:
    return int(config.get("request_timeout", 30))


def _headers(config: dict):
    api_key = (config.get("providers", {}).get("openrouter", {}) or {}).get(
        "api_key", ""
    )
    if not api_key or api_key.startswith("YOUR_"):
        return None
    return {
        "Authorization": f"Bearer {api_key}",
        # App attribution, same as the sync OpenRouterProvider (providers/__init__.py).
        "HTTP-Referer": "https://github.com/kacperpaluch/anki-toolkit",
        "X-Title": "Anki Toolkit",
    }


def submit_batch(items, config: dict) -> tuple:
    """Create one OpenRouter batch for items of a single model.

    Return (batch_id, error). `endpoint` and `model` MUST be serialized before
    `requests` — the API stream-parses the body and 400s otherwise.
    """
    headers = _headers(config)
    if headers is None:
        return None, "Brak klucza API OpenRouter — uzupełnij w Ustawieniach."
    or_cfg = config.get("providers", {}).get("openrouter", {}) or {}
    default_temp = or_cfg.get("temperature", 0.2)
    reasoning = or_cfg.get("reasoning_effort")
    reasoning = reasoning.strip().lower() if isinstance(reasoning, str) else None

    model = _batch_model(items[0]["model"])
    requests = []
    for item in items:
        body = {"messages": [{"role": "user", "content": item["prompt"]}]}
        temperature = (
            item["temperature"]
            if item["temperature"] is not None
            else default_temp
        )
        add_temperature_if_supported(body, model, temperature)
        add_reasoning_effort_if_supported(body, model, reasoning)
        requests.append({"custom_id": item["custom_id"], "body": body})

    # Order matters (stream-parsing on OpenRouter's side): endpoint + model first.
    payload = json.dumps({
        "endpoint": "/v1/chat/completions",
        "model": model,
        "requests": requests,
    }, ensure_ascii=False).encode("utf-8")
    raw, err = post_json(
        OPENROUTER_BATCHES_URL,
        payload,
        dict(headers, **{"Content-Type": "application/json"}),
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
    logger.info(
        f"Batch OpenRouter wysłany: {batch_id} "
        f"({len(items)} zapytań, model {model})"
    )
    return batch_id, None


def _parse_result(entry: dict) -> dict:
    """Normalize one inline result item → {custom_id, ok, text} (OpenAI shape)."""
    response = entry.get("response") or {}
    body = response.get("body") or {}
    text = None
    if response.get("status_code") == 200:
        choices = body.get("choices") or []
        if choices:
            text = ((choices[0].get("message") or {}).get("content")) or None
    return {
        "custom_id": entry.get("custom_id"),
        "ok": bool(text),
        "text": text,
    }


def poll_batch(record: dict, config: dict) -> tuple:
    """Return (status, normalized results) for one OpenRouter batch.

    Results are inline in the batch object once it reaches a terminal state;
    there is no output-file download. Terminal statuses come straight from the
    API docs: completed/failed/expired/cancelled.
    """
    headers = _headers(config)
    if headers is None:
        return "error", None
    raw = fetch_url(
        f"{OPENROUTER_BATCHES_URL}/{record['id']}",
        headers=headers,
        timeout=_timeout(config),
    )
    if raw is None:
        return "error", None
    try:
        info = json.loads(raw.decode("utf-8"))
    except ValueError:
        return "error", None
    if info.get("status") not in _TERMINAL:
        return "pending", None
    results = [_parse_result(e) for e in (info.get("results") or [])]
    return "ended", results