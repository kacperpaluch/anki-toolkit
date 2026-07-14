"""Unit tests for audio_embed.logic — [sound:...] -> <audio> conversion."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_logic():
    spec = importlib.util.spec_from_file_location(
        "ae_logic", ROOT / "audio_embed" / "logic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = load_logic()


class FakeNote:
    def __init__(self, fields):
        self._f = dict(fields)

    def keys(self):
        return list(self._f.keys())

    def __getitem__(self, k):
        return self._f[k]

    def __setitem__(self, k, v):
        self._f[k] = v


class ConvertTextTests(unittest.TestCase):
    def test_single_tag(self):
        out = logic.convert_text("Hi[sound:tts_abc.mp3]")
        self.assertEqual(
            out, 'Hi<audio class="ex-audio" src="tts_abc.mp3" preload="none"></audio>')

    def test_multiple_tags_and_text(self):
        src = ("One.[sound:a.mp3]<br><br>\nTwo.[sound:b.mp3]")
        out = logic.convert_text(src)
        self.assertNotIn("[sound:", out)
        self.assertEqual(out.count("<audio "), 2)
        self.assertIn('src="a.mp3"', out)
        self.assertIn('src="b.mp3"', out)

    def test_custom_class_and_preload(self):
        out = logic.convert_text("[sound:x.mp3]", css_class="ex", preload="auto")
        self.assertEqual(
            out, '<audio class="ex" src="x.mp3" preload="auto"></audio>')

    def test_idempotent(self):
        once = logic.convert_text("[sound:x.mp3]")
        twice = logic.convert_text(once)
        self.assertEqual(once, twice)  # already-<audio> untouched

    def test_no_sound_tag_unchanged(self):
        self.assertEqual(logic.convert_text("plain text"), "plain text")


class ConvertNoteTests(unittest.TestCase):
    def test_only_listed_fields_touched(self):
        note = FakeNote({
            "audio": "[sound:dict_uk.mp3] [sound:dict_us.mp3]",  # main field, keep
            "przyklad": "Ex.[sound:tts_1.mp3]",
            "p1": "P1.[sound:tts_1.mp3]",
        })
        changed = logic.convert_note(note, ["przyklad", "p1", "p2", "p3"])
        self.assertTrue(changed)
        self.assertEqual(note["audio"], "[sound:dict_uk.mp3] [sound:dict_us.mp3]")
        self.assertIn("<audio ", note["przyklad"])
        self.assertIn("<audio ", note["p1"])

    def test_missing_field_skipped(self):
        note = FakeNote({"przyklad": "no audio here"})
        changed = logic.convert_note(note, ["przyklad", "p9"])
        self.assertFalse(changed)

    def test_no_change_returns_false(self):
        note = FakeNote({"p1": "already <audio class=\"ex-audio\" src=\"x.mp3\"></audio>"})
        self.assertFalse(logic.convert_note(note, ["p1"]))


if __name__ == "__main__":
    unittest.main()
