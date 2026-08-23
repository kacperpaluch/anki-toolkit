"""Pure-logic tests for the standalone Audio Embed package."""

import importlib.util
from pathlib import Path
import unittest


_PATH = Path(__file__).parent.parent / "anki_toolkit_audio_embed" / "logic.py"
_SPEC = importlib.util.spec_from_file_location("standalone_audio_embed_logic", _PATH)
logic = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(logic)


class AudioEmbedLogicTests(unittest.TestCase):
    def test_conversion_is_idempotent(self):
        converted = logic.convert_text("[sound:example.mp3]", "example-audio", "metadata")
        self.assertEqual(
            converted,
            '<audio class="example-audio" src="example.mp3" preload="metadata"></audio>',
        )
        self.assertEqual(logic.convert_text(converted), converted)

    def test_only_configured_existing_fields_change(self):
        note = {"example": "[sound:example.mp3]", "audio": "[sound:main.mp3]"}
        self.assertTrue(logic.convert_note(note, ["example", "missing"]))
        self.assertIn("<audio", note["example"])
        self.assertEqual(note["audio"], "[sound:main.mp3]")
