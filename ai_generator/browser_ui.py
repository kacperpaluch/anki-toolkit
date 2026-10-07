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
from ..common.editor_operation import save_detached_notes, snapshot_fields, detach_note
from . import batch_backfill
from ._generator import get_config
from .field_generator import FieldGenerator, iter_note_fields

logger = logging.getLogger(__name__)


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


def _on_regenerate_field_browser(browser: Browser, field_name: str):
    config = get_config()
    notes = [mw.col.get_note(nid) for nid in browser.selected_notes()]
    eligible = [note for note in notes if list(iter_note_fields(
        note, config, only_fields={field_name}, overwrite=True))]
    if not eligible:
        tooltip("Brak pasujących notatek do regenerowania.")
        return
    if not askUser(
        f"Wygenerować ponownie pole „{field_name}” w {len(eligible)} notatkach?\n\n"
        "Istniejąca treść tego pola zostanie zastąpiona po udanym generowaniu.\n"
        "Zapis możesz cofnąć jednym krokiem w Anki.", parent=browser,
        defaultno=True,
    ):
        return
    _run_batch(browser, [n.id for n in eligible], config,
               only_fields={field_name}, label=f"Regenerowanie: {field_name}",
               overwrite=True)


def _skip_reason(note, config, only_fields, overwrite=False):
    if any(t in note.tags for t in (config.get("skip_tags") or [])):
        return "tag wykluczający generowanie AI"
    configured = list(iter_note_fields(note, config, only_fields, overwrite=True))
    if not configured:
        return "brak pasujących pól AI (typ notatki, pola lub tryb tylko na żądanie)"
    if not overwrite and not list(iter_note_fields(note, config, only_fields)):
        return "pola docelowe mają już treść"
    return None


def _show_run_report(parent, title, total, done, changed, details, cancelled,
                     skipped_at_save=()):
    from aqt.utils import showText
    from aqt.qt import sip
    if parent is None or sip.isdeleted(parent):
        parent = mw
    conflicts = set(skipped_at_save)
    saved = sum(n.id not in conflicts for n in changed)
    lines = [f"Zapisano zmiany w notatkach: {saved}",
             f"Przetworzono: {done} z {total}",
             f"Notatki z błędami: {sum(kind == 'error' for _, kind, _ in details)}",
             f"Pominięto bez zmian: {sum(kind == 'skip' for _, kind, _ in details)}",
             f"Pominięto przy zapisie (notatka zmieniona lub usunięta): {len(conflicts)}"]
    if cancelled:
        lines.append("Przerwano operację; zakończone wyniki zostały zapisane.")
    if details or conflicts:
        lines.append("\nSzczegóły — identyfikatory można wyszukać w Browserze przez nid:123:")
        for nid, kind, reason in sorted(details):
            lines.append(f"nid:{nid} — {'Błąd' if kind == 'error' else 'Pominięto'}: {reason}")
        for nid in sorted(conflicts):
            lines.append(f"nid:{nid} — nie zapisano: notatka zmieniona lub usunięta podczas pracy")
    text = "\n".join(lines)
    logger.info("%s: %s", title, text)
    showText(text, parent=parent, title=title, type="text", copyBtn=True)


def _run_batch(browser: Browser, nids, config: dict,
               only_fields, label: str, overwrite: bool = False):
    """Run a parallel AI batch. only_fields=None = all configured empty fields;
    only_fields={name} scopes the target; overwrite requires explicit confirmation.
    """
    batch_limit: int = max(1, config.get("batch_limit", 3))
    sleep_time: float = config.get("batch_sleep", 1.0)
    parallel: int = max(1, int(config.get("parallel_requests", 3)))

    # Load notes on the main thread — the Anki collection is single-threaded,
    # so workers must never touch mw.col. Each note is read once here and only
    # mutated in memory by process_note(); collection writes happen on the main
    # thread in save_detached_notes(). detach_note() freezes the model lookup
    # so workers do not reach the collection through note_type().
    nids = list(nids)
    try:
        notes = []
        for nid in nids:
            note, _before = detach_note(mw.col.get_note(nid))
            notes.append(note)
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return
    col = mw.col
    before = snapshot_fields(notes)

    cancel_flag = start_progress(label, len(notes), "AI Generator")

    state = {"done": 0}
    details = []
    changed_notes: list = []
    lock = threading.Lock()

    def process_one(note):
        # Each call gets its own FieldGenerator — provider instances keep
        # last_error, so sharing one across worker threads would cross-attribute
        # failures.
        gen = FieldGenerator(config)
        try:
            reason = _skip_reason(note, config, only_fields, overwrite)
            changed = gen.process_note(note, only_fields=only_fields, overwrite=overwrite)
        except Exception as e:
            with lock:
                if list(note.fields) != before[note.id]:
                    changed_notes.append(note)
                details.append((note.id, "error", str(e)))
                state["done"] += 1
                done = state["done"]
            _report_progress(done)
            return
        with lock:
            if list(note.fields) != before[note.id]:
                changed_notes.append(note)
            # Independently of what was written: one field failing while
            # another succeeded used to be reported as a clean run.
            if gen.last_error:
                details.append((note.id, "error", " · ".join(gen.errors) or gen.last_error))
            elif list(note.fields) == before[note.id]:
                details.append((note.id, "skip", reason or (
                    "wynik identyczny z dotychczasową treścią" if changed
                    else "zadanie nie zwróciło zmian")))
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
        save_detached_notes(
            browser, col, changed_notes, before, label,
            on_saved=lambda skipped: _show_run_report(
                browser, label, len(notes), state["done"], changed_notes,
                details, cancel_flag["cancelled"], skipped),
        )

    mw.taskman.run_in_background(task, on_done, uses_collection=False)


