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
    detach_note,
    editor_shows_note,
    finish_editor_operation,
    merge_editor_note,
)


def _run_editor_generation(editor: Editor, label: str, only_fields=None,
                           overwrite: bool = False, empty_msg: str = ""):
    """Generate AI fields for the editor's note.

    The worker runs on a detached copy of the note (process_note writes results
    straight into the note it is given), so the user can keep typing; merge_note
    then writes back only the fields they did not touch meanwhile.
    """
    token = begin_editor_operation(editor, label)
    if token is None:
        tooltip(
            f"Anki Toolkit: trwa już {active_editor_operation(editor)}.",
            period=2500,
        )
        return

    # Świeża instancja per uruchomienie (config czytany na głównym wątku) —
    # dwa równoległe generowania (np. dwa okna edytora) nie współdzielą
    # last_error providera.
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
            clone, before = detach_note(note)
        except Exception:
            finish_editor_operation(editor, token)
            raise

        def task():
            return gen.process_note(clone, only_fields=only_fields,
                                    overwrite=overwrite)

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
                    tooltip(f"Błąd generowania AI: {gen.last_error}", period=8000)
                else:
                    tooltip(empty_msg or "Brak pól do wygenerowania.", period=5000)
                return

            def apply():
                try:
                    skipped = merge_editor_note(editor, note, clone, before)
                    _report(len(ai_results), skipped, gen.last_error)
                finally:
                    finish_editor_operation(editor, token)

            try:
                if editor_shows_note(editor, note):
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


def _report(filled: int, skipped: list, error) -> None:
    """One tooltip covering partial failure — a field that errored while
    another succeeded used to be reported as a clean success."""
    if not skipped and not error:
        return
    parts = [f"AI: wygenerowano {filled}"]
    if skipped:
        parts.append("pominięto pola zmienione w trakcie: " + ", ".join(skipped))
    if error:
        parts.append(f"błąd: {error}")
    tooltip(" · ".join(parts), period=8000)


def _on_generate_editor(editor: Editor):
    _run_editor_generation(editor, "generowanie AI")


def _on_generate_field_editor(editor: Editor, field_name: str):
    """Generate a single AI field for the current editor note (overwrites)."""
    _run_editor_generation(
        editor,
        f"generowanie AI pola „{field_name}”",
        only_fields={field_name},
        overwrite=True,
        empty_msg=f'Pole „{field_name}” nie ma skonfigurowanego promptu '
                  f'dla tego typu notatki.',
    )


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
