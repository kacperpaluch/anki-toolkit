"""Pure HTML cleanup helpers."""

import re


NBSP = "&nbsp;"
DIV_TAG_RE = r"</?div[^>]*>"
DIV_INNER_RE = re.compile(r"<div[^>]*>((?:(?!</?div\b).)*?)</div>", re.DOTALL | re.IGNORECASE)
TRAILING_BR_RE = r"<br>\s*$"


def clean_field(name: str, value: str, skip_field: str) -> tuple[str, int, int, int]:
    """Return cleaned value and counts: nbsp, removed div tags, div-to-br blocks."""
    value = value or ""
    nbsp_count = value.count(NBSP)
    if nbsp_count:
        value = value.replace(NBSP, " ")

    if name == skip_field:
        div_count = len(re.findall(DIV_TAG_RE, value))
        if div_count:
            value = re.sub(DIV_TAG_RE, "", value)
        return value, nbsp_count, div_count, 0

    div_br_count = 0
    while True:
        value, replaced = DIV_INNER_RE.subn(r"\1<br>", value)
        if not replaced:
            break
        div_br_count += replaced
    if div_br_count:
        value = re.sub(TRAILING_BR_RE, "", value)
    return value, nbsp_count, 0, div_br_count