# ---------------------------------------------------------------------------
# Batch API backfill — async, ~50% cheaper (Anthropic + OpenAI + OpenRouter;
# separate from the sync path)
# ---------------------------------------------------------------------------

def _on_batch_submit(browser: Browser, only_fields=None):
    col = mw.col
    if col is None:
        return
    col_id = col.path
    config = get_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return
    try:
        notes = []
        for nid in nids:
            note, _before = detach_note(mw.col.get_note(nid))
            notes.append(note)
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return

    items, skipped = batch_backfill.build_items(notes, config, only_fields=only_fields)
    # A field sitting in a pending batch is still empty, so build_items picks
    # it again — re-sending the same selection before the results land would
    # pay for every request twice.
    inflight = batch_backfill.inflight_fields()
    resent = [i for i in items if (i["nid"], i["field"]) in inflight]
    if resent:
        items = [i for i in items if (i["nid"], i["field"]) not in inflight]
        for n, item in enumerate(items):  # keep custom_ids dense and unique
            item["custom_id"] = f"i{n}"
    if not items and resent:
        tooltip(
            f"Wszystkie {len(resent)} pól czeka już w wysłanym batchu — "
            f"nic nie wysyłam. Wyniki dopiszą się automatycznie.",
            period=6000,
        )
        return
    if not items:
        msg = "Brak pustych pól z dostawcą Anthropic/OpenAI/OpenRouter w zaznaczeniu."
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
        text += f"\n\nPominięto {skipped} pól (dostawca inny niż Anthropic/OpenAI/OpenRouter lub brak modelu)."
    if resent:
        text += f"\n\nPominięto {len(resent)} pól, które czekają już w wysłanym batchu."
    text += "\n\nWysłać?"
    if not askUser(text, title="Batch API — potwierdzenie", parent=browser):
        return
    if mw.col is not col:
        return

    def task():
        return batch_backfill.submit(items, config, col_id=col_id)

    def on_done(fut):
        try:
            records, errors = fut.result()
        except Exception as e:
            tooltip(f"Błąd wysyłki batcha: {e}", period=6000)
            return
        deferred_only = batch_backfill.only_deferred(errors)
        if not records and not deferred_only:
            tooltip("Batch nie wysłany: " + " · ".join(errors), period=8000)
            return
        # Remember the selection so the auto-poll cycle keeps sending the
        # remaining (deferred) slices until every field is filled — hands-off.
        # A real failure (bad key, rejected request) creates no job: it would
        # upload and fail again every minute for a day.
        sent = sum(r["count"] for r in records)
        batch_backfill.add_job(nids, only_fields, total=len(items), sent=sent,
                               col_id=col_id)
        if not records:
            tooltip("Kolejka OpenAI jest pełna — zaznaczenie wyślę automatycznie, "
                    "gdy zwolni się miejsce.", period=8000)
            return
        msg = f"Wysłano batche: {len(records)} ({sent} zapytań). Wyniki dopiszą się automatycznie."
        if errors:
            msg += " · błędy: " + " · ".join(errors)
        tooltip(msg, period=8000)

    mw.taskman.run_in_background(task, on_done, uses_collection=False)


