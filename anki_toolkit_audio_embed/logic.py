"""Pure conversion of Anki sound tags to inline HTML5 audio elements."""

import re
from html import escape
from urllib.parse import quote


_SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")
_LEGACY_AUDIO_RE = re.compile(r'<audio class="([^"]*)" src="([^"]*)" preload="([^"]*)"></audio>')


def convert_text(text: str, css_class: str = "ex-audio", preload: str = "none") -> str:
    def replace(match):
        source = escape(quote(match.group(1).strip(), safe="/"), quote=True)
        return f'<audio controls class="{escape(css_class, quote=True)}" src="{source}" preload="{escape(preload, quote=True)}"></audio>'

    # Upgrade only the exact markup emitted by older versions of this add-on.
    text = _LEGACY_AUDIO_RE.sub(
        lambda match: match.group(0).replace("<audio ", "<audio controls ", 1)
        if match.group(1) == escape(css_class, quote=True) else match.group(0), text)
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
