"""Homograph Manager — stagger same-word notes with different meanings.

Separate notes that share the same word in the key field (default ``ang``) —
e.g. several "assault" notes with different meanings — interfere when studied
together. This module keeps exactly ONE meaning active at a time: the others'
NEW cards stay suspended until the active meaning matures, then one next
meaning is released.

Orthogonal to Sibling Manager: that one staggers the two sides of a single
note; this one staggers whole meanings. Both share the same hooks and menu
style.

Entry points:
  - Reviewer hook: manages homographs after each review (desktop)
  - Sync hook: batch catch-up after syncing from phone/AnkiWeb
  - Tools -> Anki Toolkit -> "Uwolnij karty zawieszone przez Homograph Manager..."
  - Tools -> Anki Toolkit -> "Homograph Manager: przeskanuj całą kolekcję..."
"""

import logging

from aqt import mw
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip
from anki.collection import Collection, OpChanges
from aqt.operations import CollectionOp

from ..common import get_module_config
from .logic import process_reactive, process_group_sync, note_key, group_nids

log = logging.getLogger(__name__)

_DEFAULTS = {
    "interval": 30,
    "field": "ang",
    "tag": "tk-homograph-suspended",
    "ignore_tag": "tk-homograph-ignored",
    "show_tooltip": True,
}
_MODULE_KEY = "homograph_manager"
_SYNC_SCAN_DELAY_MS = 600  # after sibling_manager's 500ms, so it runs on settled state


def _get_config():
    return get_module_config(_MODULE_KEY, _DEFAULTS)


def _changes_for_ui() -> OpChanges:
    changes = OpChanges()
    changes.card = True
    changes.note = True
    changes.study_queues = True
    return changes


# ---------------------------------------------------------------------------
# Reviewer hook
# ---------------------------------------------------------------------------

def on_reviewer_did_answer_card(reviewer, card, ease):
    cfg = _get_config()
    try:
        suspended, unsuspended = process_reactive(
            reviewer.mw.col, card.nid, card.id,
            cfg.get("interval", _DEFAULTS["interval"]),
            cfg.get("tag", _DEFAULTS["tag"]),
            cfg.get("field", _DEFAULTS["field"]),
            cfg.get("ignore_tag", _DEFAULTS["ignore_tag"]),
        )
        if suspended or unsuspended:
            log.info("homograph_manager: nid=%s — zawieszono %d, odwieszono %d",
                     card.nid, suspended, unsuspended)
    except Exception:
        log.exception("homograph_manager: error processing card")


# ---------------------------------------------------------------------------
# Sync hook — batch catch-up
# ---------------------------------------------------------------------------

def on_sync_did_finish(*_args):
    from aqt.qt import QTimer
    QTimer.singleShot(_SYNC_SCAN_DELAY_MS, _run_sync_scan)


def _run_sync_scan():
    cfg = _get_config()
    threshold = cfg.get("interval", _DEFAULTS["interval"])
    field = cfg.get("field", _DEFAULTS["field"])
    tag = cfg.get("tag", _DEFAULTS["tag"])
    ignore_tag = cfg.get("ignore_tag", _DEFAULTS["ignore_tag"])
    show_tooltip = cfg.get("show_tooltip", _DEFAULTS["show_tooltip"])

    counters = {"suspended": 0, "unsuspended": 0, "groups": 0}

    def op(col: Collection) -> OpChanges:
        candidates = set(col.find_notes("is:new")) | set(col.find_notes(f"tag:{tag}"))
        if not candidates:
            return OpChanges()

        seen_keys = set()
        for nid in candidates:
            key = note_key(col.get_note(nid), field)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            group = group_nids(col, field, key)
            if len(group) <= 1:
                continue
            try:
                s, u = process_group_sync(col, group, threshold, tag, field, ignore_tag)
                counters["suspended"] += s
                counters["unsuspended"] += u
                if s or u:
                    counters["groups"] += 1
            except Exception:
                log.exception("homograph_manager: error in sync scan for key=%s", key)

        if counters["suspended"] or counters["unsuspended"]:
            return _changes_for_ui()
        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        s, u = counters["suspended"], counters["unsuspended"]
        log.info(
            "homograph_manager: sync scan complete — zawieszono %d, odwieszono %d (grup: %d)",
            s, u, counters["groups"],
        )
        if show_tooltip and (s or u):
            parts = []
            if s:
                parts.append(f"zawieszono {s}")
            if u:
                parts.append(f"odwieszono {u}")
            tooltip("Homograph Manager: " + ", ".join(parts), parent=mw, period=4000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


# ---------------------------------------------------------------------------
# Tools menu — unsuspend all (escape hatch)
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
        return _changes_for_ui()

    def on_success(_changes: OpChanges) -> None:
        tooltip("Homograph Manager: uwolniono wszystkie karty", parent=mw, period=3000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


def _confirm_unsuspend_all():
    result = QMessageBox.question(
        mw, "Homograph Manager",
        "Uwolnić wszystkie karty zawieszone przez ten moduł?\n"
        "Tagi zostaną usunięte z notatek.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _unsuspend_all()


def _confirm_sync_scan():
    result = QMessageBox.question(
        mw, "Homograph Manager",
        "Przetworzyć całą kolekcję?\n"
        "Przydatne po synchronizacji lub gdy homografy nie zostały "
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
    action1 = QAction("Uwolnij karty zawieszone przez Homograph Manager...", mw)
    action1.triggered.connect(_confirm_unsuspend_all)
    menu.addAction(action1)

    action2 = QAction("Homograph Manager: przeskanuj całą kolekcję (zawieś/uwolnij homografy)...", mw)
    action2.triggered.connect(_confirm_sync_scan)
    menu.addAction(action2)