# One poll at a time — the timer tick, the manual button and profile-open all
# call this, and two overlapping runs would apply (and clean up) the same
# results twice. Keep ownership until the write callback, with no time-based
# expiry: polling many batches can legitimately take more than ten minutes.
_checking = False


def check_pending_batches(silent: bool = True):
    """Poll pending batches, apply finished ones, then auto-submit the next slice
    of any active backfill job (hands-off draining under the OpenAI token cap).

    silent=True (startup / timer) suppresses "nothing yet" tooltips; silent=False
    (manual button) reports progress even when nothing is ready.
    """
    global _checking
    if _checking:
        if not silent:
            tooltip("Sprawdzanie batchy już trwa.")
        return
    if mw.col is None:
        return
    if mw.progress and mw.progress.busy():
        return  # don't race a modal browser batch, sync, or collection operation
    col = mw.col
    config = get_config()
    records = batch_backfill.pending_batches()
    if not records and not batch_backfill.active_jobs():
        if not silent:
            unowned = batch_backfill.unowned_records()
            tooltip(
                f"Wstrzymano {unowned} starszych wpisów bez przypisanego profilu. "
                "Wymagają ręcznego przypisania kolekcji w ai_batches.json (opis w README)."
                if unowned else "Brak oczekujących batchy.", period=8000)
        return

    _checking = True

    def task():
        return batch_backfill.poll_results(config, records=records)

    def release():
        global _checking
        _checking = False

    def apply_done(fut):
        try:
            ended, still, errors = fut.result()
        except Exception as e:
            release()
            if not silent:
                tooltip(f"Błąd sprawdzania batchy: {e}", period=6000)
            return
        if mw.col is not col:
            release()
            return  # leave records pending for the original profile
        if mw.progress and mw.progress.busy():
            release()
            return  # a collection operation started while HTTP was running
        # Advance jobs when something finished (frees the token budget) or the
        # queue is fully drained (send the first slice of the remainder).
        should_advance = bool(ended) or still == 0
        summary = (batch_backfill.apply_results(mw.col, ended) if ended
                   else {"filled": 0, "failed": 0, "skipped": 0, "changed_notes": []})
        applied_ids = list(ended.keys())

        msg = None
        if ended:
            parts = [f"Batch: dopisano {summary['filled']}"]
            if summary["failed"]:
                parts.append(f"błędy: {summary['failed']}")
            if summary["skipped"]:
                parts.append(f"pominięto: {summary['skipped']}")
            if still:
                parts.append(f"w toku: {still}")
            msg = " · ".join(parts)
            # Tooltip znika po kilku sekundach — zostaw trwały ślad w logach,
            # symetrycznie do logu „Batch ... wysłany" przy submit.
            logger.info(msg)
        elif not silent:
            parts = [f"W toku: {still}"]
            if errors:
                parts.append(f"błędy odpytania: {len(errors)}")
            tooltip(" · ".join(parts), period=5000)

        def after():
            # Mark applied only once the results are safely in the collection —
            # if Anki dies earlier, the next poll re-downloads and re-applies.
            try:
                if mw.col is not col:
                    return
                if applied_ids:
                    batch_backfill.mark_applied(applied_ids)
                    applied_records = [p["record"] for p in ended.values()]
                    mw.taskman.run_in_background(
                        lambda: batch_backfill.cleanup_openai_files(applied_records, config),
                        uses_collection=False,
                    )
                if should_advance:
                    _advance_jobs(config)
            finally:
                release()

        def on_write_failed(exc):
            # Don't mark applied — the next poll re-downloads and re-applies.
            release()
            logger.error(f"Batch: zapis wyników nie powiódł się: {exc}")
            tooltip(f"Batch: zapis wyników nie powiódł się: {exc}", period=8000)

        changed = summary["changed_notes"]
        if changed:
            # Advance only AFTER the write commits, so build_items sees the just
            # filled fields and doesn't re-send them.
            CollectionOp(
                parent=mw,
                op=lambda active_col: _write_batch_results(active_col, col, ended),
            ).success(
                lambda _c: (tooltip(msg, period=8000), after())
            ).failure(on_write_failed).run_in_background()
        else:
            if msg:
                tooltip(msg, period=8000)
            after()

    def on_done(fut):
        try:
            apply_done(fut)
        except Exception as exc:
            release()
            logger.exception("Batch: nie udało się zastosować wyników")
            tooltip(f"Batch: błąd zapisu wyników: {exc}", period=8000)

    try:
        mw.taskman.run_in_background(task, on_done, uses_collection=False)
    except Exception:
        release()
        raise


