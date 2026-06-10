"""Abstract base class for AI providers."""

import json
import logging
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from .openai_compat import is_reasoning_effort_unsupported_error
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
        self.logger = logging.getLogger(self.__class__.__module__)

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

    @abstractmethod
    def call_api(self, prompt: str) -> Optional[str]:
        """Send prompt to the API and return the response text, or None on error."""
        ...

    def _request_with_retry(self, req: urllib.request.Request) -> Optional[bytes]:
        """Execute an HTTP request with exponential backoff on transient errors."""
        self.last_error = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return response.read()
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
