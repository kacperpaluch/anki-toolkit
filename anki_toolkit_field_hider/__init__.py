"""Anki Toolkit: Field Hider.

Hides configured fields only in Anki's Add Cards window. Existing notes and
the Browser editor remain unaffected. This package is deliberately standalone:
it owns its configuration and registers only its own editor hooks.
"""

import json

from aqt import mw, gui_hooks
from aqt.qt import QAction, QTimer


_DEFAULTS = {"hidden_fields": {}}


def _addon_name() -> str:
    """Name used by Anki's AddonManager for this installed package."""
    return __name__.split(".")[0]


def get_config() -> dict:
    """Return the standalone config, retaining unknown keys from the profile."""
    saved = mw.addonManager.getConfig(_addon_name()) or {}
    return {**_DEFAULTS, **saved}


def save_config(changes: dict) -> None:
    """Save this add-on's changes without discarding unknown configuration keys."""
    config = mw.addonManager.getConfig(_addon_name()) or {}
    config.update(changes)
    mw.addonManager.writeConfig(_addon_name(), config)


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
        )
    )
    return buttons


gui_hooks.editor_did_load_note.append(on_editor_load_note)
gui_hooks.editor_did_init_buttons.append(on_editor_buttons_init)


def _setup_menu(*_args) -> None:
    from .settings import open_settings

    action = QAction("Anki Toolkit: Field Hider…", mw)
    action.triggered.connect(open_settings)
    mw.form.menuTools.addAction(action)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menu)
else:
    QTimer.singleShot(0, _setup_menu)
