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


# Which built-in (auto-generated) right-click sections are shown. Workflows are
# always listed; these toggles only govern the atomic building-block entries.
DEFAULT_CONTEXT_MENU = {
    "dictionary": True,    # "Pobierz wymowę"
    "tts": True,           # "TTS"
    "ai_fields": True,     # "Generuj pola"
    "ai_blocked": True,    # "Generuj zablokowane"
    "field_splitter": True,  # "Rozdziel pole"
}

# The two pipelines that used to be hardcoded in Python — re-seeded as editable
# workflows during migration so the menu loses nothing.
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
    {
        "name": "Rozdziel + generuj naukę (p1–p3)",
        "editor_button": False,
        "steps": [
            {"module": "field_splitter", "action": "split"},
            {"module": "ai", "action": "generate",
             "fields": ["p1-nauka", "p2-nauka", "p3-nauka"]},
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
    """One-time: legacy single `workflow` → `workflows` list. Re-seeds the two
    formerly-hardcoded pipelines and default `context_menu` so nothing is lost."""
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


def execute_step(note, step: dict) -> tuple[bool, Optional[str]]:
    """Execute a single workflow step on a note (background thread).

    Returns (modified, error_message). The note is mutated in memory only.
    """
    module = step.get("module", "")
    action = step.get("action", "")

    if module == "ai" and action == "generate":
        from ._generator import get_generator, get_config
        gen = get_generator()
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
    editor_id = id(editor)
    if editor_id in _RUNNING:
        tooltip("Workflow już trwa...", period=2000)
        return

    steps = [s for s in workflow.get("steps", []) if isinstance(s, dict)]
    if not steps:
        tooltip("Brak kroków w tym workflow. Sprawdź ustawienia.")
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
