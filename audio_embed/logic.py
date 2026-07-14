"""Convert Anki `[sound:file.mp3]` tags into inline HTML5 `<audio>` players.

Universal, source-agnostic: audio may land in a field from the TTS module, a
dictionary lookup, or manual entry — this only rewrites the `[sound:...]` tag
into `<audio class="ex-audio" src="file.mp3" preload="none"></audio>`.

Runs per FIELD, on configured note types and fields only. The main `audio`
field is simply left off the field list, so its `[sound:...]` stays intact.

Pure logic — no Qt, no collection access. Idempotent: only `[sound:...]` is
matched, so re-running never touches already-converted `<audio>` tags.
"""

import re

# Filenames may contain spaces/dots; capture everything up to the closing ].
_SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def convert_text(text, css_class="ex-audio", preload="none"):
    """Rewrite every [sound:NAME] in *text* into an <audio> element."""
    def repl(m):
        src = m.group(1).strip()
        return (f'<audio class="{css_class}" src="{src}" '
                f'preload="{preload}"></audio>')
    return _SOUND_RE.sub(repl, text)


def convert_note(note, fields, css_class="ex-audio", preload="none"):
    """Convert [sound:...] in the given *fields* of *note*. Returns True if changed.

    Fields absent on the note are skipped; the caller decides which fields
    (never include the main audio field).
    """
    names = set(note.keys())
    changed = False
    for f in fields:
        if f not in names:
            continue
        new = convert_text(note[f], css_class, preload)
        if new != note[f]:
            note[f] = new
            changed = True
    return changed
