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
prompt_templates = load_module("prompt_templates", "settings/prompt_templates.py")
html_helpers = load_module("html_helpers", "common/html.py")
text_helpers = load_module("text_helpers", "common/text.py")
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


class TemplateStructureProblemsTests(unittest.TestCase):
    def _problems(self, template):
        return template_engine.template_structure_problems(template)

    def test_valid_templates_have_no_problems(self):
        self.assertEqual(self._problems("plain text {{ang}}"), [])
        self.assertEqual(self._problems("{% if def %}x{% endif %}"), [])
        self.assertEqual(self._problems("{% if def %}x{% else %}y{% endif %}"), [])
        self.assertEqual(
            self._problems("{% if a %}1{% endif %} mid {% if b %}2{% else %}3{% endif %}"),
            [],
        )

    def test_unclosed_if(self):
        problems = self._problems("{% if def %}x")
        self.assertTrue(any("Niedomknięty" in p for p in problems))

    def test_orphan_endif(self):
        problems = self._problems("x{% endif %}")
        self.assertTrue(any("{% endif %} bez otwartego" in p for p in problems))

    def test_orphan_else(self):
        problems = self._problems("x{% else %}y")
        self.assertTrue(any("{% else %} bez otwartego" in p for p in problems))

    def test_duplicate_else(self):
        problems = self._problems("{% if a %}1{% else %}2{% else %}3{% endif %}")
        self.assertTrue(any("Podwójny" in p for p in problems))

    def test_nested_if_flagged(self):
        problems = self._problems("{% if a %}{% if b %}x{% endif %}{% endif %}")
        self.assertTrue(any("Zagnieżdżone" in p for p in problems))

    def test_if_without_field_name(self):
        problems = self._problems("{% if %}x{% endif %}")
        self.assertTrue(any("bez nazwy pola" in p for p in problems))


class HtmlHelperTests(unittest.TestCase):
    def test_clean_html_normalized_removes_tags_and_collapses_space(self):
        self.assertEqual(
            html_helpers.clean_html_normalized("<div>look&nbsp;forward</div>  to"),
            "look forward to",
        )


class TextHelperTests(unittest.TestCase):
    def test_split_separator_regex_plain(self):
        regex = text_helpers.split_separator_regex("<br><br>")
        self.assertEqual(regex.split("a<br><br>b<br><br><br><br>c"), ["a", "b", "c"])

    def test_split_separator_regex_tolerates_whitespace(self):
        regex = text_helpers.split_separator_regex("<br> <br>")
        self.assertEqual(regex.split("a<br><br>b"), ["a", "b"])
        self.assertEqual(regex.split("a<br>  <br>b"), ["a", "b"])

    def test_plural_pl(self):
        plural = lambda n: text_helpers.plural_pl(n, "krok", "kroki", "kroków")
        self.assertEqual(plural(1), "krok")
        self.assertEqual(plural(3), "kroki")
        self.assertEqual(plural(5), "kroków")
        self.assertEqual(plural(12), "kroków")
        self.assertEqual(plural(22), "kroki")


