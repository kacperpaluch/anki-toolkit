"""ai_senses: dopasowanie definicji po numerach i mapowanie znaczeń na pola. Bez Anki i sieci."""
from datetime import date
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
        "ai_senses_under_test", ROOT / "integrations" / "ai_senses.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"aqt": None, "aqt.qt": None}):
        spec.loader.exec_module(module)
    return module


# Tak zwraca userscript: diki daje znaczenia, reszta ponumerowane definicje.
ENTRIES = {
    "diki": [{"pl": "krawężnik"}, {"pl": "ograniczać (np. wydatki, podatki)"}, {"pl": "wędzidło"}],
    "Cambridge": [{"def": "to limit or control something", "pl": "ograniczać"},
                  {"def": "to limit or control something", "pl": "ograniczać"}],  # drugi słownik na stronie
    "LDoCE": [{"def": "the raised edge of a road", "pl": ""}],
}


class Provider:
    def __init__(self, answer):
        self.answer, self.prompts, self.last_error = answer, [], None

    def call_api(self, prompt):
        self.prompts.append(prompt)
        return self.answer


class DefinitionMatchingTests(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def test_entries_split_by_shape_and_duplicates_drop(self):
        units, definitions = self.m.split_entries(ENTRIES)
        self.assertEqual([u["pl"] for u in units],
                         ["krawężnik", "ograniczać (np. wydatki, podatki)", "wędzidło"])
        self.assertEqual([d["en"] for d in definitions],
                         ["to limit or control something", "the raised edge of a road"])
        self.assertEqual(definitions[0]["src"], "Cambridge")

    def test_prompt_numbers_lists_and_preserves_context(self):
        units, definitions = self.m.split_entries(ENTRIES)
        units[1].update(pos="verb", labels="formal")
        prompt = self.m.build_prompt("curb", units, definitions)
        data = json.loads(prompt.split("Dane słownikowe (JSON):\n", 1)[1])
        self.assertEqual(data["headword"], "curb")
        self.assertEqual(data["meanings"][1]["id"], "D2")
        self.assertEqual(data["meanings"][1]["pos"], "verb")
        self.assertEqual(data["meanings"][1]["labels"], "formal")
        self.assertEqual(data["definitions"][0]["pl"], "ograniczać")
        self.assertIn("nie instrukcje", prompt)
        self.assertIn("przykładowe zastosowanie nie wykluczają", prompt)

    def test_mapping_requires_complete_valid_ids_or_explicit_null(self):
        raw = '```json\n{"D1": "E2", "D2": "E1", "D3": null}\n```'
        self.assertEqual(self.m.parse_mapping(raw, 3, 2), {0: 1, 1: 0})
        self.assertEqual(self.m.parse_mapping('{"D1": null, "D2": null}', 2, 2), {})
        for raw in ('{}', '{"D1": "E1"}', '{"D1": "E99", "D2": null}',
                    '{"D1": "E1", "D2": null, "D3": null}',
                    '{"D1": "E1", "D1": null, "D2": null}',
                    '{"D1": true, "D2": null}', '{"D1": 1, "D2": null}',
                    '{"D1": "1", "D2": null}', '{"D1": "e1", "D2": null}',
                    '{"D1": "E01", "D2": null}', '{"D1": "null", "D2": null}',
                    'Here: {"D1": "E1", "D2": null}', 'nie wiem'):
            with self.subTest(raw=raw):
                self.assertIsNone(self.m.parse_mapping(raw, 2, 2))

    def test_dedup_keeps_translation_provenance_and_distinct_context(self):
        units, definitions = self.m.split_entries({
            "Oxford": [{"def": "a financial institution", "pos": "noun"}],
            "Cambridge": [{"def": "a financial institution", "pl": "bank", "pos": "noun"},
                          {"def": "a financial institution", "pl": "instytucja finansowa", "pos": "noun"},
                          {"def": "a financial institution", "pl": "bank", "pos": "noun", "labels": "informal"}],
            "diki": [{"pl": "bank", "pos": "noun"}, {"pl": "bank", "pos": "verb"}],
        })
        self.assertEqual(len(units), 2)
        self.assertEqual(len(definitions), 3)
        self.assertEqual(definitions[0]["src"], "Oxford")
        self.assertEqual(definitions[0]["pl"], "bank")
        self.assertEqual(definitions[0]["pl_src"], "Cambridge")
        self.assertEqual(definitions[2]["labels"], "informal")
        provider = Provider("not called")
        senses, error = self.m.generate(provider, "bank", {
            "Oxford": [{"def": "a financial institution"}],
            "Cambridge": [{"def": "a financial institution", "pl": "bank"}],
        }, {})
        self.assertIsNone(error)
        self.assertEqual(senses[0]["pl_src"], "Cambridge")
        self.assertEqual(provider.prompts, [])

    def test_card_text_comes_only_from_the_dictionaries(self):
        provider = Provider('{"D1": "E2", "D2": "E1", "D3": null}')
        senses, error = self.m.generate(provider, "curb", ENTRIES, {})
        self.assertIsNone(error)
        self.assertEqual([(s["pl"], s["en"], s["src"], s["by_ai"]) for s in senses], [
            ("krawężnik", "the raised edge of a road", "LDoCE", True),
            ("ograniczać (np. wydatki, podatki)", "to limit or control something", "Cambridge", True),
            ("wędzidło", "", "", False),          # brak definicji to pusta, nie zmyślona
        ])
        self.assertEqual(senses[0]["pl_src"], "diki")

    def test_without_diki_cambridge_pairs_are_cards_and_no_model_is_asked(self):
        provider = Provider("{}")
        senses, error = self.m.generate(provider, "mother", {"Cambridge": [
            {"def": "your female parent", "pl": "matka"}, {"def": "no translation", "pl": ""}]}, {})
        self.assertIsNone(error)
        self.assertEqual([(s["pl"], s["en"], s["by_ai"]) for s in senses],
                         [("matka", "your female parent", False)])
        self.assertEqual(provider.prompts, [])

    def test_no_definitions_means_no_model_call(self):
        provider = Provider("{}")
        senses, _ = self.m.generate(provider, "household income", {"diki": [{"pl": "dochód"}]}, {})
        self.assertEqual([(s["pl"], s["en"]) for s in senses], [("dochód", "")])
        self.assertEqual(provider.prompts, [])

    def test_failures_are_errors_not_empty_cards(self):
        for raw in ("bełkot", "{}", '{"D1": "E1"}', '{"D1": "E1", "D2": "E99", "D3": null}'):
            senses, error = self.m.generate(Provider(raw), "curb", ENTRIES, {})
            self.assertEqual(senses, [])
            self.assertTrue(error)
        self.assertTrue(self.m.generate(Provider(""), "curb", ENTRIES, {})[1])
        self.assertTrue(self.m.generate(Provider("{}"), "curb", {"LDoCE": [{"def": "x", "pl": ""}]}, {})[1])

    def test_explicit_null_is_success_and_definitions_can_be_reused(self):
        senses, error = self.m.generate(
            Provider('{"D1": null, "D2": null, "D3": null}'), "curb", ENTRIES, {})
        self.assertIsNone(error)
        self.assertEqual(len(senses), 3)
        self.assertTrue(all(not sense["en"] and not sense["by_ai"] for sense in senses))
        self.assertEqual(self.m.parse_mapping('{"D1": "E1", "D2": "E1"}', 2, 1), {0: 0, 1: 0})

    def test_note_fields_skip_empty_and_escape_html(self):
        sense = {"pl": "rozległy", "en": ""}
        self.assertEqual(
            self.m.note_fields(sense, {"en": "ang", "pl": "pol", "definition": "def"}, "sprawling"),
            {"ang": "sprawling", "pol": "rozległy"})
        self.assertEqual(self.m.note_fields({"pl": "<b>&lt;</b>"}, {"pl": "pol"}, "x"),
                         {"pol": "&lt;b&gt;&amp;lt;&lt;/b&gt;"})

    def test_manual_definition_is_no_longer_the_models(self):
        original = {"pl": "rozległy", "en": "wide", "src": "Oxford", "by_ai": True}
        self.assertEqual(self.m.edited_sense(original, original), original)
        self.assertTrue(self.m.edited_sense(original, {**original, "pl": "obszerny"})["by_ai"])
        self.assertFalse(self.m.edited_sense(original, {**original, "en": "vast"})["by_ai"])
        self.assertEqual(original["en"], "wide")
        with self.assertRaises(ValueError):
            self.m.edited_sense(original, {**original, "pl": "  "})

    def test_source_links_are_the_meaning_and_definition_tabs(self):
        sense = {"pl": "matka", "en": "a parent", "pl_src": "diki", "src": "Oxford"}
        links = self.m.source_links(sense, {"diki": "https://diki.pl/?a=1&b=2", "Oxford": "javascript:alert(1)",
                                            "LDoCE": "https://ldoce.test"})
        self.assertIn("&amp;b=2", links)
        self.assertNotIn("javascript", links)
        self.assertNotIn("LDoCE", links)


class ProviderLookupTests(unittest.TestCase):
    """Dostawca i jego model pochodzą z sekcji `ai_generator` tej samej wtyczki."""

    PROVIDERS = types.SimpleNamespace(PROVIDER_LABELS={"claude_cli": "Claude CLI"},
                                      get_provider=lambda name, cfg, timeout: (name, cfg, timeout))

    def setUp(self):
        self.m = load()
        self.settings = {"claude_cli": {"model": "opus"}}
        for name, value in (("_providers", lambda: self.PROVIDERS),
                            ("_provider_settings", lambda n: dict(self.settings.get(n, {})))):
            patcher = patch.object(self.m, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_label_says_which_model_actually_ran(self):
        """Dostawca kolejki jest jeden i własny — nie modele per pole z AI Generatora."""
        self.assertEqual(self.m.provider_label({"ai_provider": "claude_cli"}), "Claude CLI · opus")
        self.assertEqual(  # własny model kolejki bije domyślny dostawcy
            self.m.provider_label({"ai_provider": "claude_cli", "ai_model": "sonnet"}),
            "Claude CLI · sonnet")
        self.assertEqual(self.m.provider_label({}), "")

    def test_prepare_uses_own_model_and_timeout(self):
        provider, error = self.m.prepare_provider(
            {"ai_provider": "claude_cli", "ai_model": "sonnet", "ai_timeout": 30})
        self.assertIsNone(error)
        self.assertEqual(provider, ("claude_cli", {"model": "sonnet"}, 30))
        self.assertEqual(self.settings["claude_cli"], {"model": "opus"})  # zapisany model nietknięty

    def test_queue_effort_override_and_inheritance(self):
        self.settings["claude_cli"]["reasoning_effort"] = "medium"
        for effort, expected in (("high", "high"), ("", "medium"), (None, "medium")):
            provider, error = self.m.prepare_provider(
                {"ai_provider": "claude_cli", "ai_reasoning_effort": effort})
            self.assertIsNone(error)
            self.assertEqual(provider[1]["reasoning_effort"], expected)
        self.assertEqual(self.settings["claude_cli"]["reasoning_effort"], "medium")

    def test_prepare_reports_missing_or_unconfigured_provider(self):
        self.assertIn("wybierz", self.m.prepare_provider({})[1])
        self.assertIn("nie jest skonfigurowany", self.m.prepare_provider({"ai_provider": "openai"})[1])


class DuplicateWarningTests(unittest.TestCase):
    """Notatki z add_notes omijają kontrolę duplikatów okna „Dodaj"."""

    CFG = {"word_field": "ang", "ai_fields": {"pl": "pol"}}

    def setUp(self):
        self.m = load()
        self.searches = []
        self.notes = {1: {"ang": "mother", "pol": "matka"}, 2: {"ang": "mother", "pol": "macierz"}}
        self.m.mw = types.SimpleNamespace(col=types.SimpleNamespace(
            find_notes=lambda search: self.searches.append(search) or list(self.notes),
            get_note=lambda nid: self.notes[nid]))

    def test_existing_meanings_are_listed(self):
        self.assertEqual(self.m.existing_senses("mother", self.CFG), ["matka", "macierz"])
        self.assertEqual(self.searches, ['"ang:mother"'])

    def test_quotes_and_wildcards_cannot_break_out_of_the_search(self):
        self.m.existing_senses('a" OR *_x', self.CFG)
        self.assertEqual(self.searches, ['"ang:a\\" OR \\*\\_x" OR "ang:a&quot; OR \\*\\_x"'])

    def test_search_matches_the_html_the_field_is_stored_as(self):
        self.m.existing_senses("rock & roll", self.CFG)
        self.m.existing_senses("don't", self.CFG)
        self.assertEqual(self.searches, ['"ang:rock &amp; roll"',
                                         '"ang:don\'t" OR "ang:don&#x27;t"'])
        self.assertEqual(self.m.note_fields({}, {"en": "ang"}, "don't"), {"ang": "don't"})

    def test_broken_search_warns_instead_of_killing_the_picker(self):
        self.m.mw.col.find_notes = lambda _search: (_ for _ in ()).throw(RuntimeError("zły filtr"))
        with patch.object(self.m.log, "exception"):
            self.assertEqual(self.m.existing_senses("mother", self.CFG), [])


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
        clock = patch.object(self.m, "date")
        self.clock = clock.start()
        self.clock.today.return_value = date(2026, 10, 1)
        self.addCleanup(clock.stop)
        self.added = []
        self.m.mw = types.SimpleNamespace(col=types.SimpleNamespace(
            new_note=lambda notetype: Note(self.FIELDS),
            add_notes=lambda requests: self.added.extend((r.note, r.deck_id) for r in requests)))
        self.addcards = types.SimpleNamespace(
            editor=types.SimpleNamespace(note=Note(self.FIELDS)),
            deck_chooser=types.SimpleNamespace(selected_deck_id=7))

    def add(self, senses, cfg=None, word="sprawling"):
        chosen = [(word, sense) if isinstance(sense, dict) else sense for sense in senses]
        with patch.dict(sys.modules, {"anki.collection": types.SimpleNamespace(AddNoteRequest=types.SimpleNamespace)}):
            return self.m.add_notes(self.addcards, chosen, cfg or self.CFG)

    def sense(self, **kwargs):
        return {"pl": "rozległy", "en": "covering a large area", "src": "Oxford", "by_ai": True, **kwargs}

    def test_one_note_per_sense_in_chosen_deck_and_no_example(self):
        added, error = self.add([self.sense(), self.sense(pl="chaotyczny", en="", by_ai=False)])
        self.assertIsNone(error)
        self.assertEqual(added, 2)
        self.assertEqual([deck for _note, deck in self.added], [7, 7])
        self.assertEqual(self.added[0][0]["ang"], "sprawling")
        self.assertEqual(self.added[0][0]["def"], "covering a large area")
        self.assertEqual(self.added[0][0]["przyklad"], "")      # przykłady dodajesz sam

    def test_only_model_picked_definitions_wait_for_review(self):
        self.add([self.sense(), self.sense(by_ai=False), self.sense(en="", by_ai=False)])
        self.assertEqual([note.tags for note, _ in self.added],
                         [["ai-auto", "ai-review", "ai-import::2026-10-01"],
                          ["ai-auto", "ai-import::2026-10-01"], ["ai-auto", "ai-import::2026-10-01"]])

    def test_old_drafts_without_flag_are_reviewed_like_model_output(self):
        self.add([{"pl": "rozległy", "en": "covering a large area", "match": "exact"}])
        self.assertEqual(self.added[0][0].tags, ["ai-auto", "ai-review", "ai-import::2026-10-01"])

    def test_only_human_confirmation_removes_review_tag(self):
        self.add([self.sense(reviewed=True)])
        self.assertEqual(self.added[0][0].tags, ["ai-auto", "ai-import::2026-10-01"])

    def test_duplicate_field_map_never_reaches_collection(self):
        added, error = self.add([self.sense()], {**self.CFG, "ai_fields": {"pl": "ang"}})
        self.assertEqual((added, self.added), (0, []))
        self.assertIn("innego pola", error)

    def test_empty_configured_tags_preserve_daily_import_tag(self):
        self.add([self.sense()], {**self.CFG, "ai_tag": "", "ai_review_tag": ""})
        self.assertEqual(self.added[0][0].tags, ["ai-import::2026-10-01"])

    def test_import_date_is_taken_once_at_save_for_every_card(self):
        self.add([("mother", self.sense()), ("father", self.sense(by_ai=False))])
        self.clock.today.assert_called_once()
        self.assertTrue(all("ai-import::2026-10-01" in note.tags for note, _ in self.added))
        self.clock.today.return_value = date(2026, 10, 2)
        self.add([self.sense(reviewed=True)], {**self.CFG, "ai_tag": "ai-import::2026-10-02"})
        self.assertEqual(self.added[-1][0].tags, ["ai-import::2026-10-02"])

    def test_prepare_failure_never_starts_batch(self):
        with patch.object(self.m.mw.col, "new_note", side_effect=[Note(self.FIELDS), RuntimeError("prepare")]):
            with self.assertRaises(RuntimeError):
                self.add([self.sense(), self.sense()])
        self.assertEqual(self.added, [])

    def test_empty_selection_writes_nothing(self):
        self.assertEqual(self.add([]), (0, None))
        self.assertEqual(self.added, [])

    def test_one_batch_covers_several_headwords(self):
        """Paczka z „+ lista" to jedna transakcja, nie N transakcji po jednym haśle."""
        added, error = self.add([("mother", self.sense(pl="matka")),
                                 ("father", self.sense(pl="ojciec"))])
        self.assertIsNone(error)
        self.assertEqual(added, 2)
        self.assertEqual([note["ang"] for note, _deck in self.added], ["mother", "father"])
        self.assertEqual([note["pol"] for note, _deck in self.added], ["matka", "ojciec"])

    def test_bad_field_map_aborts_before_any_note_of_any_word(self):
        added, error = self.add([("mother", self.sense()), ("father", self.sense())],
                                {**self.CFG, "ai_fields": {"pl": "polski"}})
        self.assertEqual((added, self.added), (0, []))

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
                chosen = [("test", {"pl": "pierwsze", "match": "none"}),
                          ("inne", {"pl": "drugie", "match": "none"})]
                # Sygnatura musi być aktualna: TypeError też spełniłby assertRaises
                # i test „przechodziłby" nie sprawdzając wycofania zapisu.
                self.assertEqual(m.add_notes(addcards, [], cfg), (0, None))
                first, invalid = col.new_note(nt), col.new_note(nt)
                invalid.mid = 999999999999
                with patch.object(col, "new_note", side_effect=[first, invalid]):
                    with self.assertRaises(Exception) as caught:
                        m.add_notes(addcards, chosen, cfg)
                self.assertNotIsInstance(caught.exception, TypeError)
                self.assertEqual(col.note_count(), 0)
                self.assertEqual(m.add_notes(addcards, chosen, cfg)[0], 2)
                self.assertEqual(col.note_count(), 2)
                # Recovery asks the real search whether a word already has cards.
                with patch.object(m, "mw", types.SimpleNamespace(col=col)):
                    self.assertEqual(len(m.find_word_notes("test", cfg)), 1)
                    self.assertEqual(m.find_word_notes("tes", cfg), [])
                    # Znaki, które zapis zamienia na encje HTML, też muszą się znaleźć.
                    tricky = ["don't", "rock & roll"]
                    m.add_notes(addcards, [(w, {"pl": "x", "match": "none"}) for w in tricky], cfg)
                    for word in tricky:
                        self.assertEqual(len(m.find_word_notes(word, cfg)), 1, word)
                    col.undo()
                col.undo()
                self.assertEqual(col.note_count(), 0)
                with patch.object(m, "mw", types.SimpleNamespace(col=col)):
                    self.assertEqual(m.find_word_notes("test", cfg), [])
            finally:
                col.close()


if __name__ == "__main__":
    unittest.main()
