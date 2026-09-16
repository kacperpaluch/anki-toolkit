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
from ..common.editor_operation import (
    active_editor_operation,
    begin_editor_operation,
    detach_note,
    editor_shows_note,
    finish_editor_operation,
    merge_editor_note,
)

logger = logging.getLogger(__name__)


# Which built-in (auto-generated) right-click sections are shown. Workflows are
# always listed; these toggles only govern the atomic building-block entries.
DEFAULT_CONTEXT_MENU = {
    "dictionary": True,    # "Pobierz wymowę"
    "tts": True,           # "TTS"
    "ai_fields": True,     # "Generuj pola"
    "ai_blocked": True,    # "Generuj zablokowane"
    "field_splitter": True,  # "Rozdziel pole"
}

# Re-seeded as an editable workflow during migration so the menu loses nothing.
# Only generic, field-name-agnostic steps here — a personal p1–p3 pipeline is
# something the user builds in the UI, not something a fresh install inherits.
_DEFAULT_PIPELINES = [
    {
        "name": "Generuj wszystko: puste → TTS → rozdziel → zablokowane",
        "editor_button": False,
        "steps": [
            {"module": "ai", "action": "generate", "fields": "empty"},
            {"module": "tts", "action": "generate"},
            {"module": "field_splitter", "action": "split"},
            {"module": "ai", "action": "generate", "fields": "manual"},
        ],
    },
]


def get_workflows() -> list[dict]:
    """User-defined named workflows. Falls back to wrapping the legacy single
    `workflow` config so an un-migrated profile still works."""
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    wfs = full.get("workflows")
    if isinstance(wfs, list):
        return [w for w in wfs if isinstance(w, dict) and w.get("steps")]
    legacy = full.get("workflow")
    if isinstance(legacy, dict) and legacy.get("steps"):
        return [{
            "name": legacy.get("editor_label", "Generuj fiszkę"),
            "editor_button": legacy.get("enabled", True),
            "steps": legacy.get("steps", []),
        }]
    return []


def get_context_menu() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    cm = full.get("context_menu")
    if not isinstance(cm, dict):
        return dict(DEFAULT_CONTEXT_MENU)
    return {**DEFAULT_CONTEXT_MENU, **cm}


def migrate_workflows() -> None:
    """Migrate the legacy workflow and seed the former built-in pipeline."""
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    changed = False

    if not isinstance(full.get("workflows"), list):
        workflows: list[dict] = []
        legacy = full.get("workflow")
        if isinstance(legacy, dict) and legacy.get("steps"):
            workflows.append({
                "name": legacy.get("editor_label", "Generuj fiszkę"),
                "editor_button": legacy.get("enabled", True),
                "steps": legacy.get("steps", []),
            })
        workflows.extend(_DEFAULT_PIPELINES)
        full["workflows"] = workflows
        changed = True

    if not isinstance(full.get("context_menu"), dict):
        full["context_menu"] = dict(DEFAULT_CONTEXT_MENU)
        changed = True

    if changed:
        mw.addonManager.writeConfig(ADDON_NAME, full)


def _resolve_ai_fields(step: dict, ai_config: dict):
    """Map a step's `fields` parameter to a process_note() only_fields argument.

    "empty" / missing → None (all auto-eligible empty fields, skips manual_only)
    "manual"          → set of manual_only target fields
    "name" / [names]  → exactly those fields (overwrites filled ones is up to
                        process_note; here we just scope which fields)
    """
    fields = step.get("fields", "empty")
    if not fields or fields == "empty":
        return None
    if fields == "manual":
        from .browser_ui import _all_configured_target_fields
        return set(_all_configured_target_fields(ai_config, manual_only=True))
    if isinstance(fields, str):
        return {fields}
    if isinstance(fields, list):
        return set(fields)
    return None


def execute_step(note, step: dict, ai_generator=None) -> tuple[bool, Optional[str]]:
    """Execute a single workflow step on a note (background thread).

    Returns (modified, error_message). The note is mutated in memory only.

    ai_generator: optional FieldGenerator for the AI step. Callers running
    multiple steps/notes pass their own instance (per note in the parallel
    browser batch, per run in the editor workflow) — providers keep
    per-request error state, so sharing one across worker threads would
    cross-attribute errors. None = a fresh
    instance for this one step.
    """
    module = step.get("module", "")
    action = step.get("action", "")

    if module == "ai" and action == "generate":
        from ._generator import get_config
        from .field_generator import FieldGenerator
        gen = ai_generator or FieldGenerator(get_config())
        only_fields = _resolve_ai_fields(step, get_config())
        changed = gen.process_note(note, only_fields=only_fields)
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

    if module == "field_splitter" and action == "split":
        from ..field_splitter import _get_config as _fs_get_config, _process_note as _fs_process
        try:
            return _fs_process(note, _fs_get_config()), None
        except Exception as e:
            return False, str(e)

    return False, None


