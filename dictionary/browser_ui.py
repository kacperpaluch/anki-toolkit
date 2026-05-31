from aqt import mw
from aqt.utils import tooltip
from aqt.qt import *
from aqt.browser import Browser

from ..common import ADDON_NAME

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


def _run_browser_fetch(browser: Browser, dictionary_groups: list[list[str]], checkpoint_label: str):
    config = _get_config()
    note_ids = browser.selected_notes()
    if not note_ids:
        return

    if not dictionary_groups:
        return

    mw.checkpoint(checkpoint_label)

    progress = QProgressDialog("Pobieranie wymowy...", "Anuluj", 0, len(note_ids), browser)
    progress.setWindowTitle("Słownik")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)

    cancel_flag = {"cancelled": False}

    def _set_cancelled():
        cancel_flag["cancelled"] = True

    progress.canceled.connect(_set_cancelled)

    updated_count = 0
    missing_audio_count = 0
    cancelled = False

    def task():
        nonlocal updated_count, missing_audio_count, cancelled
        batch_cache: dict = {}
        for i, nid in enumerate(note_ids):
            if cancel_flag["cancelled"]:
                cancelled = True
                break

            def _update(i=i):
                progress.setLabelText(f"Pobieranie... ({i + 1}/{len(note_ids)})")
                progress.setValue(i + 1)
            mw.taskman.run_on_main(_update)

            note = mw.col.get_note(nid)
            note_modified = False
            note_missing_audio = False
            for dictionaries in dictionary_groups:
                result = process_note_group(note, config, dictionaries, batch_cache=batch_cache)
                if result.note_modified:
                    note_modified = True
                elif result.audio_requested and not result.audio_found:
                    note_missing_audio = True
            if note_modified:
                mw.col.update_note(note)
                updated_count += 1
            elif note_missing_audio:
                missing_audio_count += 1

    def on_done(fut):
        progress.close()
        try:
            fut.result()
        except Exception as e:
            tooltip(f"Błąd podczas pobierania: {e}", parent=mw, period=5000)
            return
        mw.reset()
        parts = []
        if updated_count > 0:
            parts.append(f"Zaktualizowano: {updated_count}")
        if missing_audio_count > 0:
            parts.append(f"Brak audio: {missing_audio_count}")
        if parts:
            tooltip(" · ".join(parts), parent=mw, period=4000)

    mw.taskman.run_in_background(task, on_done)


def _on_fetch_audio_browser(browser: Browser):
    config = _get_config()
    enabled_buttons = _get_enabled_button_configs(config)
    _run_browser_fetch(
        browser,
        [btn["dictionaries"] for btn in enabled_buttons],
        "Pobierz wymowę",
    )


def _on_fetch_audio_browser_for_button(browser: Browser, dictionaries: list[str], label: str):
    _run_browser_fetch(browser, [dictionaries], f"Pobierz wymowę: {label}")


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
