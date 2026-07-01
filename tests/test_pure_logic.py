import importlib.util
import os
import pathlib
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch


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
http_helpers = load_module("http_helpers", "common/http.py")
field_splitter = load_module("field_splitter_logic", "field_splitter/splitting.py")
deck_router = load_module("deck_router_logic", "deck_router/logic.py")


def load_field_generator_with_stubs(provider_responses=None):
    """Load FieldGenerator without Anki so provider/model caching is testable.

    provider_responses: optional ``{(provider_name, model): [responses]}`` —
    each call_api() pops one response from the list. Lets tests simulate
    "primary fails, fallback succeeds".
    """
    root_pkg = types.ModuleType("_test_addon")
    root_pkg.__path__ = []
    ai_pkg = types.ModuleType("_test_addon.ai_generator")
    ai_pkg.__path__ = []
    anki_pkg = types.ModuleType("anki")
    anki_pkg.__path__ = []
    notes_mod = types.ModuleType("anki.notes")
    notes_mod.Note = object
    common_mod = types.ModuleType("_test_addon.common")
    common_mod.clean_html_normalized = lambda value: value
    common_mod.safe_str = lambda value: str(value or "").strip()
    stats_mod = types.ModuleType("_test_addon.ai_generator.stats")
    stats_mod.record_request = lambda *a, **k: None
    stats_mod.record_note = lambda *a, **k: None
    template_mod = types.ModuleType("_test_addon.ai_generator.template_engine")
    template_mod.render_template = lambda template, _fields: template
    providers_mod = types.ModuleType("_test_addon.ai_generator.providers")
    providers_mod.BaseProvider = object
    calls = []

    class FakeProvider:
        # ponytail: responses is a list consumed per call_api() — first call
        # pops index 0. If empty, returns None. Lets tests simulate "primary
        # fails, fallback succeeds" with a single config.
        def __init__(self, model, responses=None):
            self.model = model
            self.last_usage = (0, 0)
            self.last_error = None
            self._responses = list(responses) if responses else []
            self.calls = 0

        def call_api(self, prompt):
            self.calls += 1
            if self._responses:
                return self._responses.pop(0)
            return None

    def fake_get_provider(name, cfg, **_kwargs):
        calls.append((name, cfg["model"]))
        responses = (provider_responses or {}).get((name, cfg["model"]))
        return FakeProvider(cfg["model"], responses)

    providers_mod.get_provider = fake_get_provider
    modules = {
        "_test_addon": root_pkg,
        "_test_addon.ai_generator": ai_pkg,
        "_test_addon.ai_generator.stats": stats_mod,
        "_test_addon.ai_generator.template_engine": template_mod,
        "_test_addon.ai_generator.providers": providers_mod,
        "_test_addon.common": common_mod,
        "anki": anki_pkg,
        "anki.notes": notes_mod,
    }
    name = "_test_addon.ai_generator.field_generator"
    spec = importlib.util.spec_from_file_location(name, ROOT / "ai_generator/field_generator.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module, calls


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


class AiProviderModelResolutionTests(unittest.TestCase):
    def test_cache_is_per_model_and_old_config_uses_provider_default(self):
        module, calls = load_field_generator_with_stubs()
        generator = module.FieldGenerator({
            "providers": {
                "openai": {
                    "api_key": "sk-test",
                    "model": "gpt-default",
                    "temperature": 0.2,
                }
            }
        })

        first = generator._resolve_provider("openai", "gpt-5.5")
        second = generator._resolve_provider("openai", "gpt-5.6")
        same_first = generator._resolve_provider("openai", "gpt-5.5")
        fallback = generator._resolve_provider("openai")

        self.assertIs(first, same_first)
        self.assertIsNot(first, second)
        self.assertEqual(fallback.model, "gpt-default")
        self.assertEqual(calls, [
            ("openai", "gpt-5.5"),
            ("openai", "gpt-5.6"),
            ("openai", "gpt-default"),
        ])


class FallbackTests(unittest.TestCase):
    """Tests for provider-level and per-prompt fallback_model.

    Uses load_field_generator_with_stubs(provider_responses=...) to simulate
    "primary fails, fallback succeeds" without real API calls.
    """

    _NT_CONFIG = {
        "providers": {
            "openai": {
                "api_key": "sk-test",
                "model": "gpt-4o",
                "temperature": 0.2,
                "fallback_model": "gpt-4o-mini",
            },
            "openrouter": {
                "api_key": "sk-or",
                "model": "anthropic/claude-3.5-haiku",
                "temperature": 0.2,
            },
        },
        "note_types": {
            "angielski": {
                "def": {
                    "target": "def",
                    "provider": "openai",
                    "model": "gpt-4o",
                    "prompt": "Define {{ang}}",
                },
            },
        },
    }

    def _process_note(self, module, note_type="angielski", responses=None,
                      field_overrides=None):
        import copy
        nt_cfg = copy.deepcopy(self._NT_CONFIG)
        if field_overrides:
            nt_cfg["note_types"]["angielski"]["def"].update(field_overrides)
        generator = module.FieldGenerator(nt_cfg)
        note = _FakeNote(note_type, fields={"ang": "look", "def": ""})
        if responses:
            for (pname, model), resp in responses.items():
                # patch the cached provider's responses
                pass
        # Resolve providers with responses set
        for (pname, model), resp in (responses or {}).items():
            provider = generator._resolve_provider(pname, model)
            if provider is not None:
                provider._responses = list(resp)
        changed = generator.process_note(note)
        return note, changed, generator

    def test_primary_succeeds_no_fallback(self):
        module, _calls = load_field_generator_with_stubs()
        note, changed, gen = self._process_note(
            module, responses={("openai", "gpt-4o"): ["primary ok"]}
        )
        self.assertTrue(changed)
        self.assertEqual(note["def"], "primary ok")
        self.assertIsNone(gen.last_error)

    def test_provider_fallback_when_primary_fails(self):
        module, _calls = load_field_generator_with_stubs()
        note, changed, gen = self._process_note(
            module, responses={
                ("openai", "gpt-4o"): [None],  # primary fails
                ("openai", "gpt-4o-mini"): ["fallback ok"],  # fallback succeeds
            }
        )
        self.assertTrue(changed)
        self.assertEqual(note["def"], "fallback ok")

    def test_per_prompt_fallback_overrides_provider_fallback(self):
        module, _calls = load_field_generator_with_stubs()
        note, changed, gen = self._process_note(
            module,
            responses={
                ("openai", "gpt-4o"): [None],  # primary fails
                ("openrouter", "anthropic/claude-3.5-haiku"): ["cross-provider ok"],
            },
            field_overrides={
                "fallback_provider": "openrouter",
                "fallback_model": "anthropic/claude-3.5-haiku",
            },
        )
        self.assertTrue(changed)
        self.assertEqual(note["def"], "cross-provider ok")

    def test_no_fallback_when_not_configured(self):
        module, _calls = load_field_generator_with_stubs()
        # Remove fallback_model from provider config
        nt_cfg = {
            "providers": {
                "openai": {
                    "api_key": "sk-test",
                    "model": "gpt-4o",
                    "temperature": 0.2,
                    # no fallback_model
                },
            },
            "note_types": {
                "angielski": {
                    "def": {
                        "target": "def",
                        "provider": "openai",
                        "model": "gpt-4o",
                        "prompt": "Define {{ang}}",
                    },
                },
            },
        }
        generator = module.FieldGenerator(nt_cfg)
        note = _FakeNote("angielski", fields={"ang": "look", "def": ""})
        provider = generator._resolve_provider("openai", "gpt-4o")
        provider._responses = [None]  # primary fails
        changed = generator.process_note(note)
        self.assertFalse(changed)
        self.assertIsNotNone(gen.last_error if (gen := generator) else None)

    def test_both_primary_and_fallback_fail(self):
        module, _calls = load_field_generator_with_stubs()
        note, changed, gen = self._process_note(
            module, responses={
                ("openai", "gpt-4o"): [None],
                ("openai", "gpt-4o-mini"): [None],
            }
        )
        self.assertFalse(changed)
        self.assertIsNotNone(gen.last_error)
        self.assertIn("Fallback", gen.last_error)


class _FakeNote:
    """Minimal note stub for process_note tests — dict-like field access."""

    def __init__(self, note_type_name, fields, tags=None):
        self._fields = fields
        self.tags = tags or []
        self._nt_name = note_type_name

    def keys(self):
        return self._fields.keys()

    def __getitem__(self, key):
        return self._fields.get(key, "")

    def __setitem__(self, key, value):
        self._fields[key] = value

    def __contains__(self, key):
        return key in self._fields

    def __iter__(self):
        return iter(self._fields)

    def note_type(self):
        return {"name": self._nt_name}

    @property
    def id(self):
        return 1


class RateLimiterTests(unittest.TestCase):
    """Per-provider rate limiter: even RPM spacing + free_only scoping."""

    def setUp(self):
        self._fg_module, _ = load_field_generator_with_stubs()
        # Reset singleton so each test gets a fresh set of buckets.
        self._fg_module.RateLimiter._instance = None

    def _limiter(self):
        return self._fg_module.RateLimiter()

    def test_no_config_is_passthrough(self):
        rl = self._limiter()
        start = time.monotonic()
        with rl.slot("mistral", "mistral-small-latest"):
            pass
        self.assertLess(time.monotonic() - start, 0.1)

    def test_rpm_paces_request_starts(self):
        rl = self._limiter()
        rl.configure("mistral", rpm=120)  # 0.5s spacing
        with rl.slot("mistral", "mistral-small-latest"):
            pass
        start = time.monotonic()
        with rl.slot("mistral", "mistral-small-latest"):
            pass
        # Second start must wait ~one interval (0.5s) after the first.
        self.assertGreater(time.monotonic() - start, 0.4)

    def test_free_only_skips_paid_models(self):
        rl = self._limiter()
        rl.configure("openrouter", rpm=60, free_only=True)  # 1s spacing
        with rl.slot("openrouter", "anthropic/claude-3.5-haiku"):
            pass
        start = time.monotonic()
        with rl.slot("openrouter", "anthropic/claude-3.5-haiku"):
            pass
        # Paid model: not throttled even though a 1s interval is configured.
        self.assertLess(time.monotonic() - start, 0.2)

    def test_free_only_paces_free_models(self):
        rl = self._limiter()
        rl.configure("openrouter", rpm=120, free_only=True)  # 0.5s spacing
        with rl.slot("openrouter", "meta-llama/llama-3.2-3b:free"):
            pass
        start = time.monotonic()
        with rl.slot("openrouter", "meta-llama/llama-3.2-3b:free"):
            pass
        self.assertGreater(time.monotonic() - start, 0.4)

    def test_is_singleton(self):
        self.assertIs(self._limiter(), self._limiter())


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


class HttpHelperTests(unittest.TestCase):
    def test_post_json_returns_error_on_connection_failure(self):
        # Port 1 is privileged — nothing listens there, so we get a
        # deterministic connection refused without mocking. With max_retries=1
        # the loop runs once and returns (None, err) instead of raising.
        raw, err = http_helpers.post_json(
            "http://127.0.0.1:1/nope",
            b"{}",
            {"Content-Type": "application/json"},
            max_retries=1,
            timeout=1,
        )
        self.assertIsNone(raw)
        self.assertIsNotNone(err)
        self.assertIn("Connection error", err)


class TextHelperTests(unittest.TestCase):
    def test_split_separator_regex_plain(self):
        regex = text_helpers.split_separator_regex("<br><br>")
        self.assertEqual(regex.split("a<br><br>b<br><br><br><br>c"), ["a", "b", "c"])

    def test_split_separator_regex_tolerates_whitespace(self):
        regex = text_helpers.split_separator_regex("<br> <br>")
        self.assertEqual(regex.split("a<br><br>b"), ["a", "b"])
        self.assertEqual(regex.split("a<br>  <br>b"), ["a", "b"])

    def test_apply_word_replacements(self):
        repl = {"sb": "somebody", "sth": "something"}
        f = text_helpers.apply_word_replacements
        self.assertEqual(f("be reckless of sth", repl), "be reckless of something")
        self.assertEqual(f("tell sb sth", repl), "tell somebody something")
        # whole-word only: substrings inside other words are untouched
        self.assertEqual(f("absinthe", repl), "absinthe")
        # case-insensitive match; a capitalised match keeps its leading capital
        self.assertEqual(f("Sth happened", repl), "Something happened")
        self.assertEqual(f("SB", repl), "Somebody")
        # empty / no match are no-ops
        self.assertEqual(f("plain text", repl), "plain text")
        self.assertEqual(f("sth", {}), "sth")

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


class FieldSplitterTests(unittest.TestCase):
    _SAMPLE = (
        "Many people were murdered.[sound:tts_oe93owgdrkgo.mp3]<br><br>"
        "The museum tells the story.[sound:tts_9gfu5ninen4f.mp3]<br><br>"
        "Auschwitz was a death camp.[sound:tts_kwzj4ughyfk9.mp3]"
    )

    def test_split_three_examples(self):
        result = field_splitter.split_field_value(self._SAMPLE, "<br><br>", ["p1", "p2", "p3"])
        self.assertEqual(len(result), 3)
        self.assertTrue(result["p1"].startswith("Many people"))
        self.assertTrue(result["p2"].startswith("The museum"))
        self.assertTrue(result["p3"].startswith("Auschwitz"))
        self.assertIn("[sound:", result["p1"])

    def test_more_targets_than_parts(self):
        result = field_splitter.split_field_value("a<br><br>b", "<br><br>", ["p1", "p2", "p3"])
        self.assertEqual(len(result), 2)
        self.assertNotIn("p3", result)

    def test_more_parts_than_targets(self):
        result = field_splitter.split_field_value("a<br><br>b<br><br>c", "<br><br>", ["p1", "p2"])
        self.assertEqual(len(result), 2)
        self.assertNotIn("p3", result)

    def test_empty_value(self):
        self.assertEqual(field_splitter.split_field_value("", "<br><br>", ["p1"]), {})
        self.assertEqual(field_splitter.split_field_value("  ", "<br><br>", ["p1"]), {})

    def test_whitespace_tolerant_separator(self):
        # Whitespace in the SEPARATOR matches any run of whitespace in content
        result = field_splitter.split_field_value("a<br><br>b", "<br> <br>", ["p1", "p2"])
        self.assertEqual(result["p1"], "a")
        self.assertEqual(result["p2"], "b")

    def test_no_separator_found(self):
        result = field_splitter.split_field_value("just text", "<br><br>", ["p1", "p2"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result["p1"], "just text")

    def test_parse_target_fields(self):
        self.assertEqual(field_splitter.parse_target_fields("p1, p2, p3"), ["p1", "p2", "p3"])
        self.assertEqual(field_splitter.parse_target_fields(""), [])
        self.assertEqual(field_splitter.parse_target_fields(" p1 ,, p2 "), ["p1", "p2"])


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


def load_workflow_module(initial_cfg: dict):
    """Load ai_generator/workflow.py with aqt and the addon package stubbed,
    so migration and field-resolution logic is testable without Anki."""
    pkg = types.ModuleType("_twf")
    pkg.__path__ = []
    ai_pkg = types.ModuleType("_twf.ai_generator")
    ai_pkg.__path__ = []
    common_mod = types.ModuleType("_twf.common")
    common_mod.ADDON_NAME = "_twf"
    common_mod.plural_pl = lambda n, a, b, c: a

    class FakeAM:
        def __init__(self, cfg):
            self.cfg = cfg
        def getConfig(self, _name):
            return self.cfg
        def writeConfig(self, _name, cfg):
            self.cfg = cfg

    am = FakeAM(initial_cfg)
    aqt_mod = types.ModuleType("aqt")
    aqt_mod.mw = types.SimpleNamespace(addonManager=am)
    aqt_utils = types.ModuleType("aqt.utils")
    aqt_utils.tooltip = lambda *a, **k: None
    aqt_editor = types.ModuleType("aqt.editor")
    aqt_editor.Editor = object

    # browser_ui is only touched by _resolve_ai_fields("manual")
    browser_ui = types.ModuleType("_twf.ai_generator.browser_ui")
    browser_ui._all_configured_target_fields = lambda cfg, manual_only=False: (
        ["m1", "m2"] if manual_only else ["a1"]
    )

    modules = {
        "_twf": pkg,
        "_twf.ai_generator": ai_pkg,
        "_twf.ai_generator.browser_ui": browser_ui,
        "_twf.common": common_mod,
        "aqt": aqt_mod,
        "aqt.utils": aqt_utils,
        "aqt.editor": aqt_editor,
    }
    name = "_twf.ai_generator.workflow"
    spec = importlib.util.spec_from_file_location(name, ROOT / "ai_generator/workflow.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module, am, modules


class WorkflowMigrationTests(unittest.TestCase):
    def test_legacy_single_workflow_migrates_and_reseeds_pipelines(self):
        legacy = {
            "workflow": {
                "enabled": True,
                "editor_label": "Generuj fiszkę",
                "steps": [{"module": "ai", "action": "generate"}],
            }
        }
        wf, am, _mods = load_workflow_module(legacy)
        wf.migrate_workflows()
        out = am.cfg["workflows"]
        # legacy first, then the two re-seeded pipelines
        self.assertEqual(out[0]["name"], "Generuj fiszkę")
        self.assertTrue(out[0]["editor_button"])
        self.assertEqual(len(out), 3)
        self.assertIn("context_menu", am.cfg)
        self.assertTrue(am.cfg["context_menu"]["dictionary"])

    def test_migration_is_idempotent(self):
        wf, am, _mods = load_workflow_module({"workflows": [{"name": "X", "steps": [{"module": "tts", "action": "generate"}]}]})
        wf.migrate_workflows()
        self.assertEqual(len(am.cfg["workflows"]), 1)

    def test_get_workflows_falls_back_to_legacy(self):
        wf, _am, _mods = load_workflow_module({"workflow": {"editor_label": "L", "steps": [{"module": "ai", "action": "generate"}]}})
        wfs = wf.get_workflows()
        self.assertEqual(wfs[0]["name"], "L")

    def test_resolve_ai_fields(self):
        wf, _am, mods = load_workflow_module({})
        self.assertIsNone(wf._resolve_ai_fields({}, {}))
        self.assertIsNone(wf._resolve_ai_fields({"fields": "empty"}, {}))
        self.assertEqual(wf._resolve_ai_fields({"fields": "p1"}, {}), {"p1"})
        self.assertEqual(wf._resolve_ai_fields({"fields": ["a", "b"]}, {}), {"a", "b"})
        # "manual" triggers a lazy import of browser_ui — keep the stub live.
        with patch.dict(sys.modules, mods):
            self.assertEqual(wf._resolve_ai_fields({"fields": "manual"}, {}), {"m1", "m2"})


class FreeModelConcurrencyTests(unittest.TestCase):
    """slot() caps in-flight requests at max_concurrent; with free_only set,
    paid models on the same provider pass straight through."""

    def _limiter(self, max_concurrent, free_only=True):
        module, _ = load_field_generator_with_stubs()
        module.RateLimiter._instance = None
        rl = module.RateLimiter()
        rl.configure("openrouter", rpm=0,
                     max_concurrent=max_concurrent, free_only=free_only)
        return rl

    def _peak_in_flight(self, rl, model, n_threads):
        state = {"in": 0, "peak": 0}
        lock = threading.Lock()

        def worker():
            with rl.slot("openrouter", model):
                with lock:
                    state["in"] += 1
                    state["peak"] = max(state["peak"], state["in"])
                time.sleep(0.05)
                with lock:
                    state["in"] -= 1

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return state["peak"]

    def test_non_free_model_is_not_gated(self):
        rl = self._limiter(1)
        self.assertEqual(self._peak_in_flight(rl, "openai/gpt-5.5", 4), 4)

    def test_free_model_serialized_to_one(self):
        rl = self._limiter(1)
        self.assertEqual(self._peak_in_flight(rl, "openai/gpt-oss-120b:free", 6), 1)

    def test_free_model_respects_higher_concurrency(self):
        rl = self._limiter(2)
        self.assertEqual(self._peak_in_flight(rl, "openai/gpt-oss-120b:free", 6), 2)


class DeckRouterMatchTest(unittest.TestCase):
    def test_tag_only_rule_matches_any_template(self):
        rules = [{"tag": "abc123", "deck": "Osobne"}]
        self.assertEqual(deck_router.match_deck({"abc123"}, "pol-ang", rules), "Osobne")
        self.assertEqual(deck_router.match_deck({"abc123"}, "p1-nauka", rules), "Osobne")

    def test_no_tag_no_match(self):
        rules = [{"tag": "abc123", "deck": "Osobne"}]
        self.assertIsNone(deck_router.match_deck({"inne"}, "pol-ang", rules))

    def test_template_scoped_rule(self):
        rules = [{"tag": "abc123", "template": "pol-ang", "deck": "A"}]
        self.assertEqual(deck_router.match_deck({"abc123"}, "pol-ang", rules), "A")
        self.assertIsNone(deck_router.match_deck({"abc123"}, "ang-pol", rules))

    def test_first_matching_rule_wins(self):
        rules = [
            {"tag": "abc123", "template": "pol-ang", "deck": "A"},
            {"tag": "abc123", "deck": "B"},
        ]
        self.assertEqual(deck_router.match_deck({"abc123"}, "pol-ang", rules), "A")
        self.assertEqual(deck_router.match_deck({"abc123"}, "ang-pol", rules), "B")

    def test_incomplete_rules_ignored(self):
        self.assertIsNone(deck_router.match_deck({"abc123"}, "x", [{"tag": "abc123"}]))
        self.assertIsNone(deck_router.match_deck({"abc123"}, "x", [{"deck": "A"}]))


if __name__ == "__main__":
    unittest.main()