class PricingMatchTests(unittest.TestCase):
    _CATALOG = [
        {"id": "openai/gpt-4o", "prompt_price": 2.5e-06, "completion_price": 1e-05},
        {"id": "anthropic/claude-3.5-haiku", "prompt_price": 8e-07, "completion_price": 4e-06},
        {"id": "google/gemini-2.0-flash-001", "prompt_price": 1e-07, "completion_price": 4e-07},
        {"id": "x-ai/grok-3", "prompt_price": None, "completion_price": None},
    ]

    def test_exact_provider_model_match(self):
        result = ai_stats.match_pricing(["openai/gpt-4o"], self._CATALOG)
        self.assertEqual(result["openai/gpt-4o"], (2.5e-06, 1e-05))

    def test_normalized_match_with_date_suffix(self):
        result = ai_stats.match_pricing(
            ["anthropic/claude-3-5-haiku-20241022"], self._CATALOG
        )
        self.assertEqual(result["anthropic/claude-3-5-haiku-20241022"], (8e-07, 4e-06))

    def test_prefix_match_for_versioned_ids(self):
        result = ai_stats.match_pricing(["google/gemini-2.0-flash"], self._CATALOG)
        self.assertEqual(result["google/gemini-2.0-flash"], (1e-07, 4e-07))

    def test_openrouter_key_uses_full_id(self):
        result = ai_stats.match_pricing(
            ["openrouter/anthropic/claude-3.5-haiku"], self._CATALOG
        )
        self.assertEqual(result["openrouter/anthropic/claude-3.5-haiku"], (8e-07, 4e-06))

    def test_unmatched_and_priceless_models_are_absent(self):
        result = ai_stats.match_pricing(
            ["cometapi/grok-3", "mistral/unknown-model"], self._CATALOG
        )
        self.assertNotIn("mistral/unknown-model", result)
        self.assertNotIn("cometapi/grok-3", result)  # catalog entry has no prices

    def test_tts_model_matches_per_char_price(self):
        tts_catalog = [
            {"id": "openai/gpt-4o-mini-tts", "prompt_price": 1.2e-05},
        ]
        result = ai_stats.match_pricing(
            ["openrouter/openai/gpt-4o-mini-tts-2025-12-15", "kokoro/kokoro"],
            tts_catalog,
        )
        self.assertEqual(
            result["openrouter/openai/gpt-4o-mini-tts-2025-12-15"], (1.2e-05, 0.0)
        )
        self.assertNotIn("kokoro/kokoro", result)  # lokalny — brak ceny


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

    def test_nested_divs_leave_no_unbalanced_tags(self):
        cleaned, _nbsp, _div, div_br_count = cleaning.clean_field(
            "def", "<div>outer<div>inner</div></div>", "ang"
        )
        self.assertNotIn("<div", cleaned)
        self.assertNotIn("</div>", cleaned)
        self.assertEqual(div_br_count, 2)


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

    def test_record_tts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ai_stats._PATH = os.path.join(tmp, "usage_stats.json")
            ai_stats.reset_stats()

            ai_stats.record_tts("kokoro", "kokoro", 120, error=False)
            ai_stats.record_tts("kokoro", "kokoro", 80, error=True)
            ai_stats.record_tts("openrouter", "openai/gpt-4o-mini-tts", 50, error=False)

            data = ai_stats.get_stats()
            kokoro = data["tts"]["kokoro/kokoro"]
            self.assertEqual(kokoro["requests"], 2)
            self.assertEqual(kokoro["errors"], 1)
            self.assertEqual(kokoro["files"], 1)
            self.assertEqual(kokoro["chars"], 200)
            openrouter = data["tts"]["openrouter/openai/gpt-4o-mini-tts"]
            self.assertEqual(openrouter["files"], 1)
            self.assertEqual(openrouter["chars"], 50)

            # zakres bez danych → pusto
            empty = ai_stats.get_stats(start="2000-01-01", end="2000-12-31")
            self.assertEqual(empty["tts"], {})

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

            # własny zakres dat (inclusive) obejmujący tylko stary wpis
            custom = ai_stats.get_stats(start=old_day, end=old_day)
            self.assertEqual(custom["models"]["openai/gpt-4o"]["requests"], 9)
            self.assertEqual(custom["notes_processed"], 5)

            # zakres poza danymi → pusto
            empty = ai_stats.get_stats(start="2000-01-01", end="2000-12-31")
            self.assertEqual(empty["models"], {})


class PromptTemplatesTests(unittest.TestCase):
    def _mapping_for(self, template):
        mapping = {key: f"pole_{key}" for key, _label, _hints in template["params"]}
        cond = template.get("conditional")
        if cond:
            mapping[cond["param"][0]] = "pole_" + cond["param"][0]
        return mapping

    def test_all_templates_build_valid_prompts(self):
        for template in prompt_templates.TEMPLATES:
            for use_cond in (False, True):
                mapping = self._mapping_for(template)
                prompt = prompt_templates.build_prompt(template, mapping, use_cond)
                self.assertNotIn("«", prompt, f"leftover placeholder in {template['id']}")
                self.assertEqual(
                    template_engine.template_structure_problems(prompt), [],
                    f"invalid block structure in {template['id']} (cond={use_cond})",
                )

    def test_conditional_template_renders_both_branches(self):
        examples = next(t for t in prompt_templates.TEMPLATES if t["id"] == "examples")
        mapping = {"word": "ang", "translation": "pol", "definition": "def"}
        prompt = prompt_templates.build_prompt(examples, mapping, use_conditional=True)

        with_def = template_engine.render_template(
            prompt, {"ang": "book", "pol": "rezerwować", "def": "to arrange"}
        )
        self.assertIn("DEF: to arrange", with_def)

        without_def = template_engine.render_template(
            prompt, {"ang": "book", "pol": "rezerwować", "def": ""}
        )
        self.assertNotIn("DEF:", without_def)
        self.assertIn("book", without_def)

    def test_guess_field(self):
        fields = ["Ang", "pol", "Definicja", "IPA"]
        self.assertEqual(prompt_templates.guess_field(["ang"], fields), "Ang")
        self.assertEqual(prompt_templates.guess_field(["def", "definicja"], fields), "Definicja")
        self.assertEqual(prompt_templates.guess_field(["brak"], fields), "")


if __name__ == "__main__":
    unittest.main()