def _write_batch_results(active_col, expected_col, ended):
    if active_col is not expected_col:
        raise RuntimeError("Profil zmienił się przed zapisem batcha")
    # Re-read under CollectionOp: another operation may have filled the fields
    # between the poll callback and this queued write.
    summary = batch_backfill.apply_results(active_col, ended)
    return active_col.update_notes(summary["changed_notes"])


# Guard against overlapping runs (timer tick + manual "Sprawdź batche" +
# profile open) — two concurrent submits would double-send the same fields.
_advance_running = False
_scan_offsets = {}  # in-memory cursors; restarting simply rescans from the start
_scan_clean = {}    # notes in a row with nothing left to send; a full lap ends the job


def _advance_jobs(config: dict):
    """Submit the next budget-worth of still-empty, not-in-flight fields for each
    active backfill job. Main thread (reads the collection); HTTP submit runs in
    a background task. A job whose fields are all filled is marked done."""
    global _advance_running
    if _advance_running:
        return
    col = mw.col
    if col is None:
        return
    col_id = col.path
    jobs = batch_backfill.active_jobs()
    if not jobs:
        return
    job_cursor = (col_id, "")
    start = _scan_offsets.get(job_cursor, 0) % len(jobs)
    jobs = jobs[start:] + jobs[:start]
    _scan_offsets[job_cursor] = (start + 1) % len(jobs)
    # Two independent send budgets: OpenAI's org-wide enqueued-token cap, and a
    # plain per-tick slice for the providers that have no such cap — an
    # exhausted OpenAI queue used to stall Anthropic/OpenRouter jobs too.
    caps = {
        "openai": batch_backfill.openai_budget_left(config),
        "other": batch_backfill.slice_tokens(config),
    }
    if max(caps.values()) <= 0:
        return
    used = {"openai": 0, "other": 0}
    # Everything looked at counts against one scan budget, so a tick ends even
    # when every item found belongs to a bucket that is already full —
    # rendering prompts for the whole remainder froze the UI for no gain.
    scan_cap = max(caps.values())
    scanned = 0
    scanned_notes = 0

    def bucket(item):
        return "openai" if item["provider"] == "openai" else "other"

    inflight = batch_backfill.inflight_fields()
    seen = set(inflight)  # also dedups fields shared across overlapping jobs
    to_send = []
    for job in jobs:
        if batch_backfill.job_expired(job):
            batch_backfill.finish_job(job["id"])  # 24h window up → stop retrying
            continue
        only = set(job["only_fields"]) if job.get("only_fields") else None
        # Build note-by-note and stop at the token budget — rendering prompts
        # for the WHOLE remainder (tens of thousands of fields) every poll
        # tick just to defer them again froze the UI for no gain.
        nids = job.get("nids", [])
        cursor = (col_id, job["id"])
        offset = _scan_offsets.get(cursor, 0)
        clean = _scan_clean.get(cursor, 0)
        for position in range(len(nids)):
            if scanned >= scan_cap or scanned_notes >= 500:
                break
            index = (offset + position) % len(nids)
            nid = nids[index]
            _scan_offsets[cursor] = (index + 1) % len(nids)
            scanned_notes += 1
            try:
                note = mw.col.get_note(nid)
            except Exception:
                clean += 1
                continue
            raw, _skipped = batch_backfill.build_items([note], config, only_fields=only)
            clean = 0 if raw else clean + 1
            for i in raw:
                est = batch_backfill.est_item_tokens(i, config)
                scanned += est
                key = (i["nid"], i["field"])
                if key in seen:
                    continue
                b = bucket(i)
                # Always let the first item into an empty bucket, so one
                # oversized prompt can't wedge the queue for good.
                if caps[b] <= 0 or (used[b] and used[b] + est > caps[b]):
                    continue  # bucket full — next tick picks it up
                seen.add(key)
                to_send.append(i)
                used[b] += est
        # Counted across ticks: one tick scans at most 500 notes, so a bigger
        # job never completes a lap inside a single call.
        _scan_clean[cursor] = clean
        if clean >= len(nids):
            batch_backfill.finish_job(job["id"])  # every field filled → done
            _scan_offsets.pop(cursor, None)
            _scan_clean.pop(cursor, None)
    if not to_send:
        return
    for n, item in enumerate(to_send):  # unique custom_ids across the combined submit
        item["custom_id"] = f"i{n}"

    _advance_running = True

    def task():
        return batch_backfill.submit(to_send, config, col_id=col_id)

    def on_done(fut):
        global _advance_running
        _advance_running = False
        try:
            records, errors = fut.result()
        except Exception as e:
            logger.exception("Auto-dosyłanie batchy nie powiodło się")
            tooltip(f"Batch: auto-dosyłanie nie powiodło się: {e}", period=8000)
            return
        if mw.col is not col:
            return
        if records:
            sent = sum(r["count"] for r in records)
            msg = f"Auto-dosłano {len(records)} batchy ({sent} zapytań)."
            progress = batch_backfill.record_job_progress(records)
            if progress:
                msg += f" Zadanie: {progress}."
            tooltip(msg, period=6000)
        if errors:
            # Silent swallowing hid 2h of failed submits — always surface these.
            logger.warning("Auto-dosyłanie: " + " · ".join(errors))
            if not records:
                tooltip("Batch: " + errors[0], period=8000)

    try:
        mw.taskman.run_in_background(task, on_done, uses_collection=False)
    except Exception:
        _advance_running = False
        raise


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

    # Freeze notes/models on the main thread. Workers mutate detached copies;
    # save_detached_notes() merges them with freshly read collection notes.
    try:
        notes = []
        for nid in nids:
            note, _before = detach_note(mw.col.get_note(nid))
            notes.append(note)
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return
    col = mw.col
    before = snapshot_fields(notes)
    for note in notes:
        note._toolkit_collection = col  # TTS/dictionary steps write media to this profile only

    label = workflow.get("name", "Workflow")
    cancel_flag = start_progress(label, len(notes), "Workflow")

    state = {"done": 0}
    details = []
    changed_notes: list = []
    lock = threading.Lock()

    def process_one(note):
        # Each note gets its own FieldGenerator — steps within one note stay
        # sequential, but notes run in parallel, so providers must not share
        # last_error across threads.
        gen = FieldGenerator(config)
        note_modified = False
        note_errors = []
        for step in steps:
            if cancel_flag["cancelled"]:
                break
            try:
                modified, err = execute_step(note, step, ai_generator=gen)
            except Exception as e:
                modified, err = False, str(e)
            note_modified = note_modified or modified
            if err:
                note_errors.append(err)
                logger.error(f"Workflow batch (nid={note.id}): {err}")
        with lock:
            if list(note.fields) != before[note.id]:
                changed_notes.append(note)
            if note_errors:
                details.append((note.id, "error", " · ".join(note_errors)))
            elif list(note.fields) == before[note.id]:
                details.append((note.id, "skip", "kroki nie zmieniły pól notatki"))
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
        save_detached_notes(
            browser, col, changed_notes, before, label,
            on_saved=lambda skipped: _show_run_report(
                browser, label, len(notes), state["done"], changed_notes,
                details, cancel_flag["cancelled"], skipped),
        )

    mw.taskman.run_in_background(task, on_done, uses_collection=False)


