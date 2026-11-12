"""Browser batch actions — AI field generation and full workflow for selected notes."""

import concurrent.futures
import logging
import threading
import time

from aqt import mw
from aqt.utils import tooltip, askUser
from aqt.qt import *
from aqt.browser import Browser

from ..common import (
    start_progress, update_progress, finish_progress, load_notes, record_report, live_parent,
)
from ..common.editor_operation import save_detached_notes, snapshot_fields, detach_note
from ._generator import get_config
from .field_generator import FieldGenerator, iter_note_fields

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AI fields batch (parallel)
# ---------------------------------------------------------------------------

def _on_fields_dialog(browser: Browser, auto: list, manual: list):
    from .fields_dialog import FieldsDialog
    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return
    dialog = FieldsDialog(browser, len(nids), auto, manual)
    try:
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields, overwrite = dialog.choice()
    finally:
        dialog.deleteLater()
    if overwrite:
        _on_regenerate_browser(browser, fields)
    else:
        _run_batch(browser, nids, get_config(), only_fields=set(fields),
                   label=f"AI: {', '.join(fields)}")


def _on_regenerate_browser(browser: Browser, fields: list):
    config = get_config()
    notes = load_notes(browser.selected_notes())
    if notes is None:
        return
    eligible = [note for note in notes if list(iter_note_fields(
        note, config, only_fields=set(fields), overwrite=True))]
    if not eligible:
        tooltip("Brak pasujących notatek do ponownego generowania.")
        return
    names = ", ".join(f"„{name}”" for name in fields)
    if not askUser(
        f"Wygenerować ponownie {names} w {len(eligible)} notatkach?\n\n"
        "Istniejąca treść tych pól zostanie zastąpiona po udanym generowaniu.\n"
        "Zapis możesz cofnąć jednym krokiem w Anki.", parent=browser,
        defaultno=True,
    ):
        return
    _run_batch(browser, [n.id for n in eligible], config,
               only_fields=set(fields), label=f"Ponowne generowanie: {', '.join(fields)}",
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
                     skipped_at_save=(), retry=None):
    """retry(nids) repeats the failed notes — offered later from Diagnostyka."""
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
    failed = sorted({nid for nid, kind, _ in details if kind == "error"})
    if failed and retry:
        lines.append("Raport zostaje w Ustawienia → Diagnostyka — stamtąd ponowisz nieudane notatki.")
    if details or conflicts:
        lines.append("\nSzczegóły — identyfikatory można wyszukać w przeglądarce kart przez nid:123:")
        for nid, kind, reason in sorted(details):
            lines.append(f"nid:{nid} — {'Błąd' if kind == 'error' else 'Pominięto'}: {reason}")
        for nid in sorted(conflicts):
            lines.append(f"nid:{nid} — nie zapisano: notatka zmieniona lub usunięta podczas pracy")
    text = "\n".join(lines)
    logger.info("%s: %s", title, text)
    record_report(title, text, retry=(lambda: retry(failed)) if retry else None, failed=len(failed))
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
        notes = load_notes(nids, load=lambda nid: detach_note(mw.col.get_note(nid))[0])
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return
    if notes is None:
        return  # cancelled while loading
    col = mw.col
    before = snapshot_fields(notes)

    cancel_flag = start_progress(label, len(notes), "Generowanie AI")

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
                details, cancel_flag["cancelled"], skipped,
                retry=lambda failed: _run_batch(
                    live_parent(browser), failed, get_config(), only_fields,
                    label, overwrite=overwrite)),
        )

    mw.taskman.run_in_background(task, on_done, uses_collection=False)


# ---------------------------------------------------------------------------
# Workflow batch — runs a workflow's steps per selected note
# ---------------------------------------------------------------------------

def _on_workflow_browser(browser: Browser, workflow: dict, nids=None):
    from .workflow import execute_step

    steps = [s for s in workflow.get("steps", []) if isinstance(s, dict)]
    if not steps:
        tooltip("Brak kroków w tej sekwencji. Sprawdź ustawienia.")
        return

    nids = browser.selected_notes() if nids is None else nids
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
        notes = load_notes(nids, load=lambda nid: detach_note(mw.col.get_note(nid))[0])
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", period=5000)
        return
    if notes is None:
        return  # cancelled while loading
    col = mw.col
    before = snapshot_fields(notes)
    for note in notes:
        note._toolkit_collection = col  # TTS/dictionary steps write media to this profile only

    label = workflow.get("name", "Sekwencja")
    cancel_flag = start_progress(label, len(notes), "Sekwencja")

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
            tooltip(f"Błąd sekwencji: {e}", period=5000)
            return
        save_detached_notes(
            browser, col, changed_notes, before, label,
            on_saved=lambda skipped: _show_run_report(
                browser, label, len(notes), state["done"], changed_notes,
                details, cancel_flag["cancelled"], skipped,
                retry=lambda failed: _on_workflow_browser(
                    live_parent(browser), workflow, nids=failed)),
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


def _selected_target_fields(notes, config, manual_only=False):
    fields = {}
    for note in notes:
        for entry, target in iter_note_fields(
            note, config, only_fields=set(note.keys()), overwrite=True
        ):
            if bool(entry.get("manual_only")) != manual_only:
                continue
            if not entry.get("provider"):
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
        wf_action = QAction(wf.get("name", "Sekwencja"), browser)
        wf_action.setToolTip(" → ".join(s.get("module", "?") for s in steps))
        qconnect(wf_action.triggered,
                 lambda _checked=False, w=wf: _on_workflow_browser(browser, w))
        menu.addAction(wf_action)

    auto = target_fields if cm.get("ai_fields", True) else []
    manual = manual_fields if cm.get("ai_blocked", True) else []
    if auto or manual:
        action = QAction("Wygeneruj pola AI…", browser)
        qconnect(action.triggered, lambda: _on_fields_dialog(browser, auto, manual))
        menu.addAction(action)
