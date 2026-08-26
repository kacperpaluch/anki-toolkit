"""Pure-logic tests for the standalone HTML Cleanup package."""

import importlib.util
from pathlib import Path
import unittest


_PATH = Path(__file__).parent.parent / "anki_toolkit_html_cleanup" / "cleaning.py"
_SPEC = importlib.util.spec_from_file_location("standalone_html_cleanup", _PATH)
cleaning = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(cleaning)


class DefaultRuleTests(unittest.TestCase):
    """The shipped rules must keep behaving as they did before rules were editable."""

    def setUp(self):
        self.rules = cleaning.default_rules("ang")

    def test_skip_field_removes_div_tags_without_breaks(self):
        value, counts = cleaning.clean_field("ang", "<div>look&nbsp;up</div>", self.rules)
        self.assertEqual(value, "look up")
        self.assertEqual(counts, {0: 1, 2: 2})

    def test_other_field_preserves_division_as_break(self):
        value, counts = cleaning.clean_field("def", "<div>one</div><div>two</div>", self.rules)
        self.assertEqual(value, "one<br>two")
        self.assertEqual(counts, {1: 2, 3: 1})

    def test_nested_divs_collapse(self):
        value, _counts = cleaning.clean_field("def", "<div>a<div>b</div></div>", self.rules)
        self.assertEqual(value, "ab<br>")


class RuleEngineTests(unittest.TestCase):
    def test_plain_text_rule_is_not_a_pattern(self):
        rules = [{"on": True, "find": "a.c", "to": "X", "regex": False, "fields": ""}]
        value, counts = cleaning.clean_field("f", "abc a.c", rules)
        self.assertEqual(value, "abc X")
        self.assertEqual(counts, {0: 1})

    def test_disabled_rule_is_skipped(self):
        rules = [{"on": False, "find": "a", "to": "b", "regex": False, "fields": ""}]
        self.assertEqual(cleaning.clean_field("f", "aaa", rules), ("aaa", {}))

    def test_field_scope(self):
        self.assertTrue(cleaning.applies_to("", "anything"))
        self.assertTrue(cleaning.applies_to("ang, pl", "pl"))
        self.assertFalse(cleaning.applies_to("ang, pl", "de"))
        self.assertFalse(cleaning.applies_to("!ang, pl", "pl"))
        self.assertTrue(cleaning.applies_to("!ang", "de"))

    def test_invalid_regex_is_skipped_not_raised(self):
        rules = [{"on": True, "find": "(unclosed", "to": "", "regex": True, "fields": ""}]
        self.assertEqual(cleaning.clean_field("f", "text", rules), ("text", {}))

    def test_self_feeding_repeat_rule_terminates(self):
        rules = [{"on": True, "find": "x", "to": "xx", "regex": False,
                  "fields": "", "repeat": True}]
        value, counts = cleaning.clean_field("f", "x", rules)
        self.assertLessEqual(len(value), 2 ** cleaning.MAX_PASSES)
        self.assertGreater(counts[0], 0)


if __name__ == "__main__":
    unittest.main()
