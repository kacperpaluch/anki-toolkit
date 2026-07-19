"""Testy czystej logiki supermemo.logic — bez Anki."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_logic():
    spec = importlib.util.spec_from_file_location(
        "sm_logic", ROOT / "supermemo" / "logic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = load_logic()

FIELD_MAP = {
    "English": "ang", "Translation": "pol", "Definition": "def",
    "Synonyms": "synonim", "PartOfSpeech": "cz_mowy", "Sound": "audio",
}


class CleanPosTests(unittest.TestCase):
    def test_strips_trailing_paren(self):
        self.assertEqual(logic.clean_pos("n)"), "n")
        self.assertEqual(logic.clean_pos("adj)"), "adj")

    def test_plain_value_untouched(self):
        self.assertEqual(logic.clean_pos("adverb"), "adverb")


class BuildQueryTests(unittest.TestCase):
    def test_basic(self):
        q = logic.build_query("SuperMemo Extreme", "English", "animal")
        self.assertEqual(q, 'note:"SuperMemo Extreme" "English:animal"')

    def test_escapes_quote_and_backslash(self):
        # Apostrof/cudzysłów w słowie nie może rozbić zapytania.
        q = logic.build_query("SM", "English", 'a"b\\c')
        self.assertEqual(q, 'note:"SM" "English:a\\"b\\\\c"')


class FieldsToFillTests(unittest.TestCase):
    def _sm(self):
        return {
            "English": "animal", "Translation": "zwierzę",
            "Definition": "a living organism", "Synonyms": "beast",
            "PartOfSpeech": "n)", "Sound": "[sound:x.mp3]",
        }

    def test_maps_and_cleans(self):
        existing = {k: "" for k in ["ang", "pol", "def", "synonim", "cz_mowy", "audio", "IPA"]}
        out = logic.fields_to_fill(self._sm(), existing, FIELD_MAP, "ang")
        self.assertEqual(out["pol"], "zwierzę")
        self.assertEqual(out["cz_mowy"], "n")           # nawias obcięty
        self.assertEqual(out["audio"], "[sound:x.mp3]")
        self.assertNotIn("ang", out)                    # pole dopasowania pominięte

    def test_skips_nonempty_targets(self):
        existing = {"ang": "", "pol": "już mam", "def": "", "synonim": "",
                    "cz_mowy": "", "audio": ""}
        out = logic.fields_to_fill(self._sm(), existing, FIELD_MAP, "ang")
        self.assertNotIn("pol", out)                    # nie nadpisuj
        self.assertIn("def", out)

    def test_skips_missing_target_fields(self):
        # Model docelowy nie ma pola 'synonim' → pomiń, bez błędu.
        existing = {"ang": "", "pol": "", "def": "", "cz_mowy": "", "audio": ""}
        out = logic.fields_to_fill(self._sm(), existing, FIELD_MAP, "ang")
        self.assertNotIn("synonim", out)

    def test_skips_empty_source(self):
        sm = self._sm()
        sm["Synonyms"] = ""
        existing = {"ang": "", "pol": "", "def": "", "synonim": "", "cz_mowy": "", "audio": ""}
        out = logic.fields_to_fill(sm, existing, FIELD_MAP, "ang")
        self.assertNotIn("synonim", out)


if __name__ == "__main__":
    unittest.main()
