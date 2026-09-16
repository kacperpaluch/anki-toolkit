"""Anthropic API provider (Messages API)."""

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
        # temperature jest deprecated w Messages API — nowe modele (>Opus 4.6)
        # przyjmują tylko 1.0 (default), inne wartości → 400. Pomijamy je całkowicie.
        data = {
            "model": self.model,
            "max_tokens": self.max_tokens if self.max_tokens is not None else 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            raw = self._post(API_URL, data, headers)
            if raw is None:
                return None
            return self._parse_messages(raw, "Anthropic")
        except Exception as e:
            self.last_error = f"Anthropic Error: {e}"
            self.logger.error(self.last_error)
            return None
