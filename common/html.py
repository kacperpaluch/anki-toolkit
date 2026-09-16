import html
import re

# Line and block boundaries separate words; inline tags (<b>c</b>at) do not.
_BREAKS = re.compile(
    r"<\s*(?:br|/?(?:div|p|li|ul|ol|tr|td|th|table|blockquote|h[1-6]))\b[^>]*>", re.IGNORECASE)
_SOUND = re.compile(r"\[sound:[^\]]*\]")


def clean_html(text: str) -> str:
    raw = _BREAKS.sub(" ", text or "")
    raw = re.sub(r"<[^<]+?>", "", raw)
    return html.unescape(raw).strip()


def clean_html_normalized(text: str) -> str:
    return re.sub(r"\s+", " ", clean_html(text)).strip()


def strip_sound_tags(text: str) -> str:
    """Anki audio references are not words to look up or read aloud."""
    return _SOUND.sub("", text or "")
