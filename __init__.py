"""Anki Toolkit — one add-on: card content, word queue and upkeep."""
from anki.utils import ids2str
from aqt import gui_hooks, mw
from aqt.qt import QAction, QTimer

from . import ai_generator, dictionary, field_splitter, tts
from . import audio_normalizer, field_hider, html_cleanup, integrations
from .common import setup_logging

setup_logging()
gui_hooks.editor_did_init_buttons.append(ai_generator.on_editor_buttons_init)
gui_hooks.editor_did_init_buttons.append(dictionary.on_editor_buttons_init)
gui_hooks.editor_did_init_buttons.append(tts.on_editor_buttons_init)
gui_hooks.profile_did_open.append(lambda: ai_generator.check_pending_batches(silent=True))
# Batche kończą się w ciągu godzin, a zadanie wygasa po 24h — bez cyklicznego
# sprawdzania wyniki czekałyby do następnego startu Anki, a reszta zadania
# nigdy by nie poszła. check_pending_batches() samo pilnuje, by dwa przebiegi
# się nie nałożyły i by nie ruszać zamkniętego profilu.
_batch_timer = QTimer(mw)
_batch_timer.setInterval(60000)
_batch_timer.timeout.connect(lambda: ai_generator.check_pending_batches(silent=True))
_batch_timer.start()


def _context(browser, menu):
    from .ai_generator.workflow import get_context_menu
    nids = browser.selected_notes()
    if not nids or mw.col is None:
        return
    # The menus depend only on note type and tags, so one note per combination
    # stands for the selection — reading 30k selected notes froze the right click.
    notes = [mw.col.get_note(nid) for nid in mw.col.db.list(
        f"select min(id) from notes where id in {ids2str(nids)} group by mid, tags")]
    sub = menu.addMenu("Anki Toolkit")
    cm = get_context_menu()
    ai_generator.add_to_context_menu(browser, sub, notes=notes)
    for key, module in (("dictionary", dictionary), ("tts", tts),
                        ("field_splitter", field_splitter)):
        if cm.get(key, True):
            module.add_to_context_menu(browser, sub, notes=notes)
    if sub.isEmpty():
        menu.removeAction(sub.menuAction())


gui_hooks.browser_will_show_context_menu.append(_context)


def _setup_menu(*_):
    from .settings_dialog import open_settings

    menu = mw.form.menuTools.addMenu("Anki Toolkit")
    def add_actions(target, entries):
        for title, callback in entries:
            action = QAction(title, target)
            # QAction passes checked(bool), never a settings page name.
            action.triggered.connect(lambda _checked=False, callback=callback: callback())
            target.addAction(action)

    add_actions(menu, (
        ("Kolejka słówek (n8n)…", integrations.open_queue),
        ("Ustawienia…", open_settings),
    ))
    menu.addSeparator()
    add_actions(menu, (
        ("Pobierz i zastosuj wyniki Batch API", lambda: ai_generator.check_pending_batches(silent=False)),
    ))
    operations = menu.addMenu("Operacje na kolekcji")
    add_actions(operations, (
        ("Rozdziel pola w kolekcji…", field_splitter.run_on_collection),
        ("Normalizuj audio (ffmpeg)…", audio_normalizer.confirm_normalization),
        ("Wyczyść HTML w kolekcji…", html_cleanup.confirm_collection_cleanup),
    ))
    # Anki otwiera edytor JSON, gdy akcja zwróci False — stąd zawsze `None`
    # (`open_settings() and None` dawało False po „Anuluj”).
    def config_action():
        open_settings()
    mw.addonManager.setConfigAction(__name__, config_action)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menu)
else:
    QTimer.singleShot(0, _setup_menu)
