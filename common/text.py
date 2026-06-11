import random
import re
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


def plural_pl(n: int, one: str, few: str, many: str) -> str:
    """Polish plural form: 1 krok / 2-4 kroki / 5+ kroków (with teen exception)."""
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def split_separator_regex(separator: str) -> "re.Pattern":
    """Compile a regex matching one or more occurrences of a split separator.

    Whitespace in the separator matches any run of whitespace, so
    "<br> <br>" and "<br><br>" in the field content are treated alike.
    (re.escape() stopped escaping spaces in Python 3.7, so substituting
    the escaped form "\\ " would silently do nothing.)
    """
    pattern = r"\s*".join(
        re.escape(part) for part in re.split(r"\s+", separator) if part
    ) or re.escape(separator)
    return re.compile(f"(?:{pattern}){{1,}}")
