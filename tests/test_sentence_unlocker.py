"""Unit tests for sentence_unlocker.logic — staggered gap-fill gating.

Pure logic, driven through light fakes mimicking Anki's col/note/card API.
"""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_logic():
    spec = importlib.util.spec_from_file_location(
        "su_logic", ROOT / "sentence_unlocker" / "logic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = load_logic()

# Template order in the "angielski" model
TMPLS = ["pol-ang", "ang-pol", "p1-nauka", "p2-nauka", "p3-nauka"]
MAIN = ["ang-pol", "pol-ang"]
CHAIN = [
    {"nauka_field": "p1-nauka", "tak_field": "p1-tak"},
    {"nauka_field": "p2-nauka", "tak_field": "p2-tak"},
    {"nauka_field": "p3-nauka", "tak_field": "p3-tak"},
]


class FakeCard:
    def __init__(self, cid, ord, ivl):
        self.id = cid
        self.ord = ord
        self.ivl = ivl


class FakeNote:
    def __init__(self, fields, tags=None):
        self.id = 1
        self.mid = 1
        self._fields = dict(fields)
        self.tags = list(tags or [])

    def keys(self):
        return list(self._fields.keys())

    def __getitem__(self, k):
        return self._fields[k]

    def __setitem__(self, k, v):
        self._fields[k] = v

    def has_tag(self, t):
        return t in self.tags

    def add_tag(self, t):
        if t not in self.tags:
            self.tags.append(t)


class FakeCol:
    """cards: dict template_name -> ivl for cards that currently EXIST."""

    def __init__(self, note, cards):
        self.note = note
        self.updated = 0
        self._cards = []
        for name, ivl in cards.items():
            self._cards.append(FakeCard(len(self._cards) + 100, TMPLS.index(name), ivl))
        self.models = self  # get() lives here

    def get(self, _mid):
        return {"tmpls": [{"name": n} for n in TMPLS]}

    def card_ids_of_note(self, _nid):
        return [c.id for c in self._cards]

    def get_card(self, cid):
        return next(c for c in self._cards if c.id == cid)

    def get_note(self, _nid):
        return self.note

    def update_note(self, _note):
        self.updated += 1


def run(note, cards):
    col = FakeCol(note, cards)
    n = logic.process_note(
        col, 1, threshold=21, main_templates=MAIN, chain=CHAIN, marker="tak",
        ignore_tag="tk-unlock-ignored", done_tag="tk-unlock-done",
    )
    return n, note, col


def base_fields(**over):
    f = {
        "p1-nauka": "sentence one [x]", "p1-tak": "",
        "p2-nauka": "sentence two [x]", "p2-tak": "",
        "p3-nauka": "sentence three [x]", "p3-tak": "",
    }
    f.update(over)
    return f


class SentenceUnlockerTests(unittest.TestCase):
    def test_mains_immature_no_unlock(self):
        note = FakeNote(base_fields())
        n, note, col = run(note, {"ang-pol": 5, "pol-ang": 5})
        self.assertEqual(n, 0)
        self.assertEqual(note["p1-tak"], "")

    def test_mains_mature_unlocks_first_only(self):
        note = FakeNote(base_fields())
        n, note, _ = run(note, {"ang-pol": 30, "pol-ang": 25})
        self.assertEqual(n, 1)
        self.assertEqual(note["p1-tak"], "tak")
        self.assertEqual(note["p2-tak"], "")  # staggered: p2 waits

    def test_only_one_main_mature_no_unlock(self):
        note = FakeNote(base_fields())
        n, note, _ = run(note, {"ang-pol": 30, "pol-ang": 5})
        self.assertEqual(n, 0)
        self.assertEqual(note["p1-tak"], "")

    def test_second_unlocks_when_first_card_matures(self):
        # p1 already unlocked; its card exists and is mature -> unlock p2
        note = FakeNote(base_fields(**{"p1-tak": "tak"}))
        n, note, _ = run(note, {"ang-pol": 30, "pol-ang": 30, "p1-nauka": 21})
        self.assertEqual(n, 1)
        self.assertEqual(note["p2-tak"], "tak")
        self.assertEqual(note["p3-tak"], "")

    def test_second_waits_while_first_card_immature(self):
        note = FakeNote(base_fields(**{"p1-tak": "tak"}))
        n, note, _ = run(note, {"ang-pol": 30, "pol-ang": 30, "p1-nauka": 3})
        self.assertEqual(n, 0)
        self.assertEqual(note["p2-tak"], "")

    def test_last_unlock_tags_done(self):
        note = FakeNote(base_fields(**{"p1-tak": "tak", "p2-tak": "tak"}))
        n, note, _ = run(note, {
            "ang-pol": 30, "pol-ang": 30, "p1-nauka": 30, "p2-nauka": 30,
        })
        self.assertEqual(n, 1)
        self.assertEqual(note["p3-tak"], "tak")
        self.assertTrue(note.has_tag("tk-unlock-done"))

    def test_empty_sentence_skipped(self):
        # p1 has no content -> not part of chain; p2 is first slot
        note = FakeNote(base_fields(**{"p1-nauka": ""}))
        n, note, _ = run(note, {"ang-pol": 30, "pol-ang": 30})
        self.assertEqual(n, 1)
        self.assertEqual(note["p2-tak"], "tak")
        self.assertEqual(note["p1-tak"], "")

    def test_no_sentences_tagged_done(self):
        note = FakeNote(base_fields(**{"p1-nauka": "", "p2-nauka": "", "p3-nauka": ""}))
        n, note, _ = run(note, {"ang-pol": 30, "pol-ang": 30})
        self.assertEqual(n, 0)
        self.assertTrue(note.has_tag("tk-unlock-done"))

    def test_ignore_tag_skips(self):
        note = FakeNote(base_fields(), tags=["tk-unlock-ignored"])
        n, note, col = run(note, {"ang-pol": 30, "pol-ang": 30})
        self.assertEqual(n, 0)
        self.assertEqual(note["p1-tak"], "")
        self.assertEqual(col.updated, 0)


if __name__ == "__main__":
    unittest.main()
