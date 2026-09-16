"""Pure logic for splitting a field value into multiple target fields."""

import re


def split_field_value(value: str, separator: str, target_fields: list) -> dict:
    """Split *value* by *separator* and map parts to *target_fields*.

    Returns ``{target_field: part}`` for non-empty parts that fit within
    the target list. The source value is not modified — caller copies
    at its own discretion.

    Whitespace in the separator matches any run of whitespace, so
    ``"<br> <br>"`` and ``"<br><br>"`` in the content are treated alike.
    """
    if not value or not value.strip():
        return {}
    if not separator or not target_fields:
        return {}

    # ponytail: inline split_separator_regex from common/text.py — keeps
    # this module testable without Anki package imports
    pattern = r"\s*".join(
        re.escape(part) for part in re.split(r"\s+", separator) if part
    ) or re.escape(separator)
    regex = re.compile(f"(?:{pattern}){{1,}}")

    parts = [p.strip() for p in regex.split(value) if p.strip()]

    result = {}
    for i, part in enumerate(parts):
        if i >= len(target_fields):
            break
        tf = (target_fields[i] or "").strip()
        if tf:
            result[tf] = part
    return result


def parse_target_fields(raw: str) -> list:
    """Parse comma-separated field names into a clean list."""
    return [f.strip() for f in (raw or "").split(",") if f.strip()]


if __name__ == "__main__":
    # ponytail: self-check — one runnable assertion that fails if the split breaks
    sample = (
        "Many people were murdered in the Nazi death camp during World War II.[sound:tts_oe93owgdrkgo.mp3]<br><br>"
        "The museum tells the story of prisoners who were sent to a death camp.[sound:tts_9gfu5ninen4f.mp3]<br><br>"
        "Auschwitz was a death camp where the Nazis killed large numbers of civilians and prisoners.[sound:tts_kwzj4ughyfk9.mp3]"
    )
    result = split_field_value(sample, "<br><br>", ["p1", "p2", "p3"])
    assert len(result) == 3, f"expected 3 parts, got {len(result)}"
    assert result["p1"].startswith("Many people"), f"p1 wrong: {result['p1'][:30]}"
    assert result["p2"].startswith("The museum"), f"p2 wrong: {result['p2'][:30]}"
    assert result["p3"].startswith("Auschwitz"), f"p3 wrong: {result['p3'][:30]}"
    assert "<br>" not in result["p1"], "separator leaked into p1"
    assert "[sound:" in result["p1"], "audio tag missing from p1"
    print("OK — 3 examples split correctly with audio tags intact")
