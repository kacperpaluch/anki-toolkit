"""OpenAI Files and Batch API wire protocol."""

import json
import logging
import urllib.request
import uuid

from ..common import fetch_url, post_json
from .providers.openai_compat import (
    add_reasoning_effort_if_supported,
    add_temperature_if_supported,
)

logger = logging.getLogger(__name__)

OPENAI_FILES_URL = "https://api.openai.com/v1/files"
OPENAI_BATCHES_URL = "https://api.openai.com/v1/batches"
_TERMINAL = {"completed", "failed", "expired", "cancelled"}


def _retries(config: dict) -> int:
    return int(config.get("max_retries", 3))


def _timeout(config: dict) -> int:
    return int(config.get("request_timeout", 30))


def _key(config: dict):
    api_key = (config.get("providers", {}).get("openai", {}) or {}).get(
        "api_key", ""
    )
    if not api_key or api_key.startswith("YOUR_"):
        return None
    return api_key


def _multipart(
    fields: dict, file_field: str, filename: str, file_bytes: bytes
) -> tuple:
    boundary = "----ankitoolkit" + uuid.uuid4().hex
    out = bytearray()
    for key, value in fields.items():
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        out += f"{value}\r\n".encode()
    out += f"--{boundary}\r\n".encode()
    out += (
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\n'
    ).encode()
    out += b"Content-Type: application/jsonl\r\n\r\n"
    out += file_bytes + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), boundary


def _delete_file(file_id: str, api_key: str, timeout: int) -> None:
    try:
        req = urllib.request.Request(
            f"{OPENAI_FILES_URL}/{file_id}",
            method="DELETE",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        logger.warning(f"Nie udało się usunąć osieroconego pliku {file_id}")


def submit_batch(items, config: dict) -> tuple:
    """Upload JSONL and create a batch; return (backend metadata, error)."""
    api_key = _key(config)
    if api_key is None:
        return None, "Brak klucza API OpenAI — uzupełnij w Ustawieniach."
    o_cfg = config.get("providers", {}).get("openai", {}) or {}
    default_temp = o_cfg.get("temperature", 0.7)
    reasoning = o_cfg.get("reasoning_effort")
    reasoning = reasoning.strip().lower() if isinstance(reasoning, str) else None

    lines = []
    for item in items:
        body = {
            "model": item["model"],
            "messages": [{"role": "user", "content": item["prompt"]}],
        }
        temperature = (
            item["temperature"]
            if item["temperature"] is not None
            else default_temp
        )
        add_temperature_if_supported(body, item["model"], temperature)
        add_reasoning_effort_if_supported(body, item["model"], reasoning)
        lines.append(json.dumps({
            "custom_id": item["custom_id"],
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }, ensure_ascii=False))
    jsonl = ("\n".join(lines) + "\n").encode("utf-8")

    file_bytes, boundary = _multipart(
        {"purpose": "batch"}, "file", "batchinput.jsonl", jsonl
    )
    raw, err = post_json(
        OPENAI_FILES_URL,
        file_bytes,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        max_retries=_retries(config),
        timeout=_timeout(config),
        log=logger,
    )
    if raw is None:
        return None, f"upload pliku: {err}"
    try:
        file_id = json.loads(raw.decode("utf-8")).get("id")
    except ValueError as e:
        return None, f"upload pliku — nieczytelna odpowiedź: {e}"
    if not file_id:
        return None, "upload pliku — brak id pliku w odpowiedzi."

    body = json.dumps({
        "input_file_id": file_id,
        "endpoint": "/v1/chat/completions",
        "completion_window": "24h",
    }).encode("utf-8")
    raw, err = post_json(
        OPENAI_BATCHES_URL,
        body,
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        max_retries=_retries(config),
        timeout=_timeout(config),
        log=logger,
    )
    if raw is None:
        _delete_file(file_id, api_key, _timeout(config))
        return None, err
    try:
        batch_id = json.loads(raw.decode("utf-8")).get("id")
    except ValueError as e:
        return None, f"Nieczytelna odpowiedź API: {e}"
    if not batch_id:
        return None, "Nieoczekiwana odpowiedź API (brak id batcha)."
    logger.info(
        f"Batch OpenAI wysłany: {batch_id} "
        f"({len(items)} zapytań, model {items[0]['model']})"
    )
    return {"id": batch_id, "input_file_id": file_id}, None


def poll_batch(record: dict, config: dict) -> tuple:
    """Return (status, normalized results) for one OpenAI batch."""
    api_key = _key(config)
    if api_key is None:
        return "error", None
    headers = {"Authorization": f"Bearer {api_key}"}
    raw = fetch_url(
        f"{OPENAI_BATCHES_URL}/{record['id']}",
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
    output_file_id = info.get("output_file_id")
    record["output_file_id"] = output_file_id
    results = []
    if output_file_id:
        raw_res = fetch_url(
            f"{OPENAI_FILES_URL}/{output_file_id}/content",
            headers=headers,
            timeout=_timeout(config),
        )
        if raw_res is None:
            return "error", None
        for line in raw_res.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            response = entry.get("response") or {}
            body = response.get("body") or {}
            usage = body.get("usage") or {}
            text = None
            if response.get("status_code") == 200:
                choices = body.get("choices") or []
                if choices:
                    text = ((choices[0].get("message") or {}).get("content")) or None
            results.append({
                "custom_id": entry.get("custom_id"),
                "ok": bool(text),
                "text": text,
                "in_tok": int(usage.get("prompt_tokens") or 0),
                "out_tok": int(usage.get("completion_tokens") or 0),
            })
    return "ended", results


def cleanup_files(records, config: dict) -> None:
    api_key = _key(config)
    if api_key is None:
        return
    for record in records:
        if record.get("provider") != "openai":
            continue
        for file_id in (record.get("input_file_id"), record.get("output_file_id")):
            if file_id:
                _delete_file(file_id, api_key, _timeout(config))
