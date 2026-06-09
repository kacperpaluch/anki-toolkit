import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


template_engine = load_module("template_engine", "ai_generator/template_engine.py")
html_helpers = load_module("html_helpers", "common/html.py")
cleaning = load_module("nbsp_cleaning", "nbsp_remover/cleaning.py")


class TemplateEngineTests(unittest.TestCase):
    def test_replaces_variables_and_conditionals(self):
        rendered = template_engine.render_template(
            "{% if def %}DEF: {{def}}{% else %}WORD: {{ang}}{% endif %}",
            {"ang": "book", "def": "a written work"},
        )
        self.assertEqual(rendered, "DEF: a written work")

    def test_uses_else_for_empty_field(self):
        rendered = template_engine.render_template(
            "{% if def %}{{def}}{% else %}{{ang}}{% endif %}",
            {"ang": "book", "def": ""},
        )
        self.assertEqual(rendered, "book")


class HtmlHelperTests(unittest.TestCase):
    def test_clean_html_normalized_removes_tags_and_collapses_space(self):
        self.assertEqual(
            html_helpers.clean_html_normalized("<div>look&nbsp;forward</div>  to"),
            "look forward to",
        )


class NbspCleaningTests(unittest.TestCase):
    def test_skip_field_removes_div_tags(self):
        cleaned, nbsp_count, div_count, div_br_count = cleaning.clean_field(
            "ang", "<div>look&nbsp;forward</div>", "ang"
        )
        self.assertEqual(cleaned, "look forward")
        self.assertEqual((nbsp_count, div_count, div_br_count), (1, 2, 0))

    def test_other_field_converts_div_blocks_to_line_breaks(self):
        cleaned, nbsp_count, div_count, div_br_count = cleaning.clean_field(
            "def", "<div>one&nbsp;line</div><div>second</div>", "ang"
        )
        self.assertEqual(cleaned, "one line<br>second")
        self.assertEqual((nbsp_count, div_count, div_br_count), (1, 0, 2))


if __name__ == "__main__":
    unittest.main()
