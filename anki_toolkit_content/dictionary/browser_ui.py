from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import tooltip
from aqt.qt import *
from aqt.browser import Browser

from ..common import ADDON_NAME, start_progress, update_progress, finish_progress

from .service import process_note_group


def _get_config() -> dict:
    full_config = mw.addonManager.getConfig(ADDON_NAME)
    return full_config.get("dictionary", {})


def _get_enabled_button_configs(config: dict) -> list[dict]:
    return [
        btn
        for btn in config.get("buttons", [])
        if btn.get("enabled", False) and btn.get("dictionaries")
    ]


def _run_browser_fetch(browser: Browser, dictionary_groups: list[list[str]]):
    config = _get_config()
    note_ids = browser.selected_notes()
    if not note_ids:
        return

    if not dictionary_groups:
        return

    # Notatki wczytywane na głównym wątku — kolekcja Anki jest jednowątkowa,
    # wątek roboczy tylko mutuje je w pamięci (ten sam wzorzec co batch AI/TTS).
    try:
        notes = [mw.col.get_note(nid) for nid in note_ids]
    except Exception as e:
        tooltip(f"Błąd wczytywania notatek: {e}", parent=mw, period=5000)
        return

    cancel_flag = start_progress("Pobieranie wymowy", len(notes), "Słownik")

    missing_audio_count = 0
    changed_notes: list = []

    def task():
        nonlocal missing_audio_count
        batch_cache: dict = {}
        for i, note in enumerate(notes):
            if cancel_flag["cancelled"]:
                break

            update_progress(cancel_flag, "Pobieranie", i + 1, len(notes))

            note_modified = False
            note_missing_audio = False
            for dictionaries in dictionary_groups:
                result = process_note_group(note, config, dictionaries, batch_cache=batch_cache)
                if result.note_modified:
                    note_modified = True
                elif result.audio_requested and not result.audio_found:
                    note_missing_audio = True
            if note_modified:
                changed_notes.append(note)
            elif note_missing_audio:
                missing_audio_count += 1

    def on_done(fut):
        finish_progress()
        try:
            fut.result()
        except Exception as e:
            tooltip(f"Błąd podczas pobierania: {e}", parent=mw, period=5000)
            return
        parts = []
        if changed_notes:
            parts.append(f"Zaktualizowano: {len(changed_notes)}")
        if missing_audio_count > 0:
            parts.append(f"Brak audio: {missing_audio_count}")
        if cancel_flag["cancelled"]:
            parts.append("przerwano")
        summary = " · ".join(parts) if parts else "Brak zmian."

        if not changed_notes:
            tooltip(summary, parent=mw, period=4000)
            return
        # One undoable operation for the whole batch (collection write on
        # the main thread, UI refresh handled by CollectionOp).
        CollectionOp(
            parent=browser,
            op=lambda col: col.update_notes(changed_notes),
        ).success(
            lambda _changes: tooltip(summary, parent=mw, period=4000)
        ).run_in_background()

    mw.taskman.run_in_background(task, on_done)


def _on_fetch_audio_browser(browser: Browser):
    config = _get_config()
    enabled_buttons = _get_enabled_button_configs(config)
    _run_browser_fetch(
        browser,
        [btn["dictionaries"] for btn in enabled_buttons],
    )


def _on_fetch_audio_browser_for_button(browser: Browser, dictionaries: list[str], label: str):
    _run_browser_fetch(browser, [dictionaries])


def add_to_context_menu(browser: Browser, menu):
    fetch_menu = menu.addMenu("Pobierz wymowę")

    action = QAction("Wszystkie włączone słowniki", browser)
    action.triggered.connect(lambda: _on_fetch_audio_browser(browser))
    fetch_menu.addAction(action)
    fetch_menu.addSeparator()

    config = _get_config()
    for btn_config in _get_enabled_button_configs(config):
        label = btn_config.get("label", "Audio")
        dictionaries = btn_config["dictionaries"]
        source_action = QAction(f"Pobierz z {label}", browser)
        source_action.triggered.connect(
            lambda _checked=False, d=dictionaries, lbl=label: _on_fetch_audio_browser_for_button(browser, d, lbl)
        )
        fetch_menu.addAction(source_action)
