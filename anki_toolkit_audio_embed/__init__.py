"""Anki Toolkit: Audio Embed — standalone sound-tag conversion add-on."""

import logging

from anki.collection import Collection, OpChanges
from aqt import gui_hooks, mw
from aqt.browser import Browser
from aqt.operations import CollectionOp
from aqt.qt import QAction, QMessageBox, QTimer
from aqt.utils import tooltip

from .logic import convert_note


log = logging.getLogger(__name__)
_DEFAULTS = {
    "note_types": ["angielski"],
    "fields": ["przyklad", "p1", "p2", "p3", "p4", "p5"],
    "css_class": "ex-audio",
    "preload": "none",
    "scan_on_sync": True,
}
_SYNC_SCAN_DELAY_MS = 700


def _addon_name() -> str:
    return __name__.split(".")[0]


def get_config() -> dict:
    return {**_DEFAULTS, **(mw.addonManager.getConfig(_addon_name()) or {})}


def save_config(changes: dict) -> None:
    config = mw.addonManager.getConfig(_addon_name()) or {}
    config.update(changes)
    mw.addonManager.writeConfig(_addon_name(), config)


def _note_type_name(note) -> str:
    try:
        return note.note_type()["name"]
    except Exception:
        return ""


def _process(note, config: dict) -> bool:
    note_types = config.get("note_types", _DEFAULTS["note_types"])
    if note_types and _note_type_name(note) not in note_types:
        return False
    return convert_note(
        note,
        config.get("fields", _DEFAULTS["fields"]),
        config.get("css_class", _DEFAULTS["css_class"]),
        config.get("preload", _DEFAULTS["preload"]),
    )


def _plural_notes(number: int) -> str:
    if number == 1:
        return "notatka"
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return "notatki"
    return "notatek"


def _run_batch(note_ids: list[int], silent: bool = False) -> None:
    if not note_ids:
        if not silent:
            tooltip("Nie wybrano notatek.", parent=mw, period=3000)
        return
    config = get_config()
    counters = {"changed": 0}

    def operation(collection: Collection) -> OpChanges:
        changed_notes = []
        for note_id in note_ids:
            note = collection.get_note(note_id)
            if _process(note, config):
                changed_notes.append(note)
        counters["changed"] = len(changed_notes)
        return collection.update_notes(changed_notes) if changed_notes else OpChanges()

    def success(_changes: OpChanges) -> None:
        count = counters["changed"]
        if silent:
            if count:
                log.info("audio_embed: osadzono audio w %d notatkach", count)
            return
        message = (
            f"Osadzono audio: {count} {_plural_notes(count)}"
            if count else "Nic do zrobienia — brak [sound:...] w skonfigurowanych polach."
        )
        tooltip(message, parent=mw, period=4000)

    CollectionOp(parent=mw, op=operation).success(success).run_in_background()


def _collection_note_ids(config: dict) -> list[int]:
    note_types = config.get("note_types", _DEFAULTS["note_types"])
    if not note_types:
        return list(mw.col.find_notes(""))
    note_ids = set()
    for name in note_types:
        escaped = name.replace('"', '\\"')
        note_ids.update(mw.col.find_notes(f'note:"{escaped}"'))
    return list(note_ids)


def _run_on_collection() -> None:
    config = get_config()
    note_ids = _collection_note_ids(config)
    if not note_ids:
        tooltip("Brak notatek do przetworzenia.", parent=mw, period=3000)
        return
    result = QMessageBox.question(
        mw,
        "Osadź audio w kolekcji",
        f"Zamienić [sound:...] na <audio> w {len(note_ids)} notatkach?\n\n"
        "Główne pole audio pozostaje bez zmian, jeśli nie jest na liście pól.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _run_batch(note_ids)


def _on_browser_context_menu(browser: Browser, menu) -> None:
    action = QAction("Anki Toolkit: Osadź audio (sound → <audio>)", menu)
    action.triggered.connect(lambda: _run_batch(browser.selected_notes()))
    menu.addAction(action)


def _on_sync_finished(*_args) -> None:
    if get_config().get("scan_on_sync", _DEFAULTS["scan_on_sync"]):
        QTimer.singleShot(_SYNC_SCAN_DELAY_MS, _run_sync_scan)


def _run_sync_scan() -> None:
    note_ids = _collection_note_ids(get_config())
    if note_ids:
        _run_batch(note_ids, silent=True)


def _setup_menu(*_args) -> None:
    from .settings import open_settings

    menu = mw.form.menuTools.addMenu("Anki Toolkit: Audio Embed")
    configure = QAction("Ustawienia…", menu)
    configure.triggered.connect(open_settings)
    menu.addAction(configure)
    menu.addSeparator()
    run = QAction("Osadź audio w kolekcji…", menu)
    run.triggered.connect(_run_on_collection)
    menu.addAction(run)


gui_hooks.browser_will_show_context_menu.append(_on_browser_context_menu)
gui_hooks.sync_did_finish.append(_on_sync_finished)
if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menu)
else:
    QTimer.singleShot(0, _setup_menu)
