"""Field Hider — hides configured fields only in Anki's Add Cards window.

Existing notes and the Browser editor remain unaffected.
"""

import json

from aqt import gui_hooks

from ..common import get_module_config


_DEFAULTS = {"hidden_fields": {}}


def get_config() -> dict:
    return get_module_config("field_hider", _DEFAULTS)


def indices_to_hide(field_names, targets):
    """Pure core: 0-based indexes of configured fields, in note-type order."""
    targets = set(targets or [])
    return [index for index, name in enumerate(field_names) if name in targets]


def on_editor_load_note(editor) -> None:
    """Inject hiding CSS only for the Add Cards editor."""
    if not getattr(editor, "addMode", False):
        return

    note = editor.note
    note_type = note.note_type() if note else None
    if not note_type:
        return

    hidden = get_config().get("hidden_fields") or {}
    targets = hidden.get(note_type["name"], [])
    indexes = indices_to_hide([field["name"] for field in note_type["flds"]], targets)
    if indexes:
        selector = ", ".join(
            f'body:not(.atk-fh-reveal) .field-container[data-index="{index}"]'
            for index in indexes
        )
        css = f"{selector} {{ display: none !important; }}"
    else:
        css = ""

    editor.web.eval(
        "(function(){"
        "let style=document.getElementById('atk-fh-style');"
        "if(!style){style=document.createElement('style');style.id='atk-fh-style';"
        "document.head.appendChild(style);}"
        f"style.textContent={json.dumps(css)};"
        "})();"
    )


def _toggle_hidden_fields(editor) -> None:
    editor.web.eval("document.body.classList.toggle('atk-fh-reveal');")


def on_editor_buttons_init(buttons, editor):
    """Add a temporary reveal button only in Add Cards."""
    if not getattr(editor, "addMode", False):
        return buttons
    buttons.append(
        editor.addButton(
            icon=None,
            cmd="anki_toolkit_field_hider_toggle",
            func=_toggle_hidden_fields,
            tip="Pokaż/ukryj schowane pola",
            label="👁",
            disables=False,  # usable before any field has focus
        )
    )
    return buttons


gui_hooks.editor_did_load_note.append(on_editor_load_note)
gui_hooks.editor_did_init_buttons.append(on_editor_buttons_init)
