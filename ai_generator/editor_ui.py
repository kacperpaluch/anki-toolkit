from aqt import mw
from aqt.utils import tooltip
from aqt.editor import Editor
from aqt.qt import QAction, QMenu
from aqt import gui_hooks

from ._generator import get_generator, get_config

# Tracks editor instances currently generating — prevents double-click races.
_GENERATING: set[int] = set()


def _on_generate_editor(editor: Editor):
    editor_id = id(editor)
    if editor_id in _GENERATING:
        tooltip("Generowanie już trwa...", period=2000)
        return
    _GENERATING.add(editor_id)

    gen = get_generator()  # read config on main thread

    def start():
        # Note captured here — after saveNow synced webview → editor.note,
        # so field-emptiness checks in process_note see the true current state.
        note = editor.note
        if note is None:
            _GENERATING.discard(editor_id)
            return

        def task():
            return gen.process_note(note)

        def on_done(fut):
            _GENERATING.discard(editor_id)
            try:
                ai_results = fut.result()
            except Exception as e:
                tooltip(f"Błąd generowania AI: {e}", period=5000)
                return

            if not ai_results:
                if gen.last_error:
                    tooltip(f"Błąd generowania AI: {gen.last_error}", period=8000)
                    return
                tooltip("Brak pól do wygenerowania.", period=3000)
                return

            def apply():
                for field, result in ai_results.items():
                    note[field] = result
                # User may have switched to a different note while generating —
                # only refresh the editor if it still shows the processed note,
                # otherwise persist directly so results aren't lost.
                if editor.note is note:
                    editor.loadNote()
                elif note.id:
                    mw.col.update_note(note)

            if editor.note is note:
                editor.saveNow(apply)
            else:
                apply()

        mw.taskman.run_in_background(task, on_done)

    editor.saveNow(start)


def _on_generate_field_editor(editor: Editor, field_name: str):
    """Generate a single AI field for the current editor note (overwrites)."""
    editor_id = id(editor)
    if editor_id in _GENERATING:
        tooltip("Generowanie już trwa...", period=2000)
        return
    _GENERATING.add(editor_id)

    gen = get_generator()

    def start():
        note = editor.note
        if note is None:
            _GENERATING.discard(editor_id)
            return

        def task():
            return gen.process_note(note, only_fields={field_name}, overwrite=True)

        def on_done(fut):
            _GENERATING.discard(editor_id)
            try:
                ai_results = fut.result()
            except Exception as e:
                tooltip(f"Błąd generowania AI: {e}", period=5000)
                return

            if not ai_results:
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
                for field, result in ai_results.items():
                    note[field] = result
                if editor.note is note:
                    editor.loadNote()
                elif note.id:
                    mw.col.update_note(note)

            if editor.note is note:
                editor.saveNow(apply)
            else:
                apply()

        mw.taskman.run_in_background(task, on_done)

    editor.saveNow(start)


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
