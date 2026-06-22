"""Browser batch actions — AI field generation and full workflow for selected notes."""

import concurrent.futures
import logging
import threading
import time

from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import tooltip
from aqt.qt import *
from aqt.browser import Browser

from ._generator import get_config
from .field_generator import FieldGenerator

logger = logging.getLogger(__name__)


def _make_progress(browser: Browser, label: str, total: int, title: str):
    progress = QProgressDialog(label, "Anuluj", 0, total, browser)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)

    cancel_flag = {"cancelled": False}
    progress.canceled.connect(lambda: cancel_flag.update(cancelled=True))
    return progress, cancel_flag


def _save_changed_notes(browser: Browser, changed_notes: list, summary: str):
    """Persist modified notes as one undoable operation, then show the summary."""
    if not changed_notes:
        tooltip(summary, period=8000)
        return
    CollectionOp(
        parent=browser,
        op=lambda col: col.update_notes(changed_notes),
    ).success(
        lambda _changes: tooltip(summary, period=8000)
    ).run_in_background()


# ---------------------------------------------------------------------------
# AI fields batch (parallel)
# ---------------------------------------------------------------------------

def _on_generate_browser(browser: Browser):
    config = get_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    _run_batch(browser, nids, config, only_fields=None, label="Generowanie przez AI")


def _on_generate_field_browser(browser: Browser, field_name: str):
    config = get_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    _run_batch(
        browser, nids, config,
        only_fields={field_name},
        label=f"AI: {field_name}",
    )


def _run_batch(browser: Browser, nids, config: dict,
               only_fields, label: str):
    """Run a parallel AI batch. only_fields=None = all configured empty fields;
    only_fields={name} = only that target field, still skipping filled ones.
    """
    batch_limit: int = max(1, config.get("batch_limit", 3))
    sleep_time: float = config.get("batch_sleep", 1.0)
    parallel: int = max(1, int(config.get("parallel_requests", 3)))

    progress, cancel_flag = _make_progress(
        browser, f"{label}...", len(nids), "AI Generator"
    )

    state = {"done": 0, "changed": 0, "failures": 0, "last_error": None}
    changed_notes: list = []
    lock = threading.Lock()

    def process_one(nid):
        # Each call gets its own FieldGenerator — provider instances keep
        # per-request state (last_error, last_usage), so sharing one across
        # worker threads would cross-attribute errors and token usage.
        gen = FieldGenerator(config)
        try:
            note = mw.col.get_note(nid)
            changed = gen.process_note(note, only_fields=only_fields)
        except Exception as e:
            with lock:
                state["failures"] += 1
                state["last_error"] = str(e)
                state["done"] += 1
                done = state["done"]
            _report_progress(done)
            return
        with lock:
            if changed:
                changed_notes.append(note)
                state["changed"] += 1
            elif gen.last_error:
                state["failures"] += 1
                state["last_error"] = gen.last_error
            state["done"] += 1
            done = state["done"]
        _report_progress(done)

    def _report_progress(done: int):
        def _update(d=done):
            progress.setLabelText(f"Przetwarzanie {d}/{len(nids)}...")
            progress.setValue(d)
        mw.taskman.run_on_main(_update)

    def task():
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
            for start in range(0, len(nids), batch_limit):
                if cancel_flag["cancelled"]:
                    break
                if start > 0 and sleep_time > 0:
                    time.sleep(sleep_time)
                chunk = nids[start:start + batch_limit]
                futures = [pool.submit(process_one, nid) for nid in chunk]
                concurrent.futures.wait(futures)

    def on_done(fut):
        progress.close()
        try:
            fut.result()
        except Exception as e:
            tooltip(f"Błąd podczas generowania: {e}", period=5000)
            return
        parts = [f"Zaktualizowano: {state['changed']}"]
        if state["failures"]:
            parts.append(f"błędy: {state['failures']}")
        if cancel_flag["cancelled"]:
            parts.append("przerwano")
        if state["last_error"]:
            parts.append(state["last_error"])
        _save_changed_notes(browser, changed_notes, " · ".join(parts))

    mw.taskman.run_in_background(task, on_done)


# ---------------------------------------------------------------------------
# Workflow batch — AI → Dictionary → TTS for each selected note
# ---------------------------------------------------------------------------

