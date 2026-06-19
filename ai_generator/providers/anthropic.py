"""Anthropic API provider (Messages API)."""

import json
import urllib.request
from typing import Optional

from .base import BaseProvider

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(BaseProvider):
    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }
        data = {
            "model": self.model,
            "max_tokens": self.max_tokens if self.max_tokens is not None else 2048,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            req = urllib.request.Request(
                API_URL,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
            )
            raw = self._request_with_retry(req)
            if raw is None:
                return None
            return self._parse_messages(raw, "Anthropic")
        except Exception as e:
            self.last_error = f"Anthropic Error: {e}"
            self.logger.error(self.last_error)
            return None
