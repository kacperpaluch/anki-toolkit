"""ai_senses: weryfikacja cytatów i mapowanie znaczeń na pola. Bez Anki i sieci."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load():
    """Moduł sam w sobie — bez aqt, bo cała logika parsowania jest czysta."""
    spec = importlib.util.spec_from_file_location(
        "ai_senses_under_test", ROOT / "anki_toolkit_integrations" / "ai_senses.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"aqt": None, "aqt.qt": None}):
        spec.loader.exec_module(module)
    return module


PAGE = ("=== diki ===\nrozległy, rozciągnięty; chaotyczny\n"
        "=== Oxford ===\ncovering a large area\n"
        "a sprawling city on the edge of the desert")


class SenseParsingTests(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def parse(self, raw, **kwargs):
        return self.m.parse_senses(raw, PAGE, **kwargs)

    def test_verbatim_quote_survives(self):
        senses, error = self.parse(
            '{"senses":[{"pl":"rozległy","en":"covering a large area",'
            '"example":"a sprawling city","src":"Oxford","match":"exact"}]}')
        self.assertIsNone(error)
        self.assertEqual(senses[0]["en"], "covering a large area")
        self.assertEqual(senses[0]["match"], "exact")

    def test_invented_definition_is_dropped_not_trusted(self):
        senses, _ = self.parse(
            '{"senses":[{"pl":"rozległy","en":"extending over a wide region","match":"exact"}]}')
        self.assertEqual(senses[0]["en"], "")
        self.assertEqual(senses[0]["match"], "none")
        self.assertEqual(senses[0]["pl"], "rozległy")  # karta EN-PL zostaje

    def test_invented_example_does_not_kill_real_definition(self):
        senses, _ = self.parse(
            '{"senses":[{"pl":"rozległy","en":"covering a large area",'
            '"example":"a sprawling meadow","match":"exact"}]}')
        self.assertEqual(senses[0]["en"], "covering a large area")
        self.assertEqual(senses[0]["example"], "")

    def test_many_senses_keep_order_and_respect_limit(self):
        raw = ('{"senses":[' + ",".join(
            f'{{"pl":"znaczenie {i}","en":"","match":"none"}}' for i in range(6)) + "]}")
        senses, _ = self.parse(raw, max_senses=4)
        self.assertEqual([s["pl"] for s in senses],
                         ["znaczenie 0", "znaczenie 1", "znaczenie 2", "znaczenie 3"])

    def test_unknown_match_label_is_never_promoted_to_exact(self):
        senses, _ = self.parse(
            '{"senses":[{"pl":"rozległy","en":"covering a large area","match":"idealne"}]}')
        self.assertEqual(senses[0]["match"], "approx")

    def test_garbage_response_is_an_error_not_an_empty_card(self):
        self.assertTrue(self.parse("nie wiem")[1])
        self.assertTrue(self.parse('{"senses":[{"pl":""}]}')[1])
        self.assertTrue(self.parse('{"co":"innego"}')[1])

    def test_note_fields_skip_empty_and_unmapped(self):
        sense = {"pl": "rozległy", "en": "", "example": "", "src": "", "match": "none"}
        self.assertEqual(
            self.m.note_fields(sense, {"en": "ang", "pl": "pol", "definition": "def"}, "sprawling"),
            {"ang": "sprawling", "pol": "rozległy"})

    def test_prompt_truncates_pages(self):
        prompt = self.m.build_prompt("sprawling", {"diki": "x" * 20000}, 3)
        self.assertLess(len(prompt), 20000)
        self.assertIn("sprawling", prompt)


class Note(dict):
    def __init__(self, fields):
        super().__init__({name: "" for name in fields})
        self.tags = []

    def note_type(self):
        return {"flds": [{"name": name} for name in self]}


class AddNotesTests(unittest.TestCase):
    """Tagi i mapowanie pól — jedna karta na znaczenie, bez połowicznych zapisów."""

    FIELDS = ("ang", "pol", "def", "przyklad")
    CFG = {"word_field": "ang", "ai_tag": "ai-auto", "ai_review_tag": "ai-review",
           "ai_fields": {"pl": "pol", "definition": "def", "example": "przyklad"}}

    def setUp(self):
        self.m = load()
        self.added = []
        self.m.mw = types.SimpleNamespace(col=types.SimpleNamespace(
            new_note=lambda notetype: Note(self.FIELDS),
            add_note=lambda note, deck_id: self.added.append((note, deck_id))))
        self.addcards = types.SimpleNamespace(
            editor=types.SimpleNamespace(note=Note(self.FIELDS)),
            deck_chooser=types.SimpleNamespace(selected_deck_id=7))

    def add(self, senses, cfg=None):
        return self.m.add_notes(self.addcards, "sprawling", senses, cfg or self.CFG)

    def sense(self, **kwargs):
        return {"pl": "rozległy", "en": "covering a large area", "example": "",
                "src": "Oxford", "match": "exact", **kwargs}

    def test_one_note_per_sense_in_chosen_deck(self):
        added, error = self.add([self.sense(), self.sense(pl="chaotyczny", match="none", en="")])
        self.assertIsNone(error)
        self.assertEqual(added, 2)
        self.assertEqual([deck for _note, deck in self.added], [7, 7])
        self.assertEqual(self.added[0][0]["ang"], "sprawling")
        self.assertEqual(self.added[0][0]["def"], "covering a large area")

    def test_tags_are_mutually_exclusive(self):
        """Pewne dopasowanie dostaje ai_tag, reszta ai_review_tag — nigdy oba."""
        self.add([self.sense(), self.sense(match="approx"), self.sense(match="none", en="")])
        self.assertEqual([note.tags for note, _ in self.added],
                         [["ai-auto"], ["ai-review"], ["ai-review"]])

    def test_empty_tags_add_nothing(self):
        self.add([self.sense(match="none", en="")], {**self.CFG, "ai_tag": "", "ai_review_tag": ""})
        self.assertEqual(self.added[0][0].tags, [])

    def test_bad_field_map_aborts_before_any_note(self):
        added, error = self.add([self.sense()], {**self.CFG, "ai_fields": {"pl": "polski"}})
        self.assertEqual((added, self.added), (0, []))
        self.assertIn("polski", error)


if __name__ == "__main__":
    unittest.main()
