"""ai_senses: weryfikacja cytatów i mapowanie znaczeń na pola. Bez Anki i sieci."""
import importlib.util
import json
import tempfile
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


PAGE = {"diki": "rozległy, rozciągnięty; chaotyczny " + " ".join(f"znaczenie {i}" for i in range(6)),
        "Oxford": "covering a large area\na sprawling city on the edge of the desert"}



class SenseParsingTests(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def parse(self, raw, **kwargs):
        data = json.loads(raw) if raw.startswith('{"senses"') else None
        if data:
            for sense in data["senses"]:
                sense.setdefault("src", "Oxford")
            raw = json.dumps(data)
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

    def test_source_and_polish_validation_and_html(self):
        sense = {"pl": "rozległy", "en": "covering a large area", "src": "Longman", "match": "exact"}
        result, _ = self.m.parse_senses(json.dumps({"senses": [sense]}), PAGE)
        self.assertEqual(result[0]["match"], "none")
        sense.update(src="Oxford", pl="nie ma tego w diki")
        self.assertEqual(self.m.parse_senses(json.dumps({"senses": [sense]}), PAGE)[0], [])
        sense.update(pl="rozległy", example="rozciągnięty")
        result, _ = self.m.parse_senses(json.dumps({"senses": [sense]}), PAGE)
        self.assertEqual(result[0]["example"], "")
        self.assertEqual(self.m.note_fields({"pl": "<b>&lt;</b>"}, {"pl": "pol"}, "x"),
                         {"pol": "&lt;b&gt;&amp;lt;&lt;/b&gt;"})

    def test_manual_edits_copy_and_downgrade_match(self):
        original = {"pl": "rozległy", "en": "wide", "example": "", "src": "Oxford", "match": "exact"}
        self.assertEqual(self.m.edited_sense(original, original), original)
        edited = self.m.edited_sense(original, {**original, "pl": "obszerny"})
        self.assertEqual(edited["match"], "approx")
        self.assertEqual(original["pl"], "rozległy")
        self.assertEqual(self.m.edited_sense(original, {**original, "en": ""})["match"], "none")
        with self.assertRaises(ValueError):
            self.m.edited_sense(original, {**original, "pl": "  "})
        links = self.m.source_links(original, {"diki": "https://diki.pl/?a=1&b=2",
                                               "Oxford": "javascript:alert(1)", "Other": "https://other.test"})
        self.assertIn("&amp;b=2", links)
        self.assertNotIn("javascript", links)
        self.assertNotIn("Other", links)

    def test_disabled_example_is_not_requested_or_returned(self):
        provider = types.SimpleNamespace(call_api=lambda prompt: json.dumps({"senses": [{
            "pl": "rozległy", "en": "covering a large area", "example": "a sprawling city",
            "src": "Oxford", "match": "exact"}]}))
        with patch.object(self.m, "_provider", return_value=(provider, None)):
            senses, error = self.m.generate("sprawling", PAGE, {"ai_fields": {"example": ""}})
            self.assertIsNone(error)
            self.assertEqual(senses[0]["example"], "")
            senses, _ = self.m.generate("sprawling", PAGE, {"ai_fields": {"example": "przyklad"}})
            self.assertEqual(senses[0]["example"], "a sprawling city")
        self.assertIn("Nie wybieraj ani nie generuj przykładów", self.m.build_prompt("x", PAGE, 3, False))

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
            add_notes=lambda requests: self.added.extend((r.note, r.deck_id) for r in requests)))
        self.addcards = types.SimpleNamespace(
            editor=types.SimpleNamespace(note=Note(self.FIELDS)),
            deck_chooser=types.SimpleNamespace(selected_deck_id=7))

    def add(self, senses, cfg=None):
        with patch.dict(sys.modules, {"anki.collection": types.SimpleNamespace(AddNoteRequest=types.SimpleNamespace)}):
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

    def test_prepare_failure_never_starts_batch(self):
        with patch.object(self.m.mw.col, "new_note", side_effect=[Note(self.FIELDS), RuntimeError("prepare")]):
            with self.assertRaises(RuntimeError):
                self.add([self.sense(), self.sense()])
        self.assertEqual(self.added, [])

    def test_batch_returns_changes_and_is_called_once(self):
        changes = object()
        with patch.object(self.m.mw.col, "add_notes", return_value=changes) as batch:
            self.assertEqual(self.add([self.sense(), self.sense()]), (2, changes))
        self.assertEqual(len(batch.call_args.args[0]), 2)
        batch.assert_called_once()

    def test_bad_field_map_aborts_before_any_note(self):
        added, error = self.add([self.sense()], {**self.CFG, "ai_fields": {"pl": "polski"}})
        self.assertEqual((added, self.added), (0, []))
        self.assertIn("polski", error)


class RealBatchTests(unittest.TestCase):
    def test_backend_batch_rolls_back_and_has_one_undo(self):
        try:
            from anki.collection import Collection
        except ImportError:
            self.skipTest("requires Anki Python environment")
        if Collection.__module__ != "anki.collection":
            self.skipTest("requires real Anki, not test stubs")
        with tempfile.TemporaryDirectory() as folder:
            col = Collection(str(Path(folder) / "collection.anki2"))
            try:
                m = load()
                m.mw = types.SimpleNamespace(col=col)
                nt = col.models.current()
                fields = [field["name"] for field in nt["flds"]]
                addcards = types.SimpleNamespace(
                    editor=types.SimpleNamespace(note=col.new_note(nt)),
                    deck_chooser=types.SimpleNamespace(selected_deck_id=1))
                cfg = {"word_field": fields[0], "ai_fields": {"pl": fields[1]}}
                senses = [{"pl": "pierwsze", "match": "none"}, {"pl": "drugie", "match": "none"}]
                first, invalid = col.new_note(nt), col.new_note(nt)
                invalid.mid = 999999999999
                with patch.object(col, "new_note", side_effect=[first, invalid]):
                    with self.assertRaises(Exception):
                        m.add_notes(addcards, "test", senses, cfg)
                self.assertEqual(col.note_count(), 0)
                self.assertEqual(m.add_notes(addcards, "test", senses, cfg)[0], 2)
                self.assertEqual(col.note_count(), 2)
                col.undo()
                self.assertEqual(col.note_count(), 0)
            finally:
                col.close()


if __name__ == "__main__":
    unittest.main()
