"""Field Splitter — copy parts of a field into separate target fields.

Splits a source field (e.g. ``przyklad``) by a separator (e.g. ``<br><br>``)
and writes each part to a target field (``p1``, ``p2``, ``p3``…).  The source
field is never modified — this is a copy, not a move.

Entry points:
  - Browser right-click → Anki Toolkit → „Rozdziel pole …"
  - Tools → Anki Toolkit → „Rozdziel pola w kolekcji…"
"""

from anki.collection import Collection, OpChanges
from aqt import mw
from aqt.browser import Browser
from aqt.operations import CollectionOp
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip

from ..common import get_module_config, plural_pl

from .splitting import split_field_value, parse_target_fields


_DEFAULTS = {
    "source_field": "przyklad",
    "separator": "<br><br>",
    "target_fields": "p1, p2, p3, p4, p5",
    "overwrite": True,
}

_MODULE_KEY = "field_splitter"


def _get_config() -> dict:
    return get_module_config(_MODULE_KEY, _DEFAULTS)


# ---------------------------------------------------------------------------
# Core note processing (shared by browser batch and whole-collection run)
# ---------------------------------------------------------------------------

def _process_note(note, cfg: dict) -> bool:
    """Split source field into targets on *note*. Returns True if changed."""
    source = cfg.get("source_field", _DEFAULTS["source_field"])
    separator = cfg.get("separator", _DEFAULTS["separator"])
    targets = parse_target_fields(cfg.get("target_fields", ""))

    field_names = set(note.keys())
    if source not in field_names:
        return False

    value = note[source] or ""
    mapping = split_field_value(value, separator, targets)
    if not mapping:
        return False

    overwrite = cfg.get("overwrite", _DEFAULTS["overwrite"])
    changed = False
    for tf, part in mapping.items():
        if tf not in field_names:
            continue
        current = note[tf] or ""
        if not overwrite and current.strip():
            continue
        if current != part:
            note[tf] = part
            changed = True
    return changed


# ---------------------------------------------------------------------------
# Batch runner (one CollectionOp = one undo step)
# ---------------------------------------------------------------------------

def _run_batch(nids: list) -> None:
    if not nids:
        tooltip("Nie wybrano notatek.", parent=mw, period=3000)
        return

    cfg = _get_config()
    targets = parse_target_fields(cfg.get("target_fields", ""))
    if not targets:
        tooltip("Brak pól docelowych w konfiguracji.", parent=mw, period=4000)
        return

    counters = {"changed": 0}

    def op(col: Collection) -> OpChanges:
        changed_notes = []
        for nid in nids:
            note = col.get_note(nid)
            if _process_note(note, cfg):
                changed_notes.append(note)
        counters["changed"] = len(changed_notes)
        if changed_notes:
            return col.update_notes(changed_notes)
        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        n = counters["changed"]
        if n:
            msg = f"Rozdzielono pola: {n} {plural_pl(n, 'notatka', 'notatki', 'notatek')}"
        else:
            msg = "Nic do zrobienia — pola docelowe już zawierają właściwą treść."
        tooltip(msg, parent=mw, period=4000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


# ---------------------------------------------------------------------------
# Browser context-menu entry
# ---------------------------------------------------------------------------

def add_to_context_menu(browser: Browser, menu) -> None:
    cfg = _get_config()
    source = cfg.get("source_field", _DEFAULTS["source_field"])
    targets = parse_target_fields(cfg.get("target_fields", ""))
    label_targets = ", ".join(targets[:3])
    if len(targets) > 3:
        label_targets += "…"
    label = f"Rozdziel pole {source} → {label_targets}" if targets else "Rozdziel pole (brak konfiguracji)"

    action = QAction(label, menu)
    action.triggered.connect(lambda: _run_batch(browser.selected_notes()))
    menu.addAction(action)


# ---------------------------------------------------------------------------
# Tools menu entry (whole collection with confirmation)
# ---------------------------------------------------------------------------

def _run_on_collection() -> None:
    cfg = _get_config()
    source = cfg.get("source_field", _DEFAULTS["source_field"])
    targets = parse_target_fields(cfg.get("target_fields", ""))
    if not targets:
        tooltip("Brak pól docelowych w konfiguracji.", parent=mw, period=4000)
        return

    nids = mw.col.find_notes("")
    if not nids:
        tooltip("Brak notatek w kolekcji.", parent=mw, period=3000)
        return

    label_targets = ", ".join(targets[:3])
    if len(targets) > 3:
        label_targets += "…"
    result = QMessageBox.question(
        mw,
        "Rozdziel pola w kolekcji",
        f"Skopiować zawartość pola '{source}' do pól: {label_targets}?\n"
        f"Liczba notatek: {len(nids)}\n\n"
        f"Pole źródłowe nie zostanie zmienione.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _run_batch(nids)


def setup_menu(parent_menu=None) -> None:
    menu = parent_menu or mw.form.menuTools
    action = QAction("Rozdziel pola w kolekcji...", mw)
    action.triggered.connect(_run_on_collection)
    menu.addAction(action)
