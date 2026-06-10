"""In-memory log buffer for the addon — viewable in Settings → Logi."""

import logging
import threading
from collections import deque

from .consts import ADDON_NAME

_MAX_LINES = 2000

_buffer: deque = deque(maxlen=_MAX_LINES)
_lock = threading.Lock()
_seq = 0
_handler = None


class _Formatter(logging.Formatter):
    def format(self, record):
        record.shortname = record.name.removeprefix(ADDON_NAME + ".")
        return super().format(record)


class _BufferHandler(logging.Handler):
    def emit(self, record):
        global _seq
        try:
            line = self.format(record)
        except Exception:
            return
        with _lock:
            _buffer.append(line)
            _seq += 1


def setup_logging() -> None:
    global _handler
    if _handler is not None:
        return
    _handler = _BufferHandler()
    _handler.setFormatter(_Formatter(
        "%(asctime)s %(levelname)-7s %(shortname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger(ADDON_NAME).addHandler(_handler)

    from .config import get_full_config
    enabled = bool(get_full_config().get("debug", {}).get("enabled", False))
    set_debug(enabled)
    logging.getLogger(ADDON_NAME).info(
        f"Anki Toolkit uruchomiony, logowanie aktywne (debug={'tak' if enabled else 'nie'})"
    )


def set_debug(enabled: bool) -> None:
    logging.getLogger(ADDON_NAME).setLevel(
        logging.DEBUG if enabled else logging.INFO
    )


def get_log_lines() -> list[str]:
    with _lock:
        return list(_buffer)


def get_log_seq() -> int:
    return _seq


def clear_log() -> None:
    global _seq
    with _lock:
        _buffer.clear()
        _seq += 1