def run_workflow_editor(editor: Editor, workflow: dict):
    """Run one workflow's steps sequentially on the current editor note."""
    steps = [s for s in workflow.get("steps", []) if isinstance(s, dict)]
    if not steps:
        tooltip("Brak kroków w tym workflow. Sprawdź ustawienia.")
        return

    token = begin_editor_operation(
        editor, f"workflow „{workflow.get('name', 'Workflow')}”"
    )
    if token is None:
        tooltip(
            f"Anki Toolkit: trwa już {active_editor_operation(editor)}.",
            period=2500,
        )
        return

    def start():
        try:
            note = editor.note
            if note is None:
                finish_editor_operation(editor, token)
                return
            _execute_steps(editor, note, steps, token)
        except Exception as e:
            finish_editor_operation(editor, token)
            tooltip(f"Błąd workflow: {e}", period=5000)

    try:
        editor.saveNow(start)
    except Exception:
        finish_editor_operation(editor, token)
        raise


def _execute_steps(editor: Editor, note, steps: list, token):
    """Run workflow steps one by one in background. Each step waits for previous.

    All steps operate on a detached copy of the note captured when the workflow
    started: switching notes mid-run cannot corrupt another note, and typing
    mid-run is not overwritten — merge_note() writes back only the fields the
    user did not touch. Collection writes happen on the main thread, after
    each step.
    """
    total = len(steps)
    clone, before = detach_note(note)
    skipped_fields: list = []

    # Jedna instancja na cały przebieg — kroki AI reużywają cache providerów,
    # a równoległe przebiegi (dwa okna edytora) nie współdzielą stanu.
    from ._generator import get_config
    from .field_generator import FieldGenerator
    gen = FieldGenerator(get_config())

    def run_step(i: int):
        if i >= total:
            finish_editor_operation(editor, token)
            msg = (f"Workflow zakończony. Wykonano {total} "
                   f"{plural_pl(total, 'krok', 'kroki', 'kroków')}.")
            if skipped_fields:
                msg += (" Pominięto pola zmienione w trakcie: "
                        + ", ".join(sorted(set(skipped_fields))) + ".")
            tooltip(msg, period=5000)
            return

        step = steps[i]
        module = step.get("module", "")
        action = step.get("action", "")
        logger.info(f"Workflow: krok {i + 1}/{total} ({module}/{action}), nid={note.id}")

        def bg_task():
            return execute_step(clone, step, ai_generator=gen)

        def on_done(future):
            try:
                modified, err = future.result()
            except Exception as e:
                modified, err = False, str(e)

            ran = {"once": False}

            def commit():
                nonlocal err
                if ran["once"]:   # saveNow may call back synchronously
                    return
                ran["once"] = True
                try:
                    # Also rebase a no-op/failed step: the next step must see
                    # edits typed while this one was running. Refresh now so
                    # the next saveNow cannot restore the previous webview.
                    skipped_fields.extend(merge_editor_note(editor, note, clone, before))
                except Exception as e:
                    finish_editor_operation(editor, token)
                    tooltip(f"Workflow przerwany: {e}", period=8000)
                    return
                if err:
                    logger.error(f"Workflow: krok {i + 1}/{total} ({module}/{action}): {err}")
                    tooltip(f"Workflow krok {i+1}/{total} ({module}/{action}): {err}", period=5000)
                run_step(i + 1)

            # Flush the webview into the note first, so merge_note() can tell
            # a user edit from an untouched field.
            try:
                if editor_shows_note(editor, note):
                    editor.saveNow(commit)
                else:
                    commit()
            except Exception as e:
                finish_editor_operation(editor, token)
                tooltip(f"Workflow przerwany: {e}", period=8000)

        try:
            mw.taskman.run_in_background(bg_task, on_done)
        except Exception as e:
            finish_editor_operation(editor, token)
            tooltip(f"Błąd workflow: {e}", period=5000)

    run_step(0)
