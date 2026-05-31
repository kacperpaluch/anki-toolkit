import random
import string
from typing import Optional


def unique(values: list) -> list:
    seen = set()
    result = []
    for v in values or []:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def safe_float(value, default: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    try:
        v = float(value)
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return default


def safe_str(value, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def unique_filename() -> str:
    chars = string.ascii_lowercase + string.digits
    return "tts_" + "".join(random.choice(chars) for _ in range(12)) + ".mp3"


def normalize_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
