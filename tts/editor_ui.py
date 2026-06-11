"""TTS editor button — generate audio for the current note."""

import logging

from aqt import mw
from aqt.editor import Editor
from aqt.utils import tooltip

from .config import get_tts_config, get_tasks, validate_config
from .processor import build_note_work_items, generate_for_items, apply_results_to_note
from ..common import unique

logger = logging.getLogger(__name__)

# Tracks editor instances currently generating TTS — prevents double-click races.
_GENERATING: set[int] = set()


def on_editor_buttons_init(buttons: list, editor: Editor):
    config = get_tts_config()
    tasks = get_tasks(config)
    if not tasks:
        return

    label = config.get("button_label", "TTS")

    btn = editor.addButton(
        None,
        "tts_gen",
        lambda ed=editor: _on_tts_editor(ed),
        tip="Generuj audio TTS dla tej notatki",
        label=label,
    )
    buttons.append(btn)


def _on_tts_editor(editor: Editor):
    editor_id = id(editor)
    if editor_id in _GENERATING:
        tooltip("TTS: generowanie już trwa...", period=2000)
        return
    _GENERATING.add(editor_id)

    def start():
        _start_tts_editor(editor, editor_id)

    editor.saveNow(start)


def _start_tts_editor(editor: Editor, editor_id: int):
    note = editor.note
    if not note:
        _GENERATING.discard(editor_id)
        tooltip("Brak notatki w edytorze.")
        return

    config = get_tts_config()
    if not validate_config(config):
        _GENERATING.discard(editor_id)
        return

    voices = unique(config.get("voices", []))
    if not voices:
        _GENERATING.discard(editor_id)
        tooltip("Brak skonfigurowanych głosów TTS.")
        return

    tasks = get_tasks(config)
    if not tasks:
        _GENERATING.discard(editor_id)
        return

    work_items, split_contexts = build_note_work_items(note, tasks, voices)
    if not work_items:
        _GENERATING.discard(editor_id)
        tooltip("TTS: brak pól do wygenerowania.", period=5000)
        return

    def bg_task():
        results, errors, first_error = generate_for_items(work_items, config)
        logger.info(
            f"TTS (edytor): wygenerowano {len(results)}/{len(work_items)}, błędów: {errors}"
        )
        return results, errors, first_error

    def on_done(future):
        _GENERATING.discard(editor_id)
        try:
            results, errors, first_error = future.result()
        except Exception as e:
            tooltip(f"TTS: błąd generowania — {e}", period=8000)
            return

        if not results:
            msg = f"TTS: nie udało się wygenerować audio ({errors} błędów)."
            if first_error:
                msg += f" {first_error}"
            tooltip(msg, period=8000)
            return

        def apply():
            changed = apply_results_to_note(note, work_items, split_contexts, results)

            # User may have switched notes while audio was generating — only
            # refresh the editor if it still shows the processed note,
            # otherwise persist directly so the audio isn't lost.
            if editor.note is note:
                editor.loadNote()
            elif changed and note.id:
                mw.col.update_note(note)

            msg = f"TTS: wygenerowano {len(results)} plików audio."
            if errors:
                msg += f" Błędy: {errors}."
            tooltip(msg, period=8000)

        if editor.note is note:
            editor.saveNow(apply)
        else:
            apply()

    mw.taskman.run_in_background(bg_task, on_done)
