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
    finish_editor_operation,
)

logger = logging.getLogger(__name__)

_STEP_MODULES = {
    "ai": ("ai_generator", "AI"),
    "dictionary": ("dictionary", "Słownik"),
    "tts": ("tts", "TTS"),
    "field_splitter": ("field_splitter", "Rozdzielanie pól"),
}
_STARTUP_MODULES = dict(
    (mw.addonManager.getConfig(ADDON_NAME) or {}).get("modules", {})
)


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


def disabled_step_modules(steps: list[dict], cfg: Optional[dict] = None) -> list[str]:
    """Return unique labels of disabled modules required by workflow steps."""
    modules = cfg.get("modules", {}) if cfg is not None else _STARTUP_MODULES
    disabled: list[str] = []
    for step in steps:
        key, label = _STEP_MODULES.get(step.get("module"), (None, None))
        if key and not modules.get(key, True) and label not in disabled:
            disabled.append(label)
    return disabled


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

    disabled = disabled_step_modules(steps)
    if disabled:
        tooltip(
            "Workflow wymaga wyłączonych modułów: " + ", ".join(disabled)
            + ". Włącz je w ustawieniach i uruchom ponownie Anki.",
            period=6000,
        )
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

    All steps operate on the note captured when the workflow started, so
    switching notes in the editor mid-run cannot corrupt another note.
    Collection writes happen on the main thread, after each step.
    """
    total = len(steps)

    # Jedna instancja na cały przebieg — kroki AI reużywają cache providerów,
    # a równoległe przebiegi (dwa okna edytora) nie współdzielą stanu.
    from ._generator import get_config
    from .field_generator import FieldGenerator
    gen = FieldGenerator(get_config())

    def run_step(i: int):
        if i >= total:
            try:
                if editor.note is note:
                    editor.loadNote()
            except Exception:
                pass  # editor may have been closed mid-run
            finally:
                finish_editor_operation(editor, token)
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
            return execute_step(note, step, ai_generator=gen)

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

        try:
            mw.taskman.run_in_background(bg_task, on_done)
        except Exception as e:
            finish_editor_operation(editor, token)
            tooltip(f"Błąd workflow: {e}", period=5000)

    run_step(0)
