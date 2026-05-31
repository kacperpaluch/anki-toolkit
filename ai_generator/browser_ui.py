import time

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import *
from aqt.browser import Browser

from ._generator import get_generator, get_config


def _on_generate_browser(browser: Browser):
    config = get_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Nie zaznaczono żadnych notatek.")
        return

    batch_limit: int = max(1, config.get("batch_limit", 3))
    sleep_time: float = config.get("batch_sleep", 1.0)
    gen = get_generator()

    mw.checkpoint("AI Generate")

    progress = QProgressDialog("Generowanie przez AI...", "Anuluj", 0, len(nids), browser)
    progress.setWindowTitle("AI Generator")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)

    cancel_flag = {"cancelled": False}

    def _set_cancelled():
        cancel_flag["cancelled"] = True

    progress.canceled.connect(_set_cancelled)

    count = 0
    failures = 0
    last_error = None
    cancelled = False

    def task():
        nonlocal count, failures, last_error, cancelled
        for i, nid in enumerate(nids):
            if cancel_flag["cancelled"]:
                cancelled = True
                break

            if i > 0 and i % batch_limit == 0 and sleep_time > 0:
                time.sleep(sleep_time)

            def _update(i=i):
                progress.setLabelText(f"Przetwarzanie {i + 1}/{len(nids)}...")
                progress.setValue(i + 1)
            mw.taskman.run_on_main(_update)

            note = mw.col.get_note(nid)
            if gen.process_note(note):  # dict — truthy when non-empty
                mw.col.update_note(note)
                count += 1
            elif gen.last_error:
                failures += 1
                last_error = gen.last_error

    def on_done(fut):
        progress.close()
        try:
            fut.result()
        except Exception as e:
            tooltip(f"Błąd podczas generowania: {e}", period=5000)
            return
        mw.reset()
        parts = [f"Zaktualizowano: {count}"]
        if failures:
            parts.append(f"błędy: {failures}")
        if cancelled:
            parts.append("przerwano")
        if last_error:
            parts.append(last_error)
        tooltip(" · ".join(parts), period=8000 if last_error else 4000)

    mw.taskman.run_in_background(task, on_done)


def add_to_context_menu(browser: Browser, menu):
    action = QAction("Generuj pola", browser)
    qconnect(action.triggered, lambda: _on_generate_browser(browser))
    menu.addAction(action)
