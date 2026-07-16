"""TTS editor button — generate audio for the current note."""

import logging

from aqt import mw
from aqt.editor import Editor
from aqt.utils import tooltip
from aqt.qt import QAction, QMenu
from aqt import gui_hooks

from .config import get_tts_config, get_tasks, validate_config
from .processor import build_note_work_items, generate_for_items, apply_results_to_note, process_single_note, has_audio
from ..common import unique
from ..common.editor_operation import (
    active_editor_operation,
    begin_editor_operation,
    finish_editor_operation,
)

logger = logging.getLogger(__name__)

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
    token = begin_editor_operation(editor, "generowanie TTS")
    if token is None:
        tooltip(
            f"Anki Toolkit: trwa już {active_editor_operation(editor)}.",
            period=2500,
        )
        return

    def start():
        try:
            _start_tts_editor(editor, token)
        except Exception:
            finish_editor_operation(editor, token)
            raise

    try:
        editor.saveNow(start)
    except Exception:
        finish_editor_operation(editor, token)
        raise


def _start_tts_editor(editor: Editor, token):
    note = editor.note
    if not note:
        finish_editor_operation(editor, token)
        tooltip("Brak notatki w edytorze.")
        return

    config = get_tts_config()
    if not validate_config(config):
        finish_editor_operation(editor, token)
        return

    voices = unique(config.get("voices", []))
    if not voices:
        finish_editor_operation(editor, token)
        tooltip("Brak skonfigurowanych głosów TTS.")
        return

    tasks = get_tasks(config)
    if not tasks:
        finish_editor_operation(editor, token)
        return

    work_items, split_contexts = build_note_work_items(note, tasks, voices)
    if not work_items:
        finish_editor_operation(editor, token)
        tooltip("TTS: brak pól do wygenerowania.", period=5000)
        return

    def bg_task():
        results, errors, first_error = generate_for_items(work_items, config)
        logger.info(
            f"TTS (edytor): wygenerowano {len(results)}/{len(work_items)}, błędów: {errors}"
        )
        return results, errors, first_error

    def on_done(future):
        try:
            results, errors, first_error = future.result()
        except Exception as e:
            finish_editor_operation(editor, token)
            tooltip(f"TTS: błąd generowania — {e}", period=8000)
            return

        if not results:
            finish_editor_operation(editor, token)
            msg = f"TTS: nie udało się wygenerować audio ({errors} błędów)."
            if first_error:
                msg += f" {first_error}"
            tooltip(msg, period=8000)
            return

        def apply():
            try:
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
        mw.taskman.run_in_background(bg_task, on_done)
    except Exception:
        finish_editor_operation(editor, token)
        raise


# ---------------------------------------------------------------------------
# Per-field TTS via editor context menu (PPM on target field)
# ---------------------------------------------------------------------------

def _tasks_for_field(field_name: str, config: dict) -> list[dict]:
    """TTS tasks whose target_field matches the given field name."""
    return [
        task for task in get_tasks(config)
        if task.get("target_field", "") == field_name
    ]


def _on_tts_field_editor(editor: Editor, task: dict, overwrite: bool):
    """Generate TTS for a single task on the current editor note."""
    label = task.get("label", "TTS")
    token = begin_editor_operation(editor, f"generowanie TTS „{label}”")
    if token is None:
        tooltip(
            f"Anki Toolkit: trwa już {active_editor_operation(editor)}.",
            period=2500,
        )
        return

    def start_inner():
        note = editor.note
        if not note:
            finish_editor_operation(editor, token)
            tooltip("Brak notatki w edytorze.")
            return

        config = get_tts_config()
        if not validate_config(config):
            finish_editor_operation(editor, token)
            return

        voices = unique(config.get("voices", []))
        if not voices:
            finish_editor_operation(editor, token)
            tooltip("Brak skonfigurowanych głosów TTS.")
            return

        def bg_task():
            return process_single_note(note, config, tasks=[task], overwrite=overwrite)

        def on_done(future):
            try:
                changed, err = future.result()
            except Exception as e:
                finish_editor_operation(editor, token)
                tooltip(f"TTS ({label}): błąd — {e}", period=8000)
                return

            if not changed:
                finish_editor_operation(editor, token)
                if err:
                    tooltip(f"TTS ({label}): {err}", period=8000)
                else:
                    source = task.get("source_field", "")
                    if source and source in note and not note[source].strip():
                        tooltip(f'TTS ({label}): pole źródłowe „{source}” jest puste.', period=5000)
                    else:
                        tooltip(f"TTS ({label}): brak audio do wygenerowania.", period=5000)
                return

            def apply():
                try:
                    if editor.note is note:
                        editor.loadNote()
                    elif note.id:
                        mw.col.update_note(note)

                    msg = f"TTS ({label}): wygenerowano audio."
                    if err:
                        msg += f" {err}"
                    tooltip(msg, period=8000)
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

        mw.taskman.run_in_background(bg_task, on_done)

    def start():
        try:
            start_inner()
        except Exception:
            finish_editor_operation(editor, token)
            raise

    try:
        editor.saveNow(start)
    except Exception:
        finish_editor_operation(editor, token)
        raise


def _on_editor_context_menu(editor_webview, menu: QMenu) -> None:
    """Add 'Generate TTS for this field' to the editor's right-click menu.

    Only shown when the focused field is the target_field of a configured
    TTS task — so the option never appears on unrelated fields.
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

    config = get_tts_config()
    matching_tasks = _tasks_for_field(field_name, config)
    if not matching_tasks:
        return

    has_sound = has_audio(note[field_name])
    menu.addSeparator()
    for task in matching_tasks:
        label = task.get("label", "TTS")
        if has_sound:
            action_label = f'Regeneruj TTS: {label}'
            overwrite = True
        else:
            action_label = f'Generuj TTS: {label}'
            overwrite = False
        action = QAction(action_label, menu)
        action.triggered.connect(
            lambda _checked=False, ed=editor, t=task, ow=overwrite:
                _on_tts_field_editor(ed, t, ow)
        )
        menu.addAction(action)


# Register the editor context-menu hook once on import.
gui_hooks.editor_will_show_context_menu.append(_on_editor_context_menu)
