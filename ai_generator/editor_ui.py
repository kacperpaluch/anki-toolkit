from aqt import mw
from aqt.utils import tooltip
from aqt.editor import Editor

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


def on_editor_buttons_init(buttons: list, editor: Editor):
    config = get_config()

    # Workflow button (if enabled and configured)
    from .workflow import get_workflow_config, run_workflow_editor
    wf = get_workflow_config()
    if wf.get("enabled", True) and wf.get("steps"):
        wf_label = wf.get("editor_label", "Generuj fiszkę")
        wf_btn = editor.addButton(
            None,
            "wf_run",
            lambda ed=editor: run_workflow_editor(ed),
            tip="AI → Słownik → TTS wg skonfigurowanej kolejności",
            label=wf_label,
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