def _on_workflow_browser(browser: Browser):
    from .workflow import get_workflow_config, execute_step

    wf = get_workflow_config()
    steps = [s for s in wf.get("steps", []) if isinstance(s, dict)]
    if not steps:
        tooltip("Brak skonfigurowanego workflow. Sprawdź ustawienia.")
        return

    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    label = wf.get("editor_label", "Generuj fiszkę")
    progress, cancel_flag = _make_progress(
        browser, f"{label}...", len(nids), "Workflow"
    )

    state = {"errors": 0, "last_error": None}
    changed_notes: list = []

    def task():
        for i, nid in enumerate(nids):
            if cancel_flag["cancelled"]:
                break

            def _update(i=i):
                progress.setLabelText(f"{label}: notatka {i + 1}/{len(nids)}...")
                progress.setValue(i + 1)
            mw.taskman.run_on_main(_update)

            try:
                note = mw.col.get_note(nid)
            except Exception as e:
                state["errors"] += 1
                state["last_error"] = str(e)
                continue

            note_modified = False
            for step in steps:
                if cancel_flag["cancelled"]:
                    break
                try:
                    modified, err = execute_step(note, step)
                except Exception as e:
                    modified, err = False, str(e)
                note_modified = note_modified or modified
                if err:
                    state["errors"] += 1
                    state["last_error"] = err
                    logger.error(f"Workflow batch (nid={nid}): {err}")
            if note_modified:
                changed_notes.append(note)

    def on_done(fut):
        progress.close()
        try:
            fut.result()
        except Exception as e:
            tooltip(f"Błąd workflow: {e}", period=5000)
            return
        parts = [f"Zaktualizowano: {len(changed_notes)}"]
        if state["errors"]:
            parts.append(f"błędy: {state['errors']}")
        if cancel_flag["cancelled"]:
            parts.append("przerwano")
        if state["last_error"]:
            parts.append(state["last_error"])
        _save_changed_notes(browser, changed_notes, " · ".join(parts))

    mw.taskman.run_in_background(task, on_done)


def _all_configured_target_fields(config: dict, manual_only: bool = False) -> list[str]:
    """Flattened list of distinct target field names across all note types.

    Order follows first appearance (stable across menu builds). Used to build
    the per-field submenu — process_note() dispatches per note type internally,
    so 'AI: def' will use the right prompt for each note's type.

    manual_only=False (default) → only fields WITHOUT manual_only flag (auto-eligible).
    manual_only=True → only fields WITH manual_only=True (blocked from auto/batch).
    """
    seen: dict[str, None] = {}  # py3.7+ dict preserves insertion order
    for nt_name, nt_cfg in config.get("note_types", {}).items():
        if not isinstance(nt_cfg, dict):
            continue
        for entry in nt_cfg.values():
            if not isinstance(entry, dict):
                continue
            target = (entry.get("target") or "").strip()
            if not target:
                continue
            is_manual = bool(entry.get("manual_only"))
            if is_manual != manual_only:
                continue
            seen.setdefault(target, None)
    return list(seen.keys())


def add_to_context_menu(browser: Browser, menu):
    from .workflow import get_workflow_config

    wf = get_workflow_config()
    if wf.get("enabled", True) and wf.get("steps"):
        label = wf.get("editor_label", "Generuj fiszkę")
        wf_action = QAction(f"{label} (workflow)", browser)
        qconnect(wf_action.triggered, lambda: _on_workflow_browser(browser))
        menu.addAction(wf_action)

    config = get_config()
    target_fields = _all_configured_target_fields(config)
    manual_fields = _all_configured_target_fields(config, manual_only=True)

    gen_menu = menu.addMenu("Generuj pola")
    all_action = QAction("Wszystkie puste", browser)
    qconnect(all_action.triggered, lambda: _on_generate_browser(browser))
    gen_menu.addAction(all_action)

    if target_fields:
        gen_menu.addSeparator()
        for field_name in target_fields:
            action = QAction(f"AI: {field_name}", browser)
            qconnect(
                action.triggered,
                lambda _checked=False, fn=field_name:
                    _on_generate_field_browser(browser, fn),
            )
            gen_menu.addAction(action)

    if manual_fields:
        blocked_menu = menu.addMenu("Generuj zablokowane")
        all_blocked = QAction("Wszystkie zablokowane", browser)
        qconnect(
            all_blocked.triggered,
            lambda: _run_batch(
                browser, browser.selected_notes(), config,
                only_fields=set(manual_fields),
                label="AI: zablokowane",
            ),
        )
        blocked_menu.addAction(all_blocked)
        blocked_menu.addSeparator()
        for field_name in manual_fields:
            action = QAction(f"AI: {field_name}", browser)
            qconnect(
                action.triggered,
                lambda _checked=False, fn=field_name:
                    _on_generate_field_browser(browser, fn),
            )
            blocked_menu.addAction(action)
