"""Rule that keeps user-defined editor shortcuts from typing characters."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("text", ROOT / "common" / "text.py")
text = importlib.util.module_from_spec(spec)
spec.loader.exec_module(text)


class ShortcutRuleTests(unittest.TestCase):
    def test_needs_ctrl_or_meta_unless_function_key(self):
        for keys in ("Ctrl+Shift+D", "Meta+O", "Ctrl+Alt+A", "F5", "Shift+F12", "Ctrl++"):
            self.assertIsNone(text.shortcut_typing_problem(keys), keys)
        for keys in ("D", "Shift+D", "Alt+A", "Alt+Shift+L", "F", "Alt+F"):
            self.assertIn("polskie znaki", text.shortcut_typing_problem(keys), keys)


if __name__ == "__main__":
    unittest.main()
