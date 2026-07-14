"""Audio Embed — turn `[sound:...]` into inline `<audio>` players.

Source-agnostic cleanup: whatever writes `[sound:file.mp3]` into a field (TTS,
dictionary, manual entry), this rewrites it into
`<audio class="ex-audio" src="file.mp3" preload="none"></audio>` in the
configured note types and fields. The main `audio` field is left off the list,
so it keeps the classic `[sound:...]`.

Entry points:
  - Browser right-click → Anki Toolkit → „Osadź audio (sound → <audio>)"
  - Tools → Anki Toolkit → „Osadź audio w kolekcji…"
  - After sync: optional auto-scan (scan_on_sync) — catches audio added anywhere,
    including from the phone.
"""

import logging

from anki.collection import Collection, OpChanges
from aqt import mw
from aqt.browser import Browser
from aqt.operations import CollectionOp
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip

from ..common import get_module_config, plural_pl
from .logic import convert_note

log = logging.getLogger(__name__)

_DEFAULTS = {
    "note_types": ["angielski"],   # empty list = all note types
    "fields": ["przyklad", "p1", "p2", "p3", "p4", "p5"],
    "css_class": "ex-audio",
    "preload": "none",
    "scan_on_sync": True,
}
_MODULE_KEY = "audio_embed"
_SYNC_SCAN_DELAY_MS = 700  # after sibling (500) / homograph (600)


def _get_config() -> dict:
    return get_module_config(_MODULE_KEY, _DEFAULTS)


def _note_type_name(note) -> str:
    try:
        return note.note_type()["name"]
    except Exception:
        return ""


def _process(note, cfg) -> bool:
    note_types = cfg.get("note_types", _DEFAULTS["note_types"])
    if note_types and _note_type_name(note) not in note_types:
        return False
    return convert_note(
        note,
        cfg.get("fields", _DEFAULTS["fields"]),
        cfg.get("css_class", _DEFAULTS["css_class"]),
        cfg.get("preload", _DEFAULTS["preload"]),
    )


def _changes_for_ui() -> OpChanges:
    changes = OpChanges()
    changes.note = True
    changes.browser_table = True
    return changes


# ---------------------------------------------------------------------------
# Batch runner (one CollectionOp = one undo step)
# ---------------------------------------------------------------------------

def _run_batch(nids: list, silent: bool = False) -> None:
    if not nids:
        if not silent:
            tooltip("Nie wybrano notatek.", parent=mw, period=3000)
        return

    cfg = _get_config()
    counters = {"changed": 0}

    def op(col: Collection) -> OpChanges:
        changed_notes = []
        for nid in nids:
            note = col.get_note(nid)
            if _process(note, cfg):
                changed_notes.append(note)
        counters["changed"] = len(changed_notes)
        if changed_notes:
            return col.update_notes(changed_notes)
        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        n = counters["changed"]
        if silent:
            if n:
                log.info("audio_embed: osadzono audio w %d notatkach", n)
            return
        if n:
            msg = f"Osadzono audio: {n} {plural_pl(n, 'notatka', 'notatki', 'notatek')}"
        else:
            msg = "Nic do zrobienia — brak [sound:...] w skonfigurowanych polach."
        tooltip(msg, parent=mw, period=4000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


def _collection_nids(cfg) -> list:
    """Notes to scan: narrowed to configured note types (else all)."""
    note_types = cfg.get("note_types", _DEFAULTS["note_types"])
    if not note_types:
        return list(mw.col.find_notes(""))
    nids = set()
    for name in note_types:
        nids |= set(mw.col.find_notes('note:"%s"' % name))
    return list(nids)


# ---------------------------------------------------------------------------
# Browser context-menu entry
# ---------------------------------------------------------------------------

def add_to_context_menu(browser: Browser, menu) -> None:
    action = QAction("Osadź audio (sound → <audio>)", menu)
    action.triggered.connect(lambda: _run_batch(browser.selected_notes()))
    menu.addAction(action)


# ---------------------------------------------------------------------------
# Tools menu entry (whole collection with confirmation)
# ---------------------------------------------------------------------------

def _run_on_collection() -> None:
    cfg = _get_config()
    nids = _collection_nids(cfg)
    if not nids:
        tooltip("Brak notatek do przetworzenia.", parent=mw, period=3000)
        return

    fields = ", ".join(cfg.get("fields", _DEFAULTS["fields"])[:4])
    result = QMessageBox.question(
        mw,
        "Osadź audio w kolekcji",
        f"Zamienić [sound:...] na <audio> w polach: {fields}…?\n"
        f"Liczba notatek: {len(nids)}\n\n"
        f"Pole audio (główne) pozostaje bez zmian.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _run_batch(nids)


# ---------------------------------------------------------------------------
# Sync hook — catch audio added anywhere (incl. phone)
# ---------------------------------------------------------------------------

def on_sync_did_finish(*_args):
    if not _get_config().get("scan_on_sync", _DEFAULTS["scan_on_sync"]):
        return
    from aqt.qt import QTimer
    QTimer.singleShot(_SYNC_SCAN_DELAY_MS, _run_sync_scan)


def _run_sync_scan():
    cfg = _get_config()
    nids = _collection_nids(cfg)
    if nids:
        _run_batch(nids, silent=True)


def setup_menu(parent_menu=None) -> None:
    menu = parent_menu or mw.form.menuTools
    action = QAction("Osadź audio w kolekcji (sound → <audio>)...", mw)
    action.triggered.connect(_run_on_collection)
    menu.addAction(action)
