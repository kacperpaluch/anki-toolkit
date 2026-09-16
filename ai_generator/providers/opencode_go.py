"""OpenCode Go provider — https://opencode.ai/zen/go/v1/

Most models use Chat Completions (OpenAI-compatible).
MiniMax and Qwen3.x models use the Anthropic Messages format.
Auth is always Bearer token regardless of endpoint.
"""

from typing import Optional

from .base import BaseProvider

CHAT_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MESSAGES_URL = "https://opencode.ai/zen/go/v1/messages"

# These models route through the Anthropic Messages API endpoint
_MESSAGES_FORMAT_MODELS = {
    "minimax-m2.5",
    "minimax-m2.7",
    "qwen3.5-plus",
    "qwen3.6-plus",
}


def _uses_messages_format(model: str) -> bool:
    return model.strip().lower() in _MESSAGES_FORMAT_MODELS


class OpenCodeGoProvider(BaseProvider):
    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (compatible; anki-toolkit/1.0)",
        }
        if _uses_messages_format(self.model):
            return self._call_messages(prompt, headers)
        return self._call_chat(prompt, headers)

    # ------------------------------------------------------------------
    # Chat Completions (OpenAI-compatible) — GLM, Kimi, DeepSeek, MiMo
    # ------------------------------------------------------------------

    def _call_chat(self, prompt: str, headers: dict) -> Optional[str]:
        data: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        if self.reasoning_effort:
            data["reasoning_effort"] = self.reasoning_effort
        try:
            raw = self._post_with_reasoning_fallback(CHAT_URL, data, headers)
            if raw is None:
                return None
            return self._parse_chat_completion(raw, "OpenCode Go")
        except Exception as e:
            self.last_error = f"OpenCode Go error: {e}"
            self.logger.error(self.last_error)
            return None

    # ------------------------------------------------------------------
    # Anthropic Messages format — MiniMax, Qwen3.x Plus
    # ------------------------------------------------------------------

    def _call_messages(self, prompt: str, headers: dict) -> Optional[str]:
        data: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens if self.max_tokens is not None else 2048,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            raw = self._post(MESSAGES_URL, data, headers)
            if raw is None:
                return None
            return self._parse_messages(raw, "OpenCode Go messages")
        except Exception as e:
            self.last_error = f"OpenCode Go messages error: {e}"
            self.logger.error(self.last_error)
            return None
