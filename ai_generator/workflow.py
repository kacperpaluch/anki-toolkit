"""Workflow — run AI → Dictionary → TTS in sequence for one note (editor)."""

from aqt import mw
from aqt.utils import tooltip
from aqt.editor import Editor

from ..common import ADDON_NAME

_RUNNING: set[int] = set()


def get_workflow_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("workflow", {})


def run_workflow_editor(editor: Editor):
    """Run workflow steps sequentially on the current editor note."""
    editor_id = id(editor)
    if editor_id in _RUNNING:
        tooltip("Workflow już trwa...", period=2000)
        return

    wf = get_workflow_config()
    steps = wf.get("steps", [])
    if not steps:
        tooltip("Brak skonfigurowanego workflow. Sprawdź ustawienia.")
        return

    _RUNNING.add(editor_id)
    editor.saveNow(lambda: _execute_steps(editor, steps, editor_id))


def _execute_steps(editor: Editor, steps: list, editor_id: int):
    """Run workflow steps one by one in background. Each step waits for previous."""
    total = len(steps)

    def run_step(i: int):
        if i >= total:
            _RUNNING.discard(editor_id)
            editor.loadNote()
            tooltip(f"Workflow zakończony. Wykonano {total} kroków.", period=5000)
            return

        step = steps[i]
        module = step.get("module", "")
        action = step.get("action", "")

        def bg_task():
            try:
                _execute_step(editor.note, step)
                return None
            except Exception as e:
                return str(e)

        def on_done(future):
            try:
                err = future.result()
            except Exception as e:
                err = str(e)
            if err:
                tooltip(f"Workflow krok {i+1}/{total} ({module}/{action}): {err}", period=5000)
            run_step(i + 1)

        mw.taskman.run_in_background(bg_task, on_done)

    run_step(0)


def _execute_step(note, step: dict):
    """Execute a single workflow step on a note (called from bg thread, modifies note in place)."""
    module = step.get("module", "")
    action = step.get("action", "")

    if module == "ai" and action == "generate":
        from ._generator import get_generator
        gen = get_generator()
        gen.process_note(note)
        mw.col.update_note(note)

    elif module == "dictionary" and action == "fetch":
        dicts = step.get("dicts", [])
        if not dicts:
            return
        from ..dictionary.service import process_note_group
        config_full = mw.addonManager.getConfig(ADDON_NAME) or {}
        dict_config = config_full.get("dictionary", {})
        result = process_note_group(note, dict_config, dicts)
        if result.note_modified:
            mw.col.update_note(note)

    elif module == "tts" and action == "generate":
        from ..tts.processor import process_single_note
        process_single_note(note)
