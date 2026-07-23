"""Testy czystej logiki oxford.logic — bez Anki."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_logic():
    spec = importlib.util.spec_from_file_location(
        "ox_logic", ROOT / "oxford" / "logic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = load_logic()

ENTRY = {"ang": "a", "pol": "każdy", "def": "any; every", "_level": "A1"}


class TestFieldsToFill(unittest.TestCase):
    def test_fills_only_empty_fields_and_skips_match_field(self):
        existing = {"ang": "a", "pol": "", "def": "moja definicja"}
        self.assertEqual(logic.fields_to_fill(ENTRY, existing, "ang"),
                         {"pol": "każdy"})

    def test_skips_fields_missing_in_note_and_technical_keys(self):
        out = logic.fields_to_fill(ENTRY, {"pol": "", "_level": ""}, "ang")
        self.assertEqual(out, {"pol": "każdy"})

    def test_whitespace_only_field_counts_as_empty(self):
        out = logic.fields_to_fill(ENTRY, {"pol": " <br> ".replace("<br>", "")}, "ang")
        self.assertEqual(out, {"pol": "każdy"})


class TestTruncate(unittest.TestCase):
    def test_keeps_short_and_cuts_long(self):
        self.assertEqual(logic.truncate("abc", 5), "abc")
        self.assertEqual(logic.truncate("abcdef", 5), "abcd…")


if __name__ == "__main__":
    unittest.main()
