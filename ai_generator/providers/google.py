"""Google Gemini API provider (generateContent)."""

import json
import urllib.request
import urllib.parse
from typing import Optional

from .base import BaseProvider

API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GoogleProvider(BaseProvider):
    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None
        # Key goes in a header, not the URL — URLs end up in logs and tracebacks.
        url = f"{API_BASE_URL}/{self.model}:generateContent"
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature},
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
            )
            raw = self._request_with_retry(req)
            if raw is None:
                return None
            res_data = json.loads(raw.decode("utf-8"))
            self._capture_usage(res_data)
            candidates = res_data.get("candidates")
            if not candidates or not isinstance(candidates, list):
                self.last_error = f"Google Gemini: unexpected response structure: {list(res_data.keys())}"
                self.logger.error(self.last_error)
                return None
            parts = candidates[0].get("content", {}).get("parts")
            if not parts or not isinstance(parts, list):
                self.last_error = f"Google Gemini: missing 'parts' in first candidate"
                self.logger.error(self.last_error)
                return None
            text = parts[0].get("text")
            if text is None:
                self.last_error = f"Google Gemini: missing 'text' in first part (finish_reason={candidates[0].get('finishReason')})"
                self.logger.error(self.last_error)
                return None
            return text.strip()
        except (KeyError, IndexError, TypeError) as e:
            self.last_error = f"Google Gemini response parse error: {e}"
            self.logger.error(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"Google Gemini Error: {e}"
            self.logger.error(self.last_error)
            return None
