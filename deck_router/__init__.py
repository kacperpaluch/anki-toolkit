"""Deck Router — kieruje karty do talii wg tagu (+ opcjonalnie szablonu).

Natywny Deck Override w Anki działa tylko per-szablon. Ten moduł dokłada
kierowanie per-tag: gdy notatka ma skonfigurowany tag, pasujące karty są
przenoszone do talii z reguły — nadpisując natywny override dla tych kart.

Reguły w config.json → "deck_router". Każda reguła:
    {"tag": "abc123", "template": "pol-ang", "deck": "Angielski::Osobne"}
`template` pominięty/pusty/"*" = wszystkie karty notatki.

Wyzwalacze:
  - okno "Dodaj": add_cards_did_add_note (podpięte w głównym __init__)
  - AI batch/workflow w przeglądarce: route_after_edit() z ai_generator
  - Narzędzia → Anki Toolkit → "Deck Router: uporządkuj istniejące karty..."

Notatki bez pasującej reguły nie są ruszane (natywny override zostaje).
"""

import logging

from aqt import mw
from aqt.qt import QAction, QMessageBox
from aqt.utils import tooltip
from anki.collection import Collection, OpChanges
from aqt.operations import CollectionOp

from ..common import ADDON_NAME, get_module_config
from .logic import match_deck

log = logging.getLogger(__name__)

_MODULE_KEY = "deck_router"
_DEFAULTS = {"rules": []}


def _get_config():
    return get_module_config(_MODULE_KEY, _DEFAULTS)


def _rules():
    rules = _get_config().get("rules", [])
    return [r for r in rules if isinstance(r, dict) and r.get("tag") and r.get("deck")]


def _module_enabled() -> bool:
    cfg = mw.addonManager.getConfig(ADDON_NAME) or {}
    return cfg.get("modules", {}).get(_MODULE_KEY, True)


def _ui_changes() -> OpChanges:
    ch = OpChanges()
    ch.card = True
    ch.study_queues = True
    return ch


def _apply(col: Collection, note_ids, rules) -> int:
    """Move each card of every note to its rule's deck. Returns cards moved.

    Decks are created on demand. Cards already in the target deck are skipped.
    """
    deck_ids: dict[str, int] = {}
    to_move: dict[int, list[int]] = {}
    for nid in note_ids:
        note = col.get_note(nid)
        tags = set(note.tags)
        tmpls = note.note_type()["tmpls"]
        for card in note.cards():
            name = tmpls[card.ord]["name"]
            deck = match_deck(tags, name, rules)
            if not deck:
                continue
            did = deck_ids.get(deck)
            if did is None:
                did = col.decks.id(deck, create=True)
                deck_ids[deck] = did
            if card.did != did:
                to_move.setdefault(did, []).append(card.id)

    moved = 0
    for did, cids in to_move.items():
        col.set_deck(cids, did)
        moved += len(cids)
    return moved


# ---------------------------------------------------------------------------
# Trigger: Add dialog
# ---------------------------------------------------------------------------

def on_add_note(note) -> None:
    """add_cards_did_add_note hook — route a freshly added note's cards."""
    rules = _rules()
    if not rules:
        return
    try:
        moved = _apply(mw.col, [note.id], rules)
        if moved:
            log.info("deck_router: przeniesiono %d kart po dodaniu nid=%s", moved, note.id)
    except Exception:
        log.exception("deck_router: błąd przy dodawaniu notatki")


# ---------------------------------------------------------------------------
# Trigger: after AI batch / workflow in the browser
# ---------------------------------------------------------------------------

def route_after_edit(parent, note_ids) -> None:
    """Called from ai_generator after a browser batch/workflow persists notes.

    No-op if the module is disabled or has no rules — the caller imports this
    unconditionally, so the guard lives here.
    """
    if not _module_enabled():
        return
    rules = _rules()
    note_ids = list(note_ids)
    if not rules or not note_ids:
        return

    counter = {"moved": 0}

    def op(col: Collection) -> OpChanges:
        counter["moved"] = _apply(col, note_ids, rules)
        return _ui_changes() if counter["moved"] else OpChanges()

    def on_success(_changes: OpChanges) -> None:
        if counter["moved"]:
            tooltip(f"Deck Router: przeniesiono {counter['moved']} kart",
                    parent=parent, period=3000)

    CollectionOp(parent=parent, op=op).success(on_success).run_in_background()


# ---------------------------------------------------------------------------
# Trigger: retroactive menu action
# ---------------------------------------------------------------------------

def _reorganize() -> None:
    rules = _rules()
    if not rules:
        tooltip("Deck Router: brak reguł w konfiguracji.", parent=mw, period=4000)
        return

    counter = {"moved": 0}

    def op(col: Collection) -> OpChanges:
        tags = {r["tag"] for r in rules}
        query = " OR ".join(f"tag:{t}" for t in tags)
        nids = col.find_notes(query)
        if not nids:
            return OpChanges()
        counter["moved"] = _apply(col, nids, rules)
        return _ui_changes() if counter["moved"] else OpChanges()

    def on_success(_changes: OpChanges) -> None:
        tooltip(f"Deck Router: przeniesiono {counter['moved']} kart", parent=mw, period=4000)

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()


def _confirm_reorganize() -> None:
    result = QMessageBox.question(
        mw, "Deck Router",
        "Przejść po istniejących notatkach z tagami z reguł i przenieść "
        "ich karty do właściwych talii?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        _reorganize()


def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools
    action = QAction("Deck Router: uporządkuj istniejące karty...", mw)
    action.triggered.connect(_confirm_reorganize)
    menu.addAction(action)
