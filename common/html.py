import html
import re


def clean_html(text: str) -> str:
    raw = re.sub(r"<[^<]+?>", "", text or "")
    return html.unescape(raw).strip()


def clean_html_normalized(text: str) -> str:
    return re.sub(r"\s+", " ", clean_html(text)).strip()
