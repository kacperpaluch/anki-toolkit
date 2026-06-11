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
            res_data = json.loads(raw.decode("utf-8"))
            self._capture_usage(res_data)
            content = res_data.get("content")
            if not content or not isinstance(content, list):
                self.last_error = f"Anthropic: unexpected response structure: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            # With extended thinking the first block is "thinking" —
            # find the first text block instead of assuming content[0].
            text = next(
                (block.get("text") for block in content
                 if isinstance(block, dict) and block.get("type") == "text"),
                None,
            )
            if text is None:
                self.last_error = f"Anthropic: no text block in response (stop_reason={res_data.get('stop_reason')})"
                self.logger.error(self.last_error)
                return None
            return text.strip()
        except (KeyError, IndexError, TypeError) as e:
            self.last_error = f"Anthropic response parse error: {e}"
            self.logger.error(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"Anthropic Error: {e}"
            self.logger.error(self.last_error)
            return None
