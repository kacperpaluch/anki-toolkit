"""Anki Toolkit: HTML Cleanup — standalone cleanup of pasted card HTML."""

import weakref

from anki.collection import Collection, OpChanges
from aqt import gui_hooks, mw
from aqt.operations import CollectionOp
from aqt.qt import QAction, QMessageBox, QTimer
from aqt.utils import tooltip

from .cleaning import clean_field


_DEFAULTS = {
    "show_tooltip": True,
    "auto_run_startup": False,
    "skip_field": "ang",
}
_add_cards_ref = None


def _addon_name() -> str:
    return __name__.split(".")[0]


def get_config() -> dict:
    return {**_DEFAULTS, **(mw.addonManager.getConfig(_addon_name()) or {})}


def save_config(changes: dict) -> None:
    config = mw.addonManager.getConfig(_addon_name()) or {}
    config.update(changes)
    mw.addonManager.writeConfig(_addon_name(), config)


def _tooltip(parent, counts: dict) -> None:
    if not get_config().get("show_tooltip", True):
        return
    total = sum(counts.values())
    if not total:
        tooltip("Nie znaleziono elementów HTML wymagających czyszczenia.", parent=parent)
        return
    parts = [f"Wyczyszczono elementy HTML: {total}"]
    if counts["nbsp"]:
        parts.append(f"&nbsp; → spacja: {counts['nbsp']}")
    if counts["div"]:
        parts.append(f"Usunięte tagi <div>: {counts['div']}")
    if counts["div_br"]:
        parts.append(f"Bloki <div> → <br>: {counts['div_br']}")
    tooltip("<br>".join(parts), parent=parent)


def _clean_note(note, skip_field: str) -> tuple[bool, dict]:
    counts = {"nbsp": 0, "div": 0, "div_br": 0}
    changed = False
    for name, value in note.items():
        cleaned, nbsp_count, div_count, div_br_count = clean_field(name, value, skip_field)
        counts["nbsp"] += nbsp_count
        counts["div"] += div_count
        counts["div_br"] += div_br_count
        if cleaned != value:
            note[name] = cleaned
            changed = True
    return changed, counts


def _on_add_cards_init(add_cards) -> None:
    global _add_cards_ref
    _add_cards_ref = weakref.ref(add_cards)


def _on_add_note(note) -> None:
    config = get_config()
    changed, counts = _clean_note(note, config.get("skip_field", "ang"))
    if not changed:
        return
    mw.col.update_note(note)
    parent = _add_cards_ref() if _add_cards_ref is not None else mw
    _tooltip(parent, counts)


def clean_collection() -> None:
    config = get_config()
    counters = {"nbsp": 0, "div": 0, "div_br": 0}
    skip_field = config.get("skip_field", "ang")

    def operation(collection: Collection) -> OpChanges:
        changed_notes = []
        for note_id in collection.find_notes(""):
            note = collection.get_note(note_id)
            changed, counts = _clean_note(note, skip_field)
            for key, value in counts.items():
                counters[key] += value
            if changed:
                changed_notes.append(note)
        return collection.update_notes(changed_notes) if changed_notes else OpChanges()

    CollectionOp(parent=mw, op=operation).success(lambda _changes: _tooltip(mw, counters)).run_in_background()


def _confirm_collection_cleanup() -> None:
    result = QMessageBox.question(
        mw,
        "Wyczyść HTML w kolekcji",
        "Wyczyścić &nbsp; i tagi <div> we wszystkich notatkach?\n\n"
        "Operację można cofnąć jednym krokiem w menu Edycja → Cofnij.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        clean_collection()


def _maybe_auto_clean(*_args) -> None:
    if get_config().get("auto_run_startup", False):
        clean_collection()


def _setup_menu(*_args) -> None:
    from .settings import open_settings

    menu = mw.form.menuTools.addMenu("Anki Toolkit: HTML Cleanup")
    configure = QAction("Ustawienia…", menu)
    configure.triggered.connect(open_settings)
    menu.addAction(configure)
    menu.addSeparator()
    cleanup = QAction("Wyczyść HTML w kolekcji…", menu)
    cleanup.triggered.connect(_confirm_collection_cleanup)
    menu.addAction(cleanup)


gui_hooks.add_cards_did_init.append(_on_add_cards_init)
gui_hooks.add_cards_did_add_note.append(_on_add_note)
gui_hooks.profile_did_open.append(_maybe_auto_clean)
if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menu)
else:
    QTimer.singleShot(0, _setup_menu)
