"""Pure-logic tests for the batch backfill (no Anki, no network)."""

import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_batch_backfill(iter_impl):
    """Load batch_backfill with common/stats/template/field_generator/openai_compat
    stubbed. iter_impl(note, config, only_fields=None, overwrite=False) controls
    which (field_cfg, target) pairs each note contributes.
    """
    root_pkg = types.ModuleType("_bb"); root_pkg.__path__ = []
    ai_pkg = types.ModuleType("_bb.ai_generator"); ai_pkg.__path__ = []
    providers_pkg = types.ModuleType("_bb.ai_generator.providers"); providers_pkg.__path__ = []
    common_mod = types.ModuleType("_bb.common")
    common_mod.clean_html_normalized = lambda v: v
    common_mod.safe_str = lambda v: str(v or "").strip()
    common_mod.post_json = lambda *a, **k: (None, "stub")
    common_mod.fetch_url = lambda *a, **k: None
    stats_mod = types.ModuleType("_bb.ai_generator.stats")
    stats_mod.record_request = lambda *a, **k: None
    stats_mod.record_note = lambda *a, **k: None
    template_mod = types.ModuleType("_bb.ai_generator.template_engine")
    template_mod.render_template = lambda t, _f: t
    fg_mod = types.ModuleType("_bb.ai_generator.field_generator")
    fg_mod.iter_note_fields = iter_impl
    oc_mod = types.ModuleType("_bb.ai_generator.providers.openai_compat")
    oc_mod.add_temperature_if_supported = lambda data, model, temp: data.__setitem__("temperature", temp)
    oc_mod.add_reasoning_effort_if_supported = lambda data, model, eff: None

    modules = {
        "_bb": root_pkg,
        "_bb.ai_generator": ai_pkg,
        "_bb.ai_generator.providers": providers_pkg,
        "_bb.common": common_mod,
        "_bb.ai_generator.stats": stats_mod,
        "_bb.ai_generator.template_engine": template_mod,
        "_bb.ai_generator.field_generator": fg_mod,
        "_bb.ai_generator.providers.openai_compat": oc_mod,
    }
    name = "_bb.ai_generator.batch_backfill"
    spec = importlib.util.spec_from_file_location(name, ROOT / "ai_generator/batch_backfill.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class FakeNote:
    def __init__(self, nid, fields, yield_fields):
        self.id = nid
        self._f = dict(fields)
        self._yield = yield_fields

    def keys(self):
        return list(self._f)

    def __contains__(self, k):
        return k in self._f

    def __getitem__(self, k):
        return self._f[k]

    def __setitem__(self, k, v):
        self._f[k] = v

    def note_type(self):
        return {"name": "T"}


def _iter(note, config, only_fields=None, overwrite=False):
    for fc, tgt in note._yield:
        if only_fields is not None and tgt not in only_fields:
            continue
        yield fc, tgt


class BuildItemsTests(unittest.TestCase):
    def test_filters_to_eligible_providers_and_resolves_model(self):
        module = load_batch_backfill(_iter)
        config = {"providers": {"anthropic": {"model": "claude-x"},
                                "openai": {"model": "gpt-x"}}}
        note = FakeNote(
            42, {"A": "", "B": "", "C": ""},
            [
                ({"provider": "anthropic", "prompt": "p1"}, "A"),
                ({"provider": "openai", "model": "gpt-mini"}, "B"),
                ({"provider": "mistral"}, "C"),  # skipped
            ],
        )
        items, skipped = module.build_items([note], config)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0], {
            "custom_id": "i0", "provider": "anthropic", "model": "claude-x",
            "prompt": "p1", "nid": 42, "field": "A", "temperature": None,
        })
        self.assertEqual(items[1]["provider"], "openai")
        self.assertEqual(items[1]["model"], "gpt-mini")  # per-field model wins
        self.assertEqual(items[1]["custom_id"], "i1")

    def test_only_fields_restricts(self):
        module = load_batch_backfill(_iter)
        config = {"providers": {"anthropic": {"model": "m"}}}
        note = FakeNote(1, {"A": "", "B": ""},
                        [({"provider": "anthropic"}, "A"),
                         ({"provider": "anthropic"}, "B")])
        items, _ = module.build_items([note], config, only_fields={"B"})
        self.assertEqual([i["field"] for i in items], ["B"])

    def test_skips_when_no_model(self):
        module = load_batch_backfill(_iter)
        config = {"providers": {"openai": {}}}
        note = FakeNote(1, {"A": ""}, [({"provider": "openai"}, "A")])
        items, skipped = module.build_items([note], config)
        self.assertEqual(items, [])
        self.assertEqual(skipped, 1)

    def test_summarize_groups_by_provider_model(self):
        module = load_batch_backfill(_iter)
        items = [
            {"provider": "anthropic", "model": "claude"},
            {"provider": "anthropic", "model": "claude"},
            {"provider": "openai", "model": "gpt"},
        ]
        self.assertEqual(module.summarize(items), "anthropic/claude: 2; openai/gpt: 1")


class ApplyResultsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_batch_backfill(_iter)
        tmp = tempfile.mkdtemp()
        self.module._USER_FILES = tmp
        self.module._PATH = str(pathlib.Path(tmp) / "ai_batches.json")

    def test_writes_only_empty_fields_and_dedups(self):
        module = self.module
        note = FakeNote(7, {"Def": "", "Ex": ""}, [])
        filled = FakeNote(8, {"Def": "istnieje"}, [])

        class Col:
            def get_note(self, nid):
                return {7: note, 8: filled}.get(nid) or (_ for _ in ()).throw(KeyError(nid))

        ended = {"b1": {
            "record": {"provider": "anthropic", "map": {
                "i0": {"nid": 7, "field": "Def", "model": "m"},
                "i1": {"nid": 7, "field": "Ex", "model": "m"},
                "i2": {"nid": 8, "field": "Def", "model": "m"},   # already filled
                "i3": {"nid": 99, "field": "Def", "model": "m"},  # note gone
            }},
            "results": [
                {"custom_id": "i0", "ok": True, "text": "A", "in_tok": 3, "out_tok": 1},
                {"custom_id": "i1", "ok": True, "text": "B", "in_tok": 0, "out_tok": 0},
                {"custom_id": "i2", "ok": True, "text": "C", "in_tok": 0, "out_tok": 0},
                {"custom_id": "i3", "ok": True, "text": "D", "in_tok": 0, "out_tok": 0},
            ],
        }}
        summary = module.apply_results(Col(), ended)
        self.assertEqual(summary["filled"], 2)
        self.assertEqual(summary["skipped"], 2)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(note["Def"], "A")
        self.assertEqual(note["Ex"], "B")
        self.assertEqual(filled["Def"], "istnieje")
        self.assertEqual([n.id for n in summary["changed_notes"]], [7])

    def test_failed_result_and_missing_result_count_as_failed(self):
        module = self.module
        note = FakeNote(1, {"Def": ""}, [])

        class Col:
            def get_note(self, nid):
                return note

        ended = {"b1": {
            "record": {"provider": "openai", "map": {
                "i0": {"nid": 1, "field": "Def", "model": "m"},  # errored result
                "i1": {"nid": 1, "field": "Def", "model": "m"},  # no result at all (expired)
            }},
            "results": [
                {"custom_id": "i0", "ok": False, "text": None, "in_tok": 0, "out_tok": 0},
            ],
        }}
        summary = module.apply_results(Col(), ended)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["filled"], 0)


class FirstTextTests(unittest.TestCase):
    def test_skips_thinking_returns_first_text(self):
        module = load_batch_backfill(_iter)
        content = [{"type": "thinking", "thinking": "..."},
                   {"type": "text", "text": "answer"}]
        self.assertEqual(module._first_text(content), "answer")

    def test_none_on_empty(self):
        module = load_batch_backfill(_iter)
        self.assertIsNone(module._first_text([]))
        self.assertIsNone(module._first_text(None))


if __name__ == "__main__":
    unittest.main()
