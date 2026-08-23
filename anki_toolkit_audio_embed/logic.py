"""Pure conversion of Anki sound tags to inline HTML5 audio elements."""

import re


_SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def convert_text(text: str, css_class: str = "ex-audio", preload: str = "none") -> str:
    def replace(match):
        source = match.group(1).strip()
        return f'<audio class="{css_class}" src="{source}" preload="{preload}"></audio>'

    return _SOUND_RE.sub(replace, text)


def convert_note(note, fields, css_class: str = "ex-audio", preload: str = "none") -> bool:
    """Convert configured note fields; return whether any field changed."""
    names = set(note.keys())
    changed = False
    for field in fields:
        if field not in names:
            continue
        converted = convert_text(note[field], css_class, preload)
        if converted != note[field]:
            note[field] = converted
            changed = True
    return changed
