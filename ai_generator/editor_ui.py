from aqt import mw
from aqt.utils import tooltip
from aqt.editor import Editor
from aqt.qt import QAction, QMenu
from aqt import gui_hooks

from ._generator import get_config
from .field_generator import FieldGenerator
from ..common.editor_operation import (
    active_editor_operation,
    begin_editor_operation,
    finish_editor_operation,
)


def _on_generate_editor(editor: Editor):
    token = begin_editor_operation(editor, "generowanie AI")
    if token is None:
        tooltip(
            f"Anki Toolkit: trwa już {active_editor_operation(editor)}.",
            period=2500,
        )
        return

    # Świeża instancja per uruchomienie (config czytany na głównym wątku) —
    # dwa równoległe generowania (np. dwa okna edytora) nie współdzielą
    # last_error/last_usage providera.
    try:
        gen = FieldGenerator(get_config())
    except Exception:
        finish_editor_operation(editor, token)
        raise

    def start():
        try:
            # Note captured here — after saveNow synced webview → editor.note,
            # so field-emptiness checks in process_note see the true current state.
            note = editor.note
            if note is None:
                finish_editor_operation(editor, token)
                return
        except Exception:
            finish_editor_operation(editor, token)
            raise

        def task():
            return gen.process_note(note)

        def on_done(fut):
            try:
                ai_results = fut.result()
            except Exception as e:
                finish_editor_operation(editor, token)
                tooltip(f"Błąd generowania AI: {e}", period=5000)
                return

            if not ai_results:
                if gen.last_error:
                    finish_editor_operation(editor, token)
                    tooltip(f"Błąd generowania AI: {gen.last_error}", period=8000)
                    return
                finish_editor_operation(editor, token)
                tooltip("Brak pól do wygenerowania.", period=3000)
                return

            def apply():
                try:
                    for field, result in ai_results.items():
                        note[field] = result
                    # User may have switched to a different note while generating —
                    # only refresh the editor if it still shows the processed note,
                    # otherwise persist directly so results aren't lost.
                    if editor.note is note:
                        editor.loadNote()
                    elif note.id:
                        mw.col.update_note(note)
                finally:
                    finish_editor_operation(editor, token)

            try:
                if editor.note is note:
                    editor.saveNow(apply)
                else:
                    apply()
            except Exception:
                finish_editor_operation(editor, token)
                raise

        try:
            mw.taskman.run_in_background(task, on_done)
        except Exception:
            finish_editor_operation(editor, token)
            raise

    try:
        editor.saveNow(start)
    except Exception:
        finish_editor_operation(editor, token)
        raise


def _on_generate_field_editor(editor: Editor, field_name: str):
    """Generate a single AI field for the current editor note (overwrites)."""
    token = begin_editor_operation(editor, f"generowanie AI pola „{field_name}”")
    if token is None:
        tooltip(
            f"Anki Toolkit: trwa już {active_editor_operation(editor)}.",
            period=2500,
        )
        return

    try:
        gen = FieldGenerator(get_config())
    except Exception:
        finish_editor_operation(editor, token)
        raise

    def start():
        try:
            note = editor.note
            if note is None:
                finish_editor_operation(editor, token)
                return
        except Exception:
            finish_editor_operation(editor, token)
            raise

        def task():
            return gen.process_note(note, only_fields={field_name}, overwrite=True)

        def on_done(fut):
            try:
                ai_results = fut.result()
            except Exception as e:
                finish_editor_operation(editor, token)
                tooltip(f"Błąd generowania AI: {e}", period=5000)
                return

            if not ai_results:
                finish_editor_operation(editor, token)
                if gen.last_error:
                    tooltip(f"Błąd generowania AI ({field_name}): {gen.last_error}", period=8000)
                else:
                    tooltip(
                        f'Pole „{field_name}” nie ma skonfigurowanego promptu '
                        f'dla tego typu notatki.',
                        period=5000,
                    )
                return

            def apply():
                try:
                    for field, result in ai_results.items():
                        note[field] = result
                    if editor.note is note:
                        editor.loadNote()
                    elif note.id:
                        mw.col.update_note(note)
                finally:
                    finish_editor_operation(editor, token)

            try:
                if editor.note is note:
                    editor.saveNow(apply)
                else:
                    apply()
            except Exception:
                finish_editor_operation(editor, token)
                raise

        try:
            mw.taskman.run_in_background(task, on_done)
        except Exception:
            finish_editor_operation(editor, token)
            raise

    try:
        editor.saveNow(start)
    except Exception:
        finish_editor_operation(editor, token)
        raise


def _fields_with_prompt_for_note_type(note_type_name: str) -> list[str]:
    """Target field names configured for this note type, in generation order."""
    config = get_config()
    nt_cfg = config.get("note_types", {}).get(note_type_name)
    if not isinstance(nt_cfg, dict):
        return []
    fields: list[str] = []
    for entry in nt_cfg.values():
        if not isinstance(entry, dict):
            continue
        target = (entry.get("target") or "").strip()
        if target and target not in fields:
            fields.append(target)
    return fields


def _on_editor_context_menu(editor_webview, menu: QMenu) -> None:
    """Add 'Generate field via AI' / 'Regenerate field' to the editor's right-click menu.

    Only shown when the focused field has a configured AI prompt for the current
    note type — so the option never appears on unrelated fields.
    """
    editor = getattr(editor_webview, "editor", None)
    if editor is None:
        return
    note = getattr(editor, "note", None)
    if note is None:
        return
    current_idx = getattr(editor, "currentField", None)
    if current_idx is None:
        return

    try:
        field_name = note.keys()[current_idx]
    except (IndexError, TypeError):
        return

    note_type_name = note.note_type()["name"]
    if field_name not in _fields_with_prompt_for_note_type(note_type_name):
        return

    menu.addSeparator()
    if note[field_name].strip():
        label = f'Regeneruj „{field_name}” przez AI'
    else:
        label = f'Wygeneruj „{field_name}” przez AI'
    action = QAction(label, menu)
    action.triggered.connect(
        lambda _checked=False, ed=editor, fn=field_name:
            _on_generate_field_editor(ed, fn)
    )
    menu.addAction(action)


def on_editor_buttons_init(buttons: list, editor: Editor):
    config = get_config()

    # One editor button per workflow flagged with editor_button.
    from .workflow import get_workflows, run_workflow_editor
    for i, wf in enumerate(get_workflows()):
        if not wf.get("editor_button") or not wf.get("steps"):
            continue
        wf_name = wf.get("name", "Workflow")
        wf_btn = editor.addButton(
            None,
            f"wf_run_{i}",
            lambda ed=editor, w=wf: run_workflow_editor(ed, w),
            tip=f"Uruchom workflow: {wf_name}",
            label=wf_name,
        )
        buttons.append(wf_btn)

    label = config.get("button_label", "AI")
    btn = editor.addButton(
        None,
        "ai_gen_field",
        lambda ed=editor: _on_generate_editor(ed),
        tip="Generuj tylko pola AI",
        label=label,
    )
    buttons.append(btn)


# Register the editor context-menu hook once on import.
gui_hooks.editor_will_show_context_menu.append(_on_editor_context_menu)
