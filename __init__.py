"""Anki Toolkit — one add-on: card content, word queue, study plan and upkeep."""
from aqt import gui_hooks, mw
from aqt.qt import QAction, QTimer

from . import ai_generator, dictionary, field_splitter, tts
from . import audio_normalizer, field_hider, html_cleanup, integrations, workload
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
    sub = menu.addMenu("Anki Toolkit")
    for module in (ai_generator, dictionary, tts, field_splitter):
        module.add_to_context_menu(browser, sub)


gui_hooks.browser_will_show_context_menu.append(_context)


def _setup_menu(*_):
    from .settings_dialog import open_settings

    menu = mw.form.menuTools.addMenu("Anki Toolkit")
    for entry in (
        ("Ustawienia…", open_settings),
        None,
        ("Kolejka słówek (n8n)…", integrations.open_queue),
        ("Plan nauki…", workload.show_report),
        None,
        ("Sprawdź batche AI", lambda: ai_generator.check_pending_batches(silent=False)),
        ("Rozdziel pola w kolekcji…", field_splitter.run_on_collection),
        ("Normalizuj audio (ffmpeg)…", audio_normalizer.confirm_normalization),
        ("Wyczyść HTML w kolekcji…", html_cleanup.confirm_collection_cleanup),
    ):
        if entry is None:
            menu.addSeparator()
            continue
        title, callback = entry
        action = QAction(title, menu)
        # triggered(bool) nie może trafić do open_settings(page) jako nazwa strony.
        action.triggered.connect(lambda _checked=False, callback=callback: callback())
        menu.addAction(action)
    # Anki otwiera edytor JSON, gdy akcja zwróci False — stąd `None`.
    mw.addonManager.setConfigAction(__name__, lambda: open_settings() and None)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menu)
else:
    QTimer.singleShot(0, _setup_menu)
