"""Pure-logic tests for the HTML Cleanup rule engine."""

import importlib.util
from pathlib import Path
import unittest


_PATH = Path(__file__).parent.parent / "html_cleanup" / "cleaning.py"
_SPEC = importlib.util.spec_from_file_location("standalone_html_cleanup", _PATH)
cleaning = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(cleaning)


class DefaultRuleTests(unittest.TestCase):
    """The shipped rules (config.json template) keep their behaviour."""

    def setUp(self):
        self.rules = cleaning.default_rules()

    def test_ang_field_removes_div_tags_without_breaks(self):
        value, counts = cleaning.clean_field("ang", "<div>look&nbsp;up</div>", self.rules)
        self.assertEqual(value, "look up")
        self.assertEqual(counts, {0: 1, 2: 2})

    def test_other_field_preserves_division_as_break(self):
        value, counts = cleaning.clean_field("def", "<div>one</div><div>two</div>", self.rules)
        self.assertEqual(value, "one<br>two")
        self.assertEqual(counts, {1: 3, 4: 2})

    def test_nested_divs_collapse(self):
        value, _counts = cleaning.clean_field("def", "<div>a<div>b</div></div>", self.rules)
        self.assertEqual(value, "a<br>b")


    def test_example_separator_survives_for_the_splitter(self):
        spec = importlib.util.spec_from_file_location(
            "standalone_splitting", _PATH.parents[1] / "field_splitter" / "splitting.py")
        splitting = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(splitting)
        value, _counts = cleaning.clean_field("przyklad", "ex one<br><br><br>ex two<br><br>", self.rules)
        self.assertEqual(value, "ex one<br><br>ex two")
        parts = splitting.split_field_value(value, "<br><br>", ["p1", "p2"])
        self.assertEqual(parts, {"p1": "ex one", "p2": "ex two"})


class RuleEngineTests(unittest.TestCase):
    def test_unknown_group_in_replacement_skips_the_rule(self):
        rules = [{"on": True, "find": "(a)", "to": r"\g<missing>", "regex": True, "fields": ""}]
        self.assertEqual(cleaning.clean_field("f", "abc", rules), ("abc", {}))

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
        with self.assertRaises(ValueError):
            cleaning.clean_field("f", "x", rules)


if __name__ == "__main__":
    unittest.main()
