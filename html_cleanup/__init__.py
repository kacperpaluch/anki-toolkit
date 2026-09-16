"""HTML Cleanup — find/replace rules for pasted card HTML."""

import weakref

from anki.collection import Collection, OpChanges
from aqt import gui_hooks, mw
from aqt.operations import CollectionOp
from aqt.qt import QMessageBox
from aqt.utils import tooltip

from ..common import get_module_config
from .cleaning import clean_field, default_rules


_DEFAULTS = {
    "show_tooltip": True,
    "auto_run_startup": False,
}
_add_cards_ref = None


def with_rules(config: dict) -> dict:
    """Section with defaults; an explicitly empty rule list stays empty."""
    config = {**_DEFAULTS, **config}
    if "rules" not in config:
        config["rules"] = default_rules()
    return config


def get_config() -> dict:
    return with_rules(get_module_config("html_cleanup"))


def _tooltip(parent, counts: dict, rules: list) -> None:
    if not get_config().get("show_tooltip", True):
        return
    total = sum(counts.values())
    if not total:
        tooltip("Nie znaleziono elementów HTML wymagających czyszczenia.", parent=parent)
        return
    parts = [f"Wyczyszczono elementy HTML: {total}"]
    for index, count in sorted(counts.items()):
        name = rules[index].get("name") or rules[index].get("find", "")
        parts.append(f"{name}: {count}")
    tooltip("<br>".join(parts), parent=parent)


def _clean_note(note, rules: list) -> tuple[bool, dict]:
    counts: dict = {}
    updates = {}
    for name, value in note.items():
        cleaned, field_counts = clean_field(name, value, rules)
        for index, count in field_counts.items():
            counts[index] = counts.get(index, 0) + count
        if cleaned != value:
            updates[name] = cleaned
    for name, cleaned in updates.items():
        note[name] = cleaned
    return bool(updates), counts


def _on_add_cards_init(add_cards) -> None:
    global _add_cards_ref
    _add_cards_ref = weakref.ref(add_cards)


def _on_add_note(problem, note):
    if problem is not None:
        return problem
    rules = get_config()["rules"]
    try:
        changed, counts = _clean_note(note, rules)
    except ValueError as error:
        return str(error)
    if not changed:
        return None
    parent = _add_cards_ref() if _add_cards_ref is not None else mw
    _tooltip(parent, counts, rules)
    return None


def clean_collection() -> None:
    rules = get_config()["rules"]
    counters: dict = {}

    def operation(collection: Collection) -> OpChanges:
        changed_notes = []
        for note_id in collection.find_notes(""):
            note = collection.get_note(note_id)
            changed, counts = _clean_note(note, rules)
            for key, value in counts.items():
                counters[key] = counters.get(key, 0) + value
            if changed:
                changed_notes.append(note)
        return collection.update_notes(changed_notes) if changed_notes else OpChanges()

    CollectionOp(parent=mw, op=operation).success(
        lambda _changes: _tooltip(mw, counters, rules)
    ).run_in_background()


def confirm_collection_cleanup() -> None:
    result = QMessageBox.question(
        mw,
        "Wyczyść HTML w kolekcji",
        "Zastosować wszystkie włączone reguły czyszczenia do wszystkich notatek?\n\n"
        "Operację można cofnąć jednym krokiem w menu Edycja → Cofnij.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        clean_collection()


def _maybe_auto_clean(*_args) -> None:
    if get_config().get("auto_run_startup", False):
        clean_collection()


gui_hooks.add_cards_did_init.append(_on_add_cards_init)
gui_hooks.add_cards_will_add_note.append(_on_add_note)
gui_hooks.profile_did_open.append(_maybe_auto_clean)
