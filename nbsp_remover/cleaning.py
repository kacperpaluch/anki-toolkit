"""Pure HTML cleanup helpers for nbsp_remover."""

import re

NBSP = "&nbsp;"
DIV_TAG_RE = r"</?div[^>]*>"
DIV_WRAP_RE = r"<div[^>]*>(.*?)</div>"
TRAILING_BR_RE = r"<br>\s*$"


def clean_field(name: str, value: str, skip_field: str) -> tuple[str, int, int, int]:
    """Return cleaned value and counters: nbsp, removed div tags, div blocks to br."""
    nbsp_count = 0
    div_count = 0
    div_br_count = 0
    value = value or ""

    nbsp_count = value.count(NBSP)
    if nbsp_count:
        value = value.replace(NBSP, " ")

    if name == skip_field:
        div_count = len(re.findall(DIV_TAG_RE, value))
        if div_count:
            value = re.sub(DIV_TAG_RE, "", value)
    else:
        div_br_count = len(re.findall(DIV_WRAP_RE, value, re.DOTALL))
        if div_br_count:
            value = re.sub(DIV_WRAP_RE, r"\1<br>", value, flags=re.DOTALL)
            value = re.sub(TRAILING_BR_RE, "", value)

    return value, nbsp_count, div_count, div_br_count
