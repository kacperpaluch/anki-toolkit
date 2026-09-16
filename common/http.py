import http.client
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
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


# Headers that may follow a redirect to another origin. Everything else
# (API keys, Cloudflare Access secrets, Authorization) stays with the origin
# the user configured — urllib would otherwise forward it anywhere.
_CROSS_ORIGIN_HEADERS = {"user-agent", "accept", "accept-language"}
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(parts.scheme)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old, target = _origin(req.full_url), _origin(new.full_url)
        if old[0] == "https" and target[0] != "https":
            raise urllib.error.HTTPError(
                req.full_url, code, f"odrzucono przekierowanie z HTTPS na {target[0]}", headers, fp)
        if old != target:
            new.headers = {k: v for k, v in new.headers.items()
                           if k.lower() in _CROSS_ORIGIN_HEADERS}
        return new


_OPENER = urllib.request.build_opener(_SafeRedirectHandler)


def urlopen(request, timeout):
    """urllib.request.urlopen that never carries credentials to another origin
    and never follows a redirect from HTTPS down to plain HTTP."""
    return _OPENER.open(request, timeout=timeout)


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
            with urlopen(req, timeout=timeout) as response:
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
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    f"Connection error fetching {url}: {e}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
                continue
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


def post_create(
    url: str,
    payload: bytes,
    headers: dict,
    *,
    max_retries: int = 3,
    timeout: int = 30,
    log: Optional[logging.Logger] = None,
) -> tuple[Optional[bytes], Optional[str], bool]:
    """POST that creates a paid resource. Returns (body, error, uncertain).

    Repeats only when the server certainly did nothing (429, refused
    connection, unknown host). A timeout, reset or 5xx may hide a request the
    server already accepted: it is reported as `uncertain` and never repeated.
    """
    log = log or logger
    for attempt in range(max_retries):
        last = attempt == max_retries - 1
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urlopen(req, timeout=timeout) as response:
                return response.read(), None, False
        except urllib.error.HTTPError as e:
            if e.code == 429 and not last:
                time.sleep(2 ** (attempt + 1))
                continue
            err = extract_http_error(e)
            log.error(f"POST {url} failed: {err}")
            return None, err, e.code >= 500
        except urllib.error.URLError as e:
            unsent = isinstance(e.reason, (ConnectionRefusedError, socket.gaierror))
            if unsent and not last:
                time.sleep(2 ** (attempt + 1))
                continue
            log.error(f"Connection error POST {url}: {e}")
            return None, f"Connection error: {e}", not unsent
        except (TimeoutError, ConnectionError, http.client.HTTPException) as e:
            log.error(f"Connection error POST {url}: {e}")
            return None, f"Connection error: {e}", True
    return None, "request failed after retries", False


def post_json(
    url: str,
    payload: bytes,
    headers: dict,
    *,
    max_retries: int = 3,
    timeout: int = 30,
    method: str = "POST",
    log: Optional[logging.Logger] = None,
) -> tuple[Optional[bytes], Optional[str]]:
    """POST raw bytes with retry on 429/5xx and connection errors.

    `method` overrides the verb (e.g. "PATCH") — body, headers and retry
    behaviour are identical.

    Returns (response_bytes, None) on success, (None, error_message) on failure.
    HTTP error messages come from extract_http_error() (parses JSON body for
    error.message when available); connection errors get a plain string.
    """
    if log is None:
        log = logger
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method=method)
            with urlopen(req, timeout=timeout) as response:
                return response.read(), None
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                log.warning(
                    f"HTTP {e.code} {method} {url}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
                continue
            err = extract_http_error(e)
            log.error(f"{method} {url} failed: {err}")
            return None, err
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries - 1:
                delay = 2 ** (attempt + 1)
                log.warning(
                    f"Connection error {method} {url}: {e}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
                continue
            err = f"Connection error: {e}"
            log.error(err)
            return None, err
    return None, "request failed after retries"
