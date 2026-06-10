import importlib.util
import os
import pathlib
import tempfile
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
ai_stats = load_module("ai_stats", "ai_generator/stats.py")


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


class AiStatsTests(unittest.TestCase):
    def test_record_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            ai_stats._PATH = os.path.join(tmp, "usage_stats.json")
            ai_stats.reset_stats()

            ai_stats.record_request("openai", "gpt-4o", 100, 50, error=False, field_generated=True)
            ai_stats.record_request("openai", "gpt-4o", 10, 5, error=True, field_generated=False)
            ai_stats.record_note()

            data = ai_stats.get_stats()
            m = data["models"]["openai/gpt-4o"]
            self.assertEqual(m["requests"], 2)
            self.assertEqual(m["errors"], 1)
            self.assertEqual(m["input_tokens"], 110)
            self.assertEqual(m["output_tokens"], 55)
            self.assertEqual(m["fields"], 1)
            self.assertEqual(data["notes_processed"], 1)

            ai_stats.reset_stats()
            data = ai_stats.get_stats()
            self.assertEqual(data["models"], {})
            self.assertEqual(data["notes_processed"], 0)

    def test_day_range_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ai_stats._PATH = os.path.join(tmp, "usage_stats.json")
            ai_stats.reset_stats()

            # dzisiejszy wpis przez normalne API
            ai_stats.record_request("openai", "gpt-4o", 100, 50, error=False, field_generated=True)

            # sztuczny wpis sprzed 10 dni — poza zakresem "7 dni"
            from datetime import datetime, timedelta
            old_day = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            data = ai_stats._load()
            data["days"][old_day] = {
                "notes_processed": 5,
                "models": {"openai/gpt-4o": {
                    "requests": 9, "errors": 0,
                    "input_tokens": 900, "output_tokens": 450, "fields": 9,
                }},
            }
            ai_stats._save(data)

            all_time = ai_stats.get_stats()
            self.assertEqual(all_time["models"]["openai/gpt-4o"]["requests"], 10)
            self.assertEqual(all_time["notes_processed"], 5)

            last_week = ai_stats.get_stats(days=7)
            self.assertEqual(last_week["models"]["openai/gpt-4o"]["requests"], 1)
            self.assertEqual(last_week["notes_processed"], 0)

            today = ai_stats.get_stats(days=1)
            self.assertEqual(today["models"]["openai/gpt-4o"]["input_tokens"], 100)


if __name__ == "__main__":
    unittest.main()
