"""OpenCode Go provider — https://opencode.ai/zen/go/v1/

Most models use Chat Completions (OpenAI-compatible).
MiniMax and Qwen3.x models use the Anthropic Messages format.
Auth is always Bearer token regardless of endpoint.
"""

import json
import urllib.request
from typing import Optional

from .base import BaseProvider
from .openai_compat import extract_message_content

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
            req = urllib.request.Request(
                CHAT_URL,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
            )
            raw = self._request_with_reasoning_fallback(req, data, headers, CHAT_URL)
            if raw is None:
                return None
            res_data = json.loads(raw.decode("utf-8"))
            self._capture_usage(res_data)
            choices = res_data.get("choices")
            if not choices or not isinstance(choices, list):
                self.last_error = f"OpenCode Go: unexpected response: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            message = choices[0].get("message")
            if not message:
                self.last_error = "OpenCode Go: missing 'message' in first choice"
                self.logger.error(self.last_error)
                return None
            content = message.get("content")
            if content is None:
                self.last_error = (
                    "OpenCode Go: missing 'content' in message "
                    f"(finish_reason={choices[0].get('finish_reason')})"
                )
                self.logger.error(self.last_error)
                return None
            text = extract_message_content(content)
            if text is None:
                self.last_error = f"OpenCode Go: unsupported content type: {type(content).__name__}"
                self.logger.error(self.last_error)
                return None
            return text
        except (KeyError, IndexError, TypeError) as e:
            self.last_error = f"OpenCode Go parse error: {e}"
            self.logger.error(self.last_error)
            return None
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
            req = urllib.request.Request(
                MESSAGES_URL,
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
                self.last_error = f"OpenCode Go messages: unexpected response: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            text = content[0].get("text", "").strip()
            if not text:
                self.last_error = "OpenCode Go messages: empty text in response"
                self.logger.error(self.last_error)
                return None
            return text
        except (KeyError, IndexError, TypeError) as e:
            self.last_error = f"OpenCode Go messages parse error: {e}"
            self.logger.error(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"OpenCode Go messages error: {e}"
            self.logger.error(self.last_error)
            return None
