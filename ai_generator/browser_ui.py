"""Browser batch actions — AI field generation and full workflow for selected notes."""

import concurrent.futures
import logging
import threading
import time

from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import tooltip, askUser
from aqt.qt import *
from aqt.browser import Browser

from ..common import start_progress, update_progress, finish_progress
from . import batch_backfill
from ._generator import get_config
from .field_generator import FieldGenerator

logger = logging.getLogger(__name__)


def _save_changed_notes(browser: Browser, changed_notes: list, summary: str):
    """Persist modified notes as one undoable operation, then show the summary."""
    if not changed_notes:
        tooltip(summary, period=8000)
        return

    def _saved(_changes):
        try:
            from ..deck_router import route_after_edit
            route_after_edit(browser, [n.id for n in changed_notes])
        except Exception:
            logger.exception("deck_router: routing po edycji nie powiódł się")
        tooltip(summary, period=8000)

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
               only_fields, label: str):
    """Run a parallel AI batch. only_fields=None = all configured empty fields;
    only_fields={name} = only that target field, still skipping filled ones.
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

    cancel_flag = start_progress(label, len(notes), "AI Generator")

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
        update_progress(cancel_flag, label, done, len(notes))

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
        finish_progress()
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
# Anthropic Batch API backfill — async, ~50% cheaper (separate from sync path)
# ---------------------------------------------------------------------------

def _on_batch_submit(browser: Browser, only_fields=None):
    config = get_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return
    try:
        notes = []
        for nid in nids:
            note = mw.col.get_note(nid)
            note.note_type()
            notes.append(note)
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return

    items, skipped = batch_backfill.build_items(notes, config, only_fields=only_fields)
    if not items:
        msg = "Brak pustych pól z dostawcą Anthropic/OpenAI w zaznaczeniu."
        if skipped:
            msg += f" (pominięto {skipped} pól z innym dostawcą lub bez modelu)"
        tooltip(msg, period=6000)
        return

    text = (
        f"Wyślę {len(items)} zapytań (z {len(notes)} notatek) do Batch API.\n"
        f"{batch_backfill.summarize(items)}\n\n"
        f"Batch jest ~50% tańszy, ale asynchroniczny — wyniki pojawią się później "
        f"(zwykle poniżej 1h, do 24h) i zostaną automatycznie dopisane do pustych "
        f"pól przy starcie Anki lub po kliknięciu „Sprawdź batche”."
    )
    if skipped:
        text += f"\n\nPominięto {skipped} pól (dostawca inny niż Anthropic/OpenAI lub brak modelu)."
    text += "\n\nWysłać?"
    if not askUser(text, title="Batch API — potwierdzenie", parent=browser):
        return

    def task():
        return batch_backfill.submit(items, config)

    def on_done(fut):
        try:
            records, errors = fut.result()
        except Exception as e:
            tooltip(f"Błąd wysyłki batcha: {e}", period=6000)
            return
        if not records:
            tooltip("Batch nie wysłany: " + " · ".join(errors), period=8000)
            return
        sent = sum(r["count"] for r in records)
        msg = f"Wysłano batche: {len(records)} ({sent} zapytań). Wyniki dopiszą się automatycznie."
        if errors:
            msg += " · błędy: " + " · ".join(errors)
        tooltip(msg, period=8000)

    mw.taskman.run_in_background(task, on_done)


def check_pending_batches(silent: bool = True):
    """Poll pending Anthropic batches and apply any that have finished.

    silent=True (startup) suppresses "nothing yet" tooltips; silent=False
    (manual button) reports progress even when nothing is ready.
    """
    config = get_config()
    if not batch_backfill.pending_batches():
        if not silent:
            tooltip("Brak oczekujących batchy.")
        return

    def task():
        return batch_backfill.poll_results(config)

    def on_done(fut):
        try:
            ended, still, errors = fut.result()
        except Exception as e:
            if not silent:
                tooltip(f"Błąd sprawdzania batchy: {e}", period=6000)
            return
        if not ended:
            if not silent:
                parts = [f"W toku: {still}"]
                if errors:
                    parts.append(f"błędy odpytania: {len(errors)}")
                tooltip(" · ".join(parts), period=5000)
            return
        summary = batch_backfill.apply_results(mw.col, ended)
        parts = [f"Batch: dopisano {summary['filled']}"]
        if summary["failed"]:
            parts.append(f"błędy: {summary['failed']}")
        if summary["skipped"]:
            parts.append(f"pominięto: {summary['skipped']}")
        if still:
            parts.append(f"w toku: {still}")
        msg = " · ".join(parts)
        changed = summary["changed_notes"]
        if changed:
            CollectionOp(
                parent=mw,
                op=lambda col: col.update_notes(changed),
            ).success(lambda _c: tooltip(msg, period=8000)).run_in_background()
        else:
            tooltip(msg, period=8000)

    mw.taskman.run_in_background(task, on_done)


# ---------------------------------------------------------------------------
# Workflow batch — runs a workflow's steps per selected note
# ---------------------------------------------------------------------------

def _on_workflow_browser(browser: Browser, workflow: dict):
    from .workflow import execute_step

    steps = [s for s in workflow.get("steps", []) if isinstance(s, dict)]
    if not steps:
        tooltip("Brak kroków w tym workflow. Sprawdź ustawienia.")
        return

    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    config = get_config()
    batch_limit: int = max(1, config.get("batch_limit", 3))
    sleep_time: float = config.get("batch_sleep", 1.0)
    parallel: int = max(1, int(config.get("parallel_requests", 3)))

    # Preload notes on the main thread (collection is single-threaded). Workers
    # only mutate notes in memory; the one collection touch left in a worker is
    # mw.col.media.write_data() inside the TTS step, which the backend
    # serializes. Collection writes for the notes themselves happen on the main
    # thread in _save_changed_notes().
    try:
        notes = []
        for nid in nids:
            note = mw.col.get_note(nid)
            note.note_type()
            notes.append(note)
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return

    label = workflow.get("name", "Workflow")
    cancel_flag = start_progress(label, len(notes), "Workflow")

    state = {"done": 0, "errors": 0, "last_error": None}
    changed_notes: list = []
    lock = threading.Lock()

    def process_one(note):
        # Each note gets its own FieldGenerator — steps within one note stay
        # sequential, but notes run in parallel, so providers must not share
        # last_error/last_usage across threads.
        gen = FieldGenerator(config)
        note_modified = False
        for step in steps:
            if cancel_flag["cancelled"]:
                break
            try:
                modified, err = execute_step(note, step, ai_generator=gen)
            except Exception as e:
                modified, err = False, str(e)
            note_modified = note_modified or modified
            if err:
                with lock:
                    state["errors"] += 1
                    state["last_error"] = err
                logger.error(f"Workflow batch (nid={note.id}): {err}")
        with lock:
            if note_modified:
                changed_notes.append(note)
            state["done"] += 1
            done = state["done"]
        _report_progress(done)

    def _report_progress(done: int):
        update_progress(cancel_flag, label, done, len(notes))

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
        finish_progress()
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
    from .workflow import get_workflows, get_context_menu

    cm = get_context_menu()

    # User-defined workflows first — each is one menu entry.
    for wf in get_workflows():
        if not [s for s in wf.get("steps", []) if isinstance(s, dict)]:
            continue
        name = wf.get("name", "Workflow")
        wf_action = QAction(name, browser)
        qconnect(
            wf_action.triggered,
            lambda _checked=False, w=wf: _on_workflow_browser(browser, w),
        )
        menu.addAction(wf_action)

    config = get_config()
    target_fields = _all_configured_target_fields(config)
    manual_fields = _all_configured_target_fields(config, manual_only=True)

    if cm.get("ai_fields", True):
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

    if cm.get("ai_fields", True):
        batch_menu = menu.addMenu("Batch API (Anthropic/OpenAI, tańszy)")
        submit_all = QAction("Wyślij zaznaczone — wszystkie pola", browser)
        qconnect(submit_all.triggered, lambda: _on_batch_submit(browser))
        batch_menu.addAction(submit_all)

        if target_fields:
            batch_menu.addSeparator()
            for field_name in target_fields:
                action = QAction(f"Batch: {field_name}", browser)
                qconnect(
                    action.triggered,
                    lambda _checked=False, fn=field_name:
                        _on_batch_submit(browser, only_fields={fn}),
                )
                batch_menu.addAction(action)

        batch_menu.addSeparator()
        check_action = QAction("Sprawdź batche i zastosuj wyniki", browser)
        qconnect(check_action.triggered, lambda: check_pending_batches(silent=False))
        batch_menu.addAction(check_action)

    if cm.get("ai_blocked", True) and manual_fields:
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
