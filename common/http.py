import json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
}


def fetch_url(
    url: str,
    data: Optional[bytes] = None,
    headers: Optional[dict] = None,
    max_retries: int = 3,
    timeout: int = 10,
) -> Optional[bytes]:
    effective_headers = dict(_DEFAULT_HEADERS, **(headers or {}))
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data, headers=effective_headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    f"HTTP {e.code} fetching {url}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
                continue
            logger.error(f"HTTP {e.code} fetching {url}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            logger.error(f"Connection error fetching {url}: {e}")
            return None
    return None


def fetch_text(
    url: str,
    data: Optional[bytes] = None,
    headers: Optional[dict] = None,
    max_retries: int = 3,
    timeout: int = 10,
) -> Optional[str]:
    raw = fetch_url(url, data=data, headers=headers, max_retries=max_retries, timeout=timeout)
    if raw is None:
        return None
    return raw.decode("utf-8", errors="replace")


def extract_http_error(error: urllib.error.HTTPError) -> str:
    msg = error.reason
    try:
        body = error.read()
        if body:
            try:
                parsed = json.loads(body.decode("utf-8"))
                err = parsed.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("detail") or msg
                elif isinstance(err, str):
                    msg = err
                else:
                    msg = parsed.get("message") or parsed.get("detail") or msg
            except Exception:
                decoded = body.decode("utf-8", errors="ignore").strip()
                if decoded:
                    msg = decoded
    except Exception:
        pass
    return f"{error.code} - {msg}"
