"""Pure-logic tests for the standalone HTML Cleanup package."""

import importlib.util
from pathlib import Path
import unittest


_PATH = Path(__file__).parent.parent / "anki_toolkit_html_cleanup" / "cleaning.py"
_SPEC = importlib.util.spec_from_file_location("standalone_html_cleanup", _PATH)
cleaning = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(cleaning)


class HtmlCleanupLogicTests(unittest.TestCase):
    def test_skip_field_removes_div_tags_without_breaks(self):
        value, nbsp, div, div_br = cleaning.clean_field("ang", "<div>look&nbsp;up</div>", "ang")
        self.assertEqual(value, "look up")
        self.assertEqual((nbsp, div, div_br), (1, 2, 0))

    def test_other_field_preserves_division_as_break(self):
        value, nbsp, div, div_br = cleaning.clean_field("def", "<div>one</div><div>two</div>", "ang")
        self.assertEqual(value, "one<br>two")
        self.assertEqual((nbsp, div, div_br), (0, 0, 2))
