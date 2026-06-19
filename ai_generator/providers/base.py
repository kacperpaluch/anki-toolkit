"""Abstract base class for AI providers."""

import json
import logging
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from .openai_compat import (
    add_reasoning_effort_if_supported,
    add_temperature_if_supported,
    extract_message_content,
    is_reasoning_effort_unsupported_error,
)
from ...common.http import RETRYABLE_STATUS_CODES


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

    def _request_with_reasoning_fallback(
        self, req: urllib.request.Request, data: dict, headers: dict, url: str
    ) -> Optional[bytes]:
        """Run request; if it fails because reasoning_effort is unsupported, retry without it."""
        raw = self._request_with_retry(req)
        if raw is None and "reasoning_effort" in data and self.last_error:
            if is_reasoning_effort_unsupported_error(self.last_error):
                self.logger.warning(
                    f"Model '{self.model}' nie obsługuje reasoning_effort — ponawiam bez tego parametru."
                )
                del data["reasoning_effort"]
                fallback_req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode("utf-8"),
                    headers=headers,
                )
                raw = self._request_with_retry(fallback_req)
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

    def _request_with_retry(self, req: urllib.request.Request) -> Optional[bytes]:
        """Execute an HTTP request with exponential backoff on transient errors."""
        self.last_error = None
        self.logger.debug(f"{self.model}: wysyłam żądanie (timeout={self.timeout}s)")
        for attempt in range(self.max_retries):
            try:
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw = response.read()
                self.logger.debug(
                    f"{self.model}: odpowiedź {len(raw)} B w {time.time() - t0:.1f}s"
                )
                return raw
            except urllib.error.HTTPError as e:
                if e.code in RETRYABLE_STATUS_CODES and attempt < self.max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    self.logger.warning(f"HTTP {e.code}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(delay)
                    continue
                details = e.read().decode("utf-8", errors="replace").strip()
                if len(details) > 600:
                    details = details[:600] + "..."
                self.last_error = f"HTTP {e.code}: {e.reason}"
                if details:
                    self.last_error = f"{self.last_error} — {details}"
                self.logger.error(self.last_error)
                return None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.max_retries - 1:
                    delay = 2 ** (attempt + 1)
                    self.logger.warning(
                        f"Connection error: {e}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    continue
                self.last_error = f"Connection error: {e}"
                self.logger.error(self.last_error)
                return None
        return None


class OpenAICompatProvider(BaseProvider):
    """Bearer-auth chat-completions provider. Subclasses set API_URL and LABEL."""

    API_URL: str = ""
    LABEL: str = ""
    # Mistral rejects reasoning_effort outright — opt out per subclass.
    SUPPORTS_REASONING_EFFORT: bool = True

    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        add_temperature_if_supported(data, self.model, self.temperature)
        if self.SUPPORTS_REASONING_EFFORT:
            add_reasoning_effort_if_supported(data, self.model, self.reasoning_effort)
        try:
            req = urllib.request.Request(
                self.API_URL,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
            )
            raw = self._request_with_reasoning_fallback(req, data, headers, self.API_URL)
            if raw is None:
                return None
            return self._parse_chat_completion(raw, self.LABEL)
        except Exception as e:
            self.last_error = f"{self.LABEL} Error: {e}"
            self.logger.error(self.last_error)
            return None
