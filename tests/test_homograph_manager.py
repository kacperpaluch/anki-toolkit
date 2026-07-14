"""Unit tests for homograph_manager.logic — staggering same-word meanings.

Pure logic, driven through light fakes mimicking Anki's col/note/card API.
anki.cards is stubbed so the test needs no Anki install.
"""

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Stub anki.cards before loading the module under test.
CARD_TYPE_NEW = 0
QUEUE_TYPE_SUSPENDED = -1
_anki = types.ModuleType("anki")
_cards_mod = types.ModuleType("anki.cards")
_cards_mod.CARD_TYPE_NEW = CARD_TYPE_NEW
_cards_mod.QUEUE_TYPE_SUSPENDED = QUEUE_TYPE_SUSPENDED
_anki.cards = _cards_mod
sys.modules.setdefault("anki", _anki)
sys.modules.setdefault("anki.cards", _cards_mod)


def load_logic():
    spec = importlib.util.spec_from_file_location(
        "hm_logic", ROOT / "homograph_manager" / "logic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = load_logic()

THRESHOLD = 30


class FakeCard:
    _seq = 0

    def __init__(self, ctype, ivl, suspended=False):
        FakeCard._seq += 1
        self.id = FakeCard._seq
        self.type = ctype
        self.ivl = ivl
        self.queue = QUEUE_TYPE_SUSPENDED if suspended else 0


class FakeNote:
    def __init__(self, nid, word, tags=None):
        self.id = nid
        self._fields = {"ang": word}
        self.tags = list(tags or [])

    def keys(self):
        return list(self._fields.keys())

    def __getitem__(self, k):
        return self._fields[k]

    def has_tag(self, t):
        return t in self.tags

    def add_tag(self, t):
        if t not in self.tags:
            self.tags.append(t)

    def remove_tag(self, t):
        if t in self.tags:
            self.tags.remove(t)


class FakeSched:
    def __init__(self, cards):
        self._cards = cards

    def suspend_cards(self, ids):
        for cid in ids:
            self._cards[cid].queue = QUEUE_TYPE_SUSPENDED

    def unsuspend_cards(self, ids):
        for cid in ids:
            self._cards[cid].queue = 0


class FakeCol:
    def __init__(self):
        self.notes = {}
        self.cards = {}
        self.note_cards = {}
        self.updates = 0
        self.sched = FakeSched(self.cards)

    def add_note(self, nid, word, cards, tags=None):
        note = FakeNote(nid, word, tags)
        self.notes[nid] = note
        cids = []
        for c in cards:
            self.cards[c.id] = c
            cids.append(c.id)
        self.note_cards[nid] = cids
        return note

    def get_note(self, nid):
        return self.notes[nid]

    def get_card(self, cid):
        return self.cards[cid]

    def card_ids_of_note(self, nid):
        return list(self.note_cards[nid])

    def update_note(self, _note):
        self.updates += 1

    def find_notes(self, query):
        # Only the '"ang:value"' exact-field form is used by group_nids.
        q = query.strip().strip('"')
        field, _, value = q.partition(":")
        value = value.replace("\\", "")
        return [nid for nid, n in self.notes.items()
                if logic.note_key(n, field) == value.strip().lower()]


def new(suspended=False):
    return FakeCard(CARD_TYPE_NEW, 0, suspended)


def review(ivl):
    return FakeCard(1, ivl)  # non-NEW type


TAG = "tk-homograph-suspended"


class HomographReactiveTests(unittest.TestCase):
    def test_no_group_noop(self):
        col = FakeCol()
        a = new()
        col.add_note(1, "unique", [a, new()])
        s, u = logic.process_reactive(col, 1, a.id, THRESHOLD, TAG)
        self.assertEqual((s, u), (0, 0))

    def test_immature_suspends_other_meanings(self):
        col = FakeCol()
        a1, a2 = new(), new()
        col.add_note(1, "assault", [a1, a2])          # answered meaning
        col.add_note(2, "assault", [new(), new()])    # other meaning
        col.add_note(3, "assault", [new(), new()])    # other meaning
        s, u = logic.process_reactive(col, 1, a1.id, THRESHOLD, TAG)
        self.assertEqual((s, u), (4, 0))              # 2 notes * 2 NEW cards
        # answered note untouched, its cards still available
        self.assertNotEqual(a2.queue, QUEUE_TYPE_SUSPENDED)
        self.assertTrue(col.get_note(2).has_tag(TAG))
        self.assertTrue(col.get_note(3).has_tag(TAG))

    def test_mature_releases_exactly_one(self):
        col = FakeCol()
        a = review(THRESHOLD)                          # answered meaning matured
        col.add_note(1, "assault", [a, review(THRESHOLD)])
        col.add_note(2, "assault", [new(True), new(True)], tags=[TAG])
        col.add_note(3, "assault", [new(True), new(True)], tags=[TAG])
        s, u = logic.process_reactive(col, 1, a.id, THRESHOLD, TAG)
        self.assertEqual((s, u), (0, 2))               # exactly one note (2 cards) freed
        # smallest nid (2) released and untagged; nid 3 still suspended/tagged
        self.assertFalse(col.get_note(2).has_tag(TAG))
        self.assertTrue(col.get_note(3).has_tag(TAG))

    def test_mature_but_slot_occupied_releases_nothing(self):
        col = FakeCol()
        a = review(THRESHOLD)
        col.add_note(1, "assault", [a, review(THRESHOLD)])
        col.add_note(2, "assault", [review(3), new(True)])  # meaning 2 already learning
        col.add_note(3, "assault", [new(True), new(True)], tags=[TAG])
        s, u = logic.process_reactive(col, 1, a.id, THRESHOLD, TAG)
        self.assertEqual((s, u), (0, 0))
        self.assertTrue(col.get_note(3).has_tag(TAG))

    def test_ignore_tag_skips(self):
        col = FakeCol()
        a = new()
        col.add_note(1, "assault", [a, new()], tags=["tk-homograph-ignored"])
        col.add_note(2, "assault", [new(), new()])
        s, u = logic.process_reactive(
            col, 1, a.id, THRESHOLD, TAG, ignore_tag="tk-homograph-ignored")
        self.assertEqual((s, u), (0, 0))


class HomographSyncTests(unittest.TestCase):
    def test_sync_keeps_one_active_learner(self):
        col = FakeCol()
        # meaning 1 learning (immature review) with an extra NEW card available;
        # meaning 2 has NEW cards available; meaning 3 already matured.
        col.add_note(1, "assault", [review(5), new()])
        col.add_note(2, "assault", [new(), new()])
        col.add_note(3, "assault", [review(THRESHOLD), new(True)], tags=[TAG])
        s, u = logic.process_group_sync(col, [1, 2, 3], THRESHOLD, TAG)
        # active = learner (nid 1): its NEW stays; nid 2's 2 NEW suspended.
        self.assertEqual(s, 2)
        self.assertNotEqual(col.get_note(1)._fields, None)
        self.assertTrue(col.get_note(2).has_tag(TAG))
        self.assertFalse(col.get_note(3).has_tag(TAG))  # matured -> tag cleared

    def test_sync_no_learner_picks_smallest_nid(self):
        col = FakeCol()
        col.add_note(3, "assault", [new(True), new(True)], tags=[TAG])
        col.add_note(5, "assault", [new(True), new(True)], tags=[TAG])
        s, u = logic.process_group_sync(col, [3, 5], THRESHOLD, TAG)
        # nid 3 activated (unsuspended), nid 5 stays suspended
        self.assertEqual(u, 2)
        self.assertFalse(col.get_note(3).has_tag(TAG))
        self.assertTrue(col.get_note(5).has_tag(TAG))


if __name__ == "__main__":
    unittest.main()
