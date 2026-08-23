"""Helpers for OpenAI-compatible chat-completions providers."""

import re
from typing import Optional


REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def _canonical_model_name(model: str) -> str:
    value = model.strip().lower()
    if "/" in value:
        value = value.rsplit("/", 1)[1]
    if ":" in value:
        value = value.split(":", 1)[0]
    return value


def _gpt_version(model: str) -> Optional[tuple[int, int]]:
    model = _canonical_model_name(model)
    match = re.match(r"gpt-(\d+)(?:\.(\d+))?", model)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def _gpt_version_at_least(model: str, major: int, minor: int = 0) -> bool:
    version = _gpt_version(model)
    return version is not None and version >= (major, minor)


def is_openai_reasoning_model(model: str) -> bool:
    model = _canonical_model_name(model)
    return bool(re.match(r"o[134](?:-|$)", model)) or _gpt_version_at_least(model, 5)


def supports_openai_reasoning_effort(model: str, effort: str) -> bool:
    model = _canonical_model_name(model)
    if effort not in REASONING_EFFORTS or not is_openai_reasoning_model(model):
        return False

    if model.startswith("gpt-5-pro"):
        return effort == "high"

    if effort == "none":
        return _gpt_version_at_least(model, 5, 1)

    if effort == "xhigh":
        if "codex" in model and _gpt_version_at_least(model, 5, 1):
            return True
        version = _gpt_version(model)
        return version is not None and version > (5, 1)

    return True


def add_temperature_if_supported(data: dict, model: str, temperature: float) -> None:
    if not is_openai_reasoning_model(model):
        data["temperature"] = temperature


def add_reasoning_effort_if_supported(data: dict, model: str, effort: Optional[str]) -> None:
    if effort and supports_openai_reasoning_effort(model, effort):
        data["reasoning_effort"] = effort


def is_reasoning_effort_unsupported_error(error: str) -> bool:
    return "reasoning_effort" in error.lower()


def extract_message_content(content) -> Optional[str]:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts).strip()
    return None
