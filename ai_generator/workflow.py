"""Workflow — run AI → Dictionary → TTS in sequence for one note (editor).

execute_step() is the shared single-step executor — also used by the
browser batch (browser_ui). It runs on a background thread, mutates the
note in memory and never writes to the collection; persisting is the
caller's job (on the main thread).
"""

import logging
from typing import Optional

from aqt import mw
from aqt.utils import tooltip
from aqt.editor import Editor

from ..common import ADDON_NAME, plural_pl

logger = logging.getLogger(__name__)

_RUNNING: set[int] = set()


def get_workflow_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("workflow", {})


def execute_step(note, step: dict) -> tuple[bool, Optional[str]]:
    """Execute a single workflow step on a note (background thread).

    Returns (modified, error_message). The note is mutated in memory only.
    """
    module = step.get("module", "")
    action = step.get("action", "")

    if module == "ai" and action == "generate":
        from ._generator import get_generator
        gen = get_generator()
        changed = gen.process_note(note)
        return bool(changed), gen.last_error

    if module == "dictionary" and action == "fetch":
        dicts = step.get("dicts", [])
        if not dicts:
            return False, None
        from ..dictionary.service import process_note_group
        config_full = mw.addonManager.getConfig(ADDON_NAME) or {}
        result = process_note_group(note, config_full.get("dictionary", {}), dicts)
        return result.note_modified, None

    if module == "tts" and action == "generate":
        from ..tts.processor import process_single_note
        return process_single_note(note)

    return False, None


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

    def start():
        note = editor.note
        if note is None:
            _RUNNING.discard(editor_id)
            return
        _execute_steps(editor, note, steps, editor_id)

    editor.saveNow(start)


def _execute_steps(editor: Editor, note, steps: list, editor_id: int):
    """Run workflow steps one by one in background. Each step waits for previous.

    All steps operate on the note captured when the workflow started, so
    switching notes in the editor mid-run cannot corrupt another note.
    Collection writes happen on the main thread, after each step.
    """
    total = len(steps)

    def run_step(i: int):
        if i >= total:
            _RUNNING.discard(editor_id)
            try:
                if editor.note is note:
                    editor.loadNote()
            except Exception:
                pass  # editor may have been closed mid-run
            tooltip(
                f"Workflow zakończony. Wykonano {total} "
                f"{plural_pl(total, 'krok', 'kroki', 'kroków')}.",
                period=5000,
            )
            return

        step = steps[i]
        module = step.get("module", "")
        action = step.get("action", "")
        logger.info(f"Workflow: krok {i + 1}/{total} ({module}/{action}), nid={note.id}")

        def bg_task():
            return execute_step(note, step)

        def on_done(future):
            try:
                modified, err = future.result()
            except Exception as e:
                modified, err = False, str(e)
            if modified and note.id:
                try:
                    mw.col.update_note(note)
                except Exception as e:
                    err = err or str(e)
            if err:
                logger.error(f"Workflow: krok {i + 1}/{total} ({module}/{action}): {err}")
                tooltip(f"Workflow krok {i+1}/{total} ({module}/{action}): {err}", period=5000)
            run_step(i + 1)

        mw.taskman.run_in_background(bg_task, on_done)

    run_step(0)
