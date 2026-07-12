"""Sentence Unlocker — progressive gap-fill card gating.

Your ``angielski`` note type has extra "fill the gap" templates
(``p1-nauka``/``p2-nauka``/``p3-nauka``) that only generate when the matching
``pX-tak`` field is non-empty. This module fills those markers automatically,
staggered by maturity:

  - both recognition cards (``ang-pol`` + ``pol-ang``) mature → unlock sentence 1
  - sentence 1's card matures → unlock sentence 2
  - sentence 2's card matures → unlock sentence 3

One-way: a marker is never removed (that would delete the generated card and
its history). "Mature" = card interval >= threshold (default 21 days).

Entry points:
  - Reviewer hook: unlocks the next sentence after each review (desktop)
  - Sync hook: batch catch-up after syncing from phone/AnkiWeb
  - Tools -> Anki Toolkit -> "Sentence Unlocker: przeskanuj kolekcję..."
"""

import logging

from aqt import mw
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip
from anki.collection import Collection, OpChanges
from aqt.operations import CollectionOp

from ..common import get_module_config
from .logic import process_note

log = logging.getLogger(__name__)

_MODULE_KEY = "sentence_unlocker"
_DEFAULTS = {
    "model": "angielski",
    "threshold": 21,
    "marker": "tak",
    "main_templates": ["ang-pol", "pol-ang"],
    "chain": [
        {"nauka_field": "p1-nauka", "tak_field": "p1-tak"},
        {"nauka_field": "p2-nauka", "tak_field": "p2-tak"},
        {"nauka_field": "p3-nauka", "tak_field": "p3-tak"},
    ],
    "ignore_tag": "tk-unlock-ignored",
    "done_tag": "tk-unlock-done",
    "show_tooltip": True,
}
_SYNC_SCAN_DELAY_MS = 500


def _get_config():
    return get_module_config(_MODULE_KEY, _DEFAULTS)


def _logic_args(cfg):
    return dict(
        threshold=cfg.get("threshold", _DEFAULTS["threshold"]),
        main_templates=cfg.get("main_templates", _DEFAULTS["main_templates"]),
        chain=cfg.get("chain", _DEFAULTS["chain"]),
        marker=cfg.get("marker", _DEFAULTS["marker"]),
        ignore_tag=cfg.get("ignore_tag", _DEFAULTS["ignore_tag"]),
        done_tag=cfg.get("done_tag", _DEFAULTS["done_tag"]),
    )


def _changes_for_ui() -> OpChanges:
    """OpChanges telling Anki to refresh after fields/tags changed (card regen)."""
    changes = OpChanges()
    changes.card = True
    changes.note = True
    changes.study_queues = True
    return changes


# ---------------------------------------------------------------------------
# Reviewer hook — fires after each card is answered (desktop)
# ---------------------------------------------------------------------------

def on_reviewer_did_answer_card(reviewer, card, ease):
    cfg = _get_config()
    col = reviewer.mw.col
    try:
        note = col.get_note(card.nid)
        if col.models.get(note.mid)["name"] != cfg.get("model", _DEFAULTS["model"]):
            return
        unlocked = process_note(col, card.nid, **_logic_args(cfg))
        if unlocked:
            log.info("sentence_unlocker: nid=%s — odblokowano zdanie", card.nid)
    except Exception:
        log.exception("sentence_unlocker: error processing card")


# ---------------------------------------------------------------------------
# Sync hook — catch up after syncing reviews from phone/AnkiWeb
# ---------------------------------------------------------------------------

def on_sync_did_finish(*_args):
    from aqt.qt import QTimer
    QTimer.singleShot(_SYNC_SCAN_DELAY_MS, _run_scan)


def _run_scan():
    """Batch-process notes of the target model that aren't done/ignored."""
    cfg = _get_config()
    model = cfg.get("model", _DEFAULTS["model"])
    args = _logic_args(cfg)
    done_tag = args["done_tag"]
    ignore_tag = args["ignore_tag"]
    show_tooltip = cfg.get("show_tooltip", _DEFAULTS["show_tooltip"])

    counters = {"unlocked": 0, "notes": 0}

    def op(col: Collection) -> OpChanges:
        query = f'"note:{model}"'
        if done_tag:
            query += f" -tag:{done_tag}"
        if ignore_tag:
            query += f" -tag:{ignore_tag}"
        nids = col.find_notes(query)
        if not nids:
            return OpChanges()

        for nid in nids:
            try:
                u = process_note(col, nid, **args)
                counters["unlocked"] += u
                if u:
                    counters["notes"] += 1
            except Exception:
                log.exception("sentence_unlocker: error in scan for nid=%s", nid)

        if counters["unlocked"]:
            return _changes_for_ui()
        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        u = counters["unlocked"]
        log.info("sentence_unlocker: scan complete — odblokowano %d zdań (notatek: %d)",
                 u, counters["notes"])
        if show_tooltip and u:
            tooltip(f"Sentence Unlocker: odblokowano {u} zdań", parent=mw, period=4000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


# ---------------------------------------------------------------------------
# Tools menu — manual batch scan
# ---------------------------------------------------------------------------

def _confirm_scan():
    result = QMessageBox.question(
        mw, "Sentence Unlocker",
        "Przeskanować kolekcję i odblokować dojrzałe zdania?\n"
        "Przydatne po synchronizacji lub przy pierwszym uruchomieniu.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _run_scan()


def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools
    action = QAction("Sentence Unlocker: przeskanuj kolekcję (odblokuj zdania)...", mw)
    action.triggered.connect(_confirm_scan)
    menu.addAction(action)
