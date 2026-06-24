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
from anki.collection import OpChanges

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


def _save_changed_notes(browser: Browser, changed_notes: list, summary: str,
                        on_complete=None):
    """Persist modified notes as one undoable operation, then show the summary.

    on_complete (if given) runs after the save commits — used to chain steps.
    """
    if not changed_notes:
        tooltip(summary, period=8000)
        if on_complete:
            on_complete()
        return

    def _saved(_changes):
        tooltip(summary, period=8000)
        if on_complete:
            on_complete()

    CollectionOp(
        parent=browser,
        op=lambda col: col.update_notes(changed_notes),
    ).success(_saved).run_in_background()


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
               only_fields, label: str, on_complete=None):
    """Run a parallel AI batch. only_fields=None = all configured empty fields;
    only_fields={name} = only that target field, still skipping filled ones.

    on_complete (if given) runs after the save commits — used to chain steps.
    """
    batch_limit: int = max(1, config.get("batch_limit", 3))
    sleep_time: float = config.get("batch_sleep", 1.0)
    parallel: int = max(1, int(config.get("parallel_requests", 3)))

    # Load notes on the main thread — the Anki collection is single-threaded,
    # so workers must never touch mw.col. Each note is read once here and only
    # mutated in memory by process_note(); collection writes happen on the main
    # thread in _save_changed_notes(). note_type() is called to warm the models
    # cache here too, so worker threads only do in-memory dict reads on it.
    nids = list(nids)
    try:
        notes = []
        for nid in nids:
            note = mw.col.get_note(nid)
            note.note_type()
            notes.append(note)
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return

    progress, cancel_flag = _make_progress(
        browser, f"{label}...", len(notes), "AI Generator"
    )

    state = {"done": 0, "changed": 0, "failures": 0, "last_error": None}
    changed_notes: list = []
    lock = threading.Lock()

    def process_one(note):
        # Each call gets its own FieldGenerator — provider instances keep
        # per-request state (last_error, last_usage), so sharing one across
        # worker threads would cross-attribute errors and token usage.
        gen = FieldGenerator(config)
        try:
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
            progress.setLabelText(f"Przetwarzanie {d}/{len(notes)}...")
            progress.setValue(d)
        mw.taskman.run_on_main(_update)

    def task():
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
            for start in range(0, len(notes), batch_limit):
                if cancel_flag["cancelled"]:
                    break
                if start > 0 and sleep_time > 0:
                    time.sleep(sleep_time)
                chunk = notes[start:start + batch_limit]
                futures = [pool.submit(process_one, n) for n in chunk]
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
        _save_changed_notes(browser, changed_notes, " · ".join(parts), on_complete)

    mw.taskman.run_in_background(task, on_done)


# ---------------------------------------------------------------------------
# Full pipeline — generate empty → TTS all → split przyklad → generate blocked
# ---------------------------------------------------------------------------

def _on_full_pipeline(browser: Browser):
    """One click: generuj puste → TTS wszystkie → rozdziel przyklad → zablokowane.

    Each step runs only after the previous one has committed to the collection,
    so every step reads the fields the previous step just wrote.
    """
    nids = list(browser.selected_notes())
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    config = get_config()
    manual_fields = set(_all_configured_target_fields(config, manual_only=True))

    from ..tts.processor import process_tasks_async
    from ..tts.config import get_tts_config, get_tasks
    from ..field_splitter import _run_batch as fs_run_batch

    def step4_blocked():
        if not manual_fields:
            return
        _run_batch(browser, nids, config,
                   only_fields=manual_fields, label="AI: zablokowane")

    def step3_split():
        fs_run_batch(nids, on_complete=step4_blocked)

    def step2_tts():
        tasks = get_tasks(get_tts_config())
        if not tasks:
            step3_split()
            return
        process_tasks_async(browser, nids, tasks, on_complete=step3_split)

    _run_batch(browser, nids, config, only_fields=None,
               label="Generowanie przez AI", on_complete=step2_tts)


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


def _on_split_then_nauka(browser: Browser):
    """One click: split przyklad → p1/p2/p3, then AI-generate the *-nauka fields.

    # ponytail: hardcoded to the user's przyklad → p1/p2/p3 → p{1,2,3}-nauka
    # flow. Generalise only if a second such chain appears.
    """
    nids = list(browser.selected_notes())
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    try:
        from ..field_splitter import (
            _get_config as _fs_get_config,
            _process_note as _fs_split,
        )
    except Exception:
        tooltip("Moduł „Rozdzielanie pól” jest wyłączony.", period=4000)
        return

    fs_cfg = _fs_get_config()
    config = get_config()
    nauka_fields = {"p1-nauka", "p2-nauka", "p3-nauka"}

    def split_op(col):
        changed = []
        for nid in nids:
            note = col.get_note(nid)
            if _fs_split(note, fs_cfg):
                changed.append(note)
        return col.update_notes(changed) if changed else OpChanges()

    def after_split(_changes):
        # Split is saved; now generate the nauka fields (reads fresh p1/p2/p3).
        _run_batch(browser, nids, config, only_fields=nauka_fields,
                   label="AI: nauka (p1–p3)")

    CollectionOp(parent=browser, op=split_op).success(after_split).run_in_background()


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

    nauka_action = QAction("Rozdziel + generuj naukę (p1–p3)", browser)
    qconnect(nauka_action.triggered, lambda: _on_split_then_nauka(browser))
    menu.addAction(nauka_action)

    pipeline_action = QAction("Generuj wszystko: puste → TTS → rozdziel → zablokowane", browser)
    qconnect(pipeline_action.triggered, lambda: _on_full_pipeline(browser))
    menu.addAction(pipeline_action)

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
