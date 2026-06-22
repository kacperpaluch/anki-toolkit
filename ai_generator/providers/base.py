"""Abstract base class for AI providers."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

from .openai_compat import (
    add_reasoning_effort_if_supported,
    add_temperature_if_supported,
    extract_message_content,
    is_reasoning_effort_unsupported_error,
)
from ...common.http import post_json


class BaseProvider(ABC):
    def __init__(self, api_key: str, model: str, temperature: float,
                 max_retries: int = 3, timeout: int = 30,
                 max_tokens: Optional[int] = None,
                 reasoning_effort: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.last_error: Optional[str] = None
        self.last_usage: tuple[int, int] = (0, 0)  # (input_tokens, output_tokens)
        self.logger = logging.getLogger(self.__class__.__module__)

    def _capture_usage(self, res_data: dict) -> None:
        """Best-effort token usage extraction from a parsed API response.

        Handles OpenAI-compatible ("usage.prompt/completion_tokens"),
        Anthropic ("usage.input/output_tokens") and Gemini ("usageMetadata").
        """
        try:
            usage = res_data.get("usage") or {}
            inp = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            out = usage.get("completion_tokens") or usage.get("output_tokens") or 0
            if not inp and not out:
                meta = res_data.get("usageMetadata") or {}
                inp = meta.get("promptTokenCount") or 0
                out = meta.get("candidatesTokenCount") or 0
            self.last_usage = (int(inp), int(out))
        except Exception:
            self.last_usage = (0, 0)

    def _post(self, url: str, data: dict, headers: dict) -> Optional[bytes]:
        """POST data dict as JSON with retry. Sets self.last_error on failure."""
        raw, err = post_json(
            url,
            json.dumps(data).encode("utf-8"),
            headers,
            max_retries=self.max_retries,
            timeout=self.timeout,
            log=self.logger,
        )
        self.last_error = err
        return raw

    def _post_with_reasoning_fallback(
        self, url: str, data: dict, headers: dict
    ) -> Optional[bytes]:
        """POST data; if reasoning_effort is unsupported, retry without it."""
        raw = self._post(url, data, headers)
        if raw is None and "reasoning_effort" in data and self.last_error:
            if is_reasoning_effort_unsupported_error(self.last_error):
                self.logger.warning(
                    f"Model '{self.model}' nie obsługuje reasoning_effort — ponawiam bez tego parametru."
                )
                del data["reasoning_effort"]
                raw = self._post(url, data, headers)
        return raw

    def _parse_chat_completion(self, raw: bytes, label: str) -> Optional[str]:
        """Parse an OpenAI-compatible chat-completions response into text."""
        try:
            res_data = json.loads(raw.decode("utf-8"))
            self._capture_usage(res_data)
            choices = res_data.get("choices")
            if not choices or not isinstance(choices, list):
                self.last_error = f"{label}: unexpected response structure: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            message = choices[0].get("message")
            if not message:
                self.last_error = f"{label}: missing 'message' in first choice"
                self.logger.error(self.last_error)
                return None
            content = message.get("content")
            if content is None:
                self.last_error = (
                    f"{label}: missing 'content' in message "
                    f"(finish_reason={choices[0].get('finish_reason')})"
                )
                self.logger.error(self.last_error)
                return None
            text = extract_message_content(content)
            if text is None:
                self.last_error = f"{label}: unsupported message content type: {type(content).__name__}"
                self.logger.error(self.last_error)
                return None
            return text
        except (KeyError, IndexError, TypeError, ValueError) as e:
            self.last_error = f"{label} response parse error: {e}"
            self.logger.error(self.last_error)
            return None

    def _parse_messages(self, raw: bytes, label: str) -> Optional[str]:
        """Parse an Anthropic Messages-format response into text.

        With extended thinking the first block is "thinking" — find the first
        block of type "text" instead of assuming content[0].
        """
        try:
            res_data = json.loads(raw.decode("utf-8"))
            self._capture_usage(res_data)
            content = res_data.get("content")
            if not content or not isinstance(content, list):
                self.last_error = f"{label}: unexpected response structure: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            text = next(
                (block.get("text") for block in content
                 if isinstance(block, dict) and block.get("type") == "text"
                 and block.get("text")),
                None,
            )
            if text is None:
                self.last_error = f"{label}: no text block in response (stop_reason={res_data.get('stop_reason')})"
                self.logger.error(self.last_error)
                return None
            return text.strip()
        except (KeyError, IndexError, TypeError, ValueError) as e:
            self.last_error = f"{label} response parse error: {e}"
            self.logger.error(self.last_error)
            return None

    @abstractmethod
    def call_api(self, prompt: str) -> Optional[str]:
        """Send prompt to the API and return the response text, or None on error."""
        ...


class OpenAICompatProvider(BaseProvider):
    """Bearer-auth chat-completions provider. Subclasses set API_URL and LABEL."""

    API_URL: str = ""
    LABEL: str = ""
    # Mistral rejects reasoning_effort outright — opt out per subclass.
    SUPPORTS_REASONING_EFFORT: bool = True
    # Extra static headers (e.g. OpenRouter app attribution). Subclass overrides.
    EXTRA_HEADERS: dict = {}

    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            **self.EXTRA_HEADERS,
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        add_temperature_if_supported(data, self.model, self.temperature)
        if self.SUPPORTS_REASONING_EFFORT:
            add_reasoning_effort_if_supported(data, self.model, self.reasoning_effort)
        try:
            raw = self._post_with_reasoning_fallback(self.API_URL, data, headers)
            if raw is None:
                return None
            return self._parse_chat_completion(raw, self.LABEL)
        except Exception as e:
            self.last_error = f"{self.LABEL} Error: {e}"
            self.logger.error(self.last_error)
            return None
