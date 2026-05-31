"""OpenRouter API provider (OpenAI-compatible endpoint)."""

import json
import urllib.request
from typing import Optional

from .base import BaseProvider
from .openai_compat import add_reasoning_effort_if_supported, add_temperature_if_supported, extract_message_content

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseProvider):
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
        add_reasoning_effort_if_supported(data, self.model, self.reasoning_effort)
        try:
            req = urllib.request.Request(
                API_URL,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
            )
            raw = self._request_with_reasoning_fallback(req, data, headers, API_URL)
            if raw is None:
                return None
            res_data = json.loads(raw.decode("utf-8"))
            choices = res_data.get("choices")
            if not choices or not isinstance(choices, list):
                self.last_error = f"OpenRouter: unexpected response structure: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            message = choices[0].get("message")
            if not message:
                self.last_error = "OpenRouter: missing 'message' in first choice"
                self.logger.error(self.last_error)
                return None
            content = message.get("content")
            if content is None:
                self.last_error = (
                    "OpenRouter: missing 'content' in message "
                    f"(finish_reason={choices[0].get('finish_reason')})"
                )
                self.logger.error(self.last_error)
                return None
            text = extract_message_content(content)
            if text is None:
                self.last_error = f"OpenRouter: unsupported message content type: {type(content).__name__}"
                self.logger.error(self.last_error)
                return None
            return text
        except (KeyError, IndexError, TypeError) as e:
            self.last_error = f"OpenRouter response parse error: {e}"
            self.logger.error(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"OpenRouter Error: {e}"
            self.logger.error(self.last_error)
            return None
