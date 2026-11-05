"""Type check of a hand-edited config against the config.json template."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("config_check", ROOT / "common" / "config_check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ConfigCheckTests(unittest.TestCase):
    def test_template_itself_is_clean(self):
        self.assertEqual(check.find_type_errors(check.load_template()), [])

    def test_wrong_types_are_named_and_reset(self):
        template = {"tts": {"timeout": 60, "voices": ["a"], "on": True}, "x": "text"}
        cfg = {"tts": {"timeout": "sixty", "voices": "a", "on": True, "extra": 1}, "x": None}
        errors = check.find_type_errors(cfg, template)
        self.assertEqual([path for path, _kind, _value in errors], ["tts.timeout", "tts.voices"])
        self.assertIn("tts.timeout: oczekiwano: liczba", check.describe(errors))
        check.reset_to_defaults(cfg, errors, template)
        self.assertEqual(cfg, {"tts": {"timeout": 60, "voices": ["a"], "on": True, "extra": 1}, "x": None})
        cfg["tts"]["voices"].append("b")
        self.assertEqual(template["tts"]["voices"], ["a"], "reset must copy, not share the template")

    def test_bool_is_not_a_number(self):
        self.assertEqual(len(check.find_type_errors({"n": True}, {"n": 3})), 1)
        self.assertEqual(check.find_type_errors({"n": 2.5}, {"n": 3}), [])


if __name__ == "__main__":
    unittest.main()
