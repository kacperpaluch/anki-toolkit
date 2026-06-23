"""Sibling Manager — dynamic sibling suspension.

Whichever card Anki shows first becomes the active one. All other NEW
siblings are suspended until the active card matures (interval >=
threshold, default 30 days). When it matures, all suspended siblings are
released at once — Anki picks the next one to show (more random than
fixed template order).

Unlike SibPush which pre-suspends based on card order, this module is
reactive: it only acts after you answer a card.

Sync catch-up: reviews done on AnkiMobile/AnkiWeb don't trigger the
reviewer hook on desktop. After sync, a batch scan runs automatically
(sync_did_finish hook) to process all notes with NEW siblings.

Entry points:
  - Reviewer hook: manages siblings automatically after each review
  - Sync hook: batch catch-up after syncing from phone/AnkiWeb
  - Tools -> Anki Toolkit -> "Uwolnij karty zawieszone przez Sibling Manager..."
  - Tools -> Anki Toolkit -> "Przetwórz kolekcję (sync catch-up)..."
"""

import logging

from aqt import mw
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip
from anki.collection import Collection, OpChanges
from aqt.operations import CollectionOp

from ..common import get_module_config
from .logic import process_note, process_note_sync

log = logging.getLogger(__name__)

_DEFAULTS = {
    "interval": 30,
    "tag": "tk-sib-suspended",
    "ignore_tag": "tk-sib-ignored",
    "show_tooltip": True,
}
_MODULE_KEY = "sibling_manager"
_SYNC_SCAN_DELAY_MS = 500


def _get_config():
    return get_module_config(_MODULE_KEY, _DEFAULTS)


# ---------------------------------------------------------------------------
# Reviewer hook — fires after each card is answered (desktop)
# ---------------------------------------------------------------------------

def on_reviewer_did_answer_card(reviewer, card, ease):
    """After answering a card on desktop, suspend/unsuspend its siblings."""
    cfg = _get_config()
    try:
        suspended, unsuspended = process_note(
            reviewer.mw.col, card.nid, card.id,
            cfg.get("interval", _DEFAULTS["interval"]),
            cfg.get("tag", _DEFAULTS["tag"]),
            cfg.get("ignore_tag", _DEFAULTS["ignore_tag"]),
        )
        if suspended or unsuspended:
            log.info("sibling_manager: nid=%s — zawieszono %d, odwieszono %d",
                     card.nid, suspended, unsuspended)
    except Exception:
        log.exception("sibling_manager: error processing card")


# ---------------------------------------------------------------------------
# Sync hook — catch up after syncing reviews from phone/AnkiWeb
# ---------------------------------------------------------------------------

def on_sync_did_finish(*_args):
    """After sync completes, scan collection for notes needing management."""
    from aqt.qt import QTimer
    QTimer.singleShot(_SYNC_SCAN_DELAY_MS, _run_sync_scan)


def _run_sync_scan():
    """Batch-process all notes with NEW siblings or our tag."""
    cfg = _get_config()
    threshold = cfg.get("interval", _DEFAULTS["interval"])
    tag = cfg.get("tag", _DEFAULTS["tag"])
    ignore_tag = cfg.get("ignore_tag", _DEFAULTS["ignore_tag"])
    show_tooltip = cfg.get("show_tooltip", _DEFAULTS["show_tooltip"])

    counters = {"suspended": 0, "unsuspended": 0, "notes": 0}

    def op(col: Collection) -> OpChanges:
        nids1 = set(col.find_notes("is:new"))
        nids2 = set(col.find_notes(f"tag:{tag}"))
        candidates = nids1 | nids2
        if not candidates:
            return OpChanges()

        db = col.db
        if db is None:
            return OpChanges()

        # Keep only notes with >1 card (single-card notes have no siblings)
        nid_list = ",".join(str(n) for n in candidates)
        multi_nids = db.list(
            f"SELECT nid FROM cards WHERE nid IN ({nid_list}) "
            f"GROUP BY nid HAVING COUNT(*) > 1"
        )

        for nid in multi_nids:
            try:
                s, u = process_note_sync(col, nid, threshold, tag, ignore_tag)
                counters["suspended"] += s
                counters["unsuspended"] += u
                if s or u:
                    counters["notes"] += 1
            except Exception:
                log.exception("sibling_manager: error in sync scan for nid=%s", nid)

        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        s, u = counters["suspended"], counters["unsuspended"]
        log.info(
            "sibling_manager: sync scan complete — zawieszono %d, odwieszono %d (notatek: %d)",
            s, u, counters["notes"],
        )
        if show_tooltip and (s or u):
            parts = []
            if s:
                parts.append(f"zawieszono {s}")
            if u:
                parts.append(f"odwieszono {u}")
            tooltip("Sibling Manager: " + ", ".join(parts), parent=mw, period=4000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


# ---------------------------------------------------------------------------
# Tools menu — unsuspend all (escape hatch / reset)
# ---------------------------------------------------------------------------

def _unsuspend_all():
    cfg = _get_config()
    tag = cfg.get("tag", _DEFAULTS["tag"])

    def op(col: Collection) -> OpChanges:
        card_ids = list(col.find_cards(f"tag:{tag} is:suspended"))
        nids = list(col.find_notes(f"tag:{tag}"))
        if not card_ids and not nids:
            return OpChanges()
        if card_ids:
            col.sched.unsuspend_cards(card_ids)
        for nid in nids:
            note = col.get_note(nid)
            note.remove_tag(tag)
            col.update_note(note)
        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        tooltip("Sibling Manager: uwolniono wszystkie karty", parent=mw, period=3000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


def _confirm_unsuspend_all():
    result = QMessageBox.question(
        mw, "Sibling Manager",
        "Uwolnić wszystkie karty zawieszone przez ten moduł?\n"
        "Tagi zostaną usunięte z notatek.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _unsuspend_all()


# ---------------------------------------------------------------------------
# Tools menu — manual sync catch-up
# ---------------------------------------------------------------------------

def _confirm_sync_scan():
    result = QMessageBox.question(
        mw, "Sibling Manager",
        "Przetworzyć całą kolekcję?\n"
        "Przydatne po synchronizacji lub gdy siblingi nie zostały "
        "zawieszone/odwiesione automatycznie.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _run_sync_scan()


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools
    action1 = QAction("Uwolnij karty zawieszone przez Sibling Manager...", mw)
    action1.triggered.connect(_confirm_unsuspend_all)
    menu.addAction(action1)

    action2 = QAction("Przetwórz kolekcję (sync catch-up)...", mw)
    action2.triggered.connect(_confirm_sync_scan)
    menu.addAction(action2)
