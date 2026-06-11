"""Pure HTML cleanup helpers for nbsp_remover."""

import re

NBSP = "&nbsp;"
DIV_TAG_RE = r"</?div[^>]*>"
# Matches an innermost <div> block (no nested <div> inside) — applied in a
# loop so nested divs are unwrapped inside-out instead of producing
# unbalanced tags like a single non-greedy pass would.
DIV_INNER_RE = re.compile(r"<div[^>]*>((?:(?!</?div\b).)*?)</div>", re.DOTALL | re.IGNORECASE)
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
        while True:
            value, replaced = DIV_INNER_RE.subn(r"\1<br>", value)
            if not replaced:
                break
            div_br_count += replaced
        if div_br_count:
            value = re.sub(TRAILING_BR_RE, "", value)

    return value, nbsp_count, div_count, div_br_count