def _all_configured_target_fields(config: dict, manual_only: bool = False) -> list[str]:
    """Flattened list of distinct target field names across all note types.

    Order follows first appearance. Used by workflow field scoping; Browser
    menus use _selected_target_fields() instead.

    manual_only=False (default) → only fields WITHOUT manual_only flag (auto-eligible).
    manual_only=True → only fields WITH manual_only=True (excluded from automatic generation).
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


def _selected_target_fields(notes, config, manual_only=False, batch_api=False):
    fields = {}
    for note in notes:
        for entry, target in iter_note_fields(
            note, config, only_fields=set(note.keys()), overwrite=True
        ):
            if bool(entry.get("manual_only")) != manual_only:
                continue
            if not entry.get("provider"):
                continue
            if batch_api and entry.get("provider") not in ("openai", "anthropic", "openrouter"):
                continue
            fields.setdefault(target, None)
    return list(fields)


def _workflow_matches(notes, steps, ai_config, full_config):
    from .workflow import _resolve_ai_fields
    from ..tts.config import get_tasks
    from ..field_splitter.splitting import parse_target_fields
    for step in steps:
        module = step.get("module")
        if module == "ai" and step.get("action") == "generate":
            only = _resolve_ai_fields(step, ai_config)
            if any(list(iter_note_fields(note, ai_config, only, overwrite=True)) for note in notes):
                return True
        elif module == "dictionary" and step.get("action") == "fetch" and step.get("dicts"):
            cfg = full_config.get("dictionary", {})
            if any(cfg.get("source_field", "ang") in n and cfg.get("target_field", "audio") in n for n in notes):
                return True
        elif module == "tts" and step.get("action") == "generate":
            if any(task.get("source_field", "") in n and task.get("target_field", "") in n
                   for task in get_tasks(full_config.get("tts", {})) for n in notes):
                return True
        elif module == "field_splitter" and step.get("action") == "split":
            cfg = full_config.get("field_splitter", {})
            source = cfg.get("source_field", "przyklad")
            targets = parse_target_fields(cfg.get("target_fields", "p1, p2, p3, p4, p5"))
            if any(source in n and any(t != source and t in n for t in targets) for n in notes):
                return True
    return False


def add_to_context_menu(browser: Browser, menu, notes=None):
    from .workflow import get_workflows, get_context_menu
    from ..common import get_full_config
    cm = get_context_menu()
    if notes is None:
        notes = [mw.col.get_note(nid) for nid in browser.selected_notes()]
    if not notes:
        return
    config = get_config()
    target_fields = _selected_target_fields(notes, config)
    manual_fields = _selected_target_fields(notes, config, manual_only=True)

    full_config = get_full_config()
    for wf in get_workflows():
        steps = [s for s in wf.get("steps", []) if isinstance(s, dict)]
        if not steps or not _workflow_matches(notes, steps, config, full_config):
            continue
        wf_action = QAction(wf.get("name", "Workflow"), browser)
        wf_action.setToolTip(" → ".join(s.get("module", "?") for s in steps))
        qconnect(wf_action.triggered,
                 lambda _checked=False, w=wf: _on_workflow_browser(browser, w))
        menu.addAction(wf_action)

    def add_field_actions(submenu, fields, callback, prefix=""):
        for field_name in fields:
            action = QAction(f"{prefix}{field_name}", browser)
            qconnect(action.triggered,
                     lambda _checked=False, fn=field_name: callback(browser, fn))
            submenu.addAction(action)

    if cm.get("ai_fields", True) and target_fields:
        gen_menu = menu.addMenu("Uzupełnij puste pola AI")
        action = QAction("Wszystkie pola automatyczne", browser)
        qconnect(action.triggered, lambda: _on_generate_browser(browser))
        gen_menu.addAction(action)
        gen_menu.addSeparator()
        add_field_actions(gen_menu, target_fields, _on_generate_field_browser)

    if cm.get("ai_blocked", True) and manual_fields:
        manual_menu = menu.addMenu("Generuj pola tylko na żądanie")
        action = QAction("Uzupełnij wszystkie puste", browser)
        qconnect(action.triggered, lambda: _run_batch(
            browser, browser.selected_notes(), get_config(),
            only_fields=set(manual_fields), label="AI: pola tylko na żądanie"))
        manual_menu.addAction(action)
        manual_menu.addSeparator()
        add_field_actions(manual_menu, manual_fields, _on_generate_field_browser)

    regenerate_fields = (target_fields if cm.get("ai_fields", True) else []) + (
        manual_fields if cm.get("ai_blocked", True) else [])
    if regenerate_fields:
        regen_menu = menu.addMenu("Wygeneruj ponownie wybrane pole…")
        add_field_actions(regen_menu, dict.fromkeys(regenerate_fields), _on_regenerate_field_browser)

    api_fields = _selected_target_fields(notes, config, batch_api=True)
    api_manual = _selected_target_fields(notes, config, manual_only=True, batch_api=True)
    if cm.get("ai_fields", True) and (api_fields or (api_manual and cm.get("ai_blocked", True))):
        batch_menu = menu.addMenu("Batch API")
        if api_fields:
            action = QAction("Wyślij wszystkie puste pola automatyczne", browser)
            qconnect(action.triggered, lambda: _on_batch_submit(browser))
            batch_menu.addAction(action)
            add_field_actions(batch_menu, api_fields,
                              lambda b, f: _on_batch_submit(b, only_fields={f}))
        if api_manual and cm.get("ai_blocked", True):
            batch_menu.addSeparator()
            action = QAction("Wyślij puste pola tylko na żądanie", browser)
            qconnect(action.triggered, lambda: _on_batch_submit(browser, only_fields=set(api_manual)))
            batch_menu.addAction(action)
            add_field_actions(batch_menu, api_manual,
                              lambda b, f: _on_batch_submit(b, only_fields={f}), "Na żądanie: ")
        batch_menu.addSeparator()
        action = QAction("Pobierz i zastosuj wyniki Batch API", browser)
        qconnect(action.triggered, lambda: check_pending_batches(silent=False))
        batch_menu.addAction(action)
