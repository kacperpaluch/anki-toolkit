"""Pure-logic tests for the batch backfill (no Anki, no network)."""

import importlib.util
import os
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


class ChunkByTokensTests(unittest.TestCase):
    def _items(self, module, n, prompt_len):
        return [{"prompt": "x" * prompt_len, "custom_id": f"i{k}"} for k in range(n)]

    def test_splits_when_over_budget(self):
        module = load_batch_backfill(_iter)
        # est per item = 400//4 + 100 = 200 tokens; budget 500 → 2 items/chunk
        items = self._items(module, 5, 400)
        chunks = module._chunk_by_tokens(items, budget=500, reserve=100)
        self.assertEqual([len(c) for c in chunks], [2, 2, 1])

    def test_single_item_always_fits(self):
        module = load_batch_backfill(_iter)
        # one item bigger than the whole budget still gets its own chunk
        items = self._items(module, 1, 40000)
        chunks = module._chunk_by_tokens(items, budget=500, reserve=0)
        self.assertEqual([len(c) for c in chunks], [1])

    def test_all_fit_one_chunk(self):
        module = load_batch_backfill(_iter)
        items = self._items(module, 3, 40)
        chunks = module._chunk_by_tokens(items, budget=1_000_000, reserve=100)
        self.assertEqual(len(chunks), 1)


class SubmitOpenAIChunkingTests(unittest.TestCase):
    def _oa_items(self, n, prompt_len=400):
        # est per item = prompt_len//4 + reserve(100 in cfg below) = 200 by default
        return [{"custom_id": f"i{k}", "provider": "openai", "model": "gpt-x",
                 "prompt": "x" * prompt_len, "nid": k, "field": "f",
                 "temperature": None}
                for k in range(n)]

    def _ok_submit(self, calls):
        def fake_submit(chunk, config):
            calls["n"] += 1
            return {"id": f"b{calls['n']}", "provider": "openai",
                    "count": len(chunk), "map": {}}, None
        return fake_submit

    def test_caps_total_tokens_and_defers_rest(self):
        module = load_batch_backfill(_iter)
        # budget 250, est 200/item → only the first chunk (1 item) fits per run
        cfg = {"openai_batch_token_budget": 250, "openai_batch_output_reserve": 100}
        calls = {"n": 0}
        with patch.object(module, "_submit_openai", side_effect=self._ok_submit(calls)), \
             patch.object(module, "_pending_openai_tokens", return_value=0), \
             patch.object(module, "_append_record"):
            records, errors = module.submit(self._oa_items(3), cfg)

        self.assertEqual(len(records), 1)           # only what fits the budget
        self.assertEqual(calls["n"], 1)             # rest never even created
        self.assertTrue(any("odłożono 2" in e for e in errors))

    def test_all_fit_no_defer(self):
        module = load_batch_backfill(_iter)
        cfg = {"openai_batch_token_budget": 10_000, "openai_batch_output_reserve": 100}
        calls = {"n": 0}
        with patch.object(module, "_submit_openai", side_effect=self._ok_submit(calls)), \
             patch.object(module, "_pending_openai_tokens", return_value=0), \
             patch.object(module, "_append_record"):
            records, errors = module.submit(self._oa_items(3), cfg)

        self.assertEqual(len(records), 1)           # all 3 in one batch, all sent
        self.assertEqual(errors, [])                # nothing deferred

    def test_existing_pending_eats_budget(self):
        module = load_batch_backfill(_iter)
        # 10k already in flight ≥ budget → even the first chunk is deferred
        cfg = {"openai_batch_token_budget": 5_000, "openai_batch_output_reserve": 100}
        calls = {"n": 0}
        with patch.object(module, "_submit_openai", side_effect=self._ok_submit(calls)), \
             patch.object(module, "_pending_openai_tokens", return_value=10_000), \
             patch.object(module, "_append_record"):
            records, errors = module.submit(self._oa_items(3), cfg)

        self.assertEqual(records, [])               # nothing sent — queue already full
        self.assertEqual(calls["n"], 0)
        self.assertTrue(any("odłożono 3" in e for e in errors))

    def test_create_error_stops_the_run(self):
        module = load_batch_backfill(_iter)
        # singleton chunks; the first failed create stops the run — each retry
        # would waste another input-file upload on the same doomed call
        cfg = {"openai_batch_token_budget": 250, "openai_batch_output_reserve": 100}
        calls = {"n": 0}

        def fake_submit(chunk, config):
            calls["n"] += 1
            return None, "boom"

        with patch.object(module, "_submit_openai", side_effect=fake_submit), \
             patch.object(module, "_pending_openai_tokens", return_value=0), \
             patch.object(module, "_append_record"):
            records, errors = module.submit(self._oa_items(3), cfg)

        self.assertEqual(records, [])
        self.assertEqual(calls["n"], 1)             # no retries within one run
        self.assertTrue(any("boom" in e for e in errors))
        # non-quota errors don't start the backoff window
        with patch.object(module, "_pending_openai_tokens", return_value=0):
            self.assertGreater(module.openai_budget_left(cfg), 0)

    def test_enqueued_limit_backs_off(self):
        module = load_batch_backfill(_iter)
        cfg = {"openai_batch_token_budget": 250, "openai_batch_output_reserve": 100}
        calls = {"n": 0}

        def fake_submit(chunk, config):
            calls["n"] += 1
            return None, "400 - Enqueued token limit reached for gpt-x"

        with patch.object(module, "_submit_openai", side_effect=fake_submit), \
             patch.object(module, "_pending_openai_tokens", return_value=0), \
             patch.object(module, "_append_record"):
            records, errors = module.submit(self._oa_items(3), cfg)

        self.assertEqual(records, [])
        self.assertEqual(calls["n"], 1)             # one rejection stops the run
        self.assertTrue(any("odłożono 3" in e for e in errors))
        with patch.object(module, "_pending_openai_tokens", return_value=0):
            self.assertEqual(module.openai_budget_left(cfg), 0)   # backoff active
        # while backing off, submit defers everything without a single create
        with patch.object(module, "_submit_openai", side_effect=fake_submit), \
             patch.object(module, "_pending_openai_tokens", return_value=0), \
             patch.object(module, "_append_record"):
            records2, errors2 = module.submit(self._oa_items(2), cfg)
        self.assertEqual(records2, [])
        self.assertEqual(calls["n"], 1)             # untouched
        self.assertTrue(any("odłożono 2" in e for e in errors2))


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.m = load_batch_backfill(_iter)
        tmp = tempfile.mkdtemp()
        self.m._USER_FILES = tmp
        self.m._PATH = os.path.join(tmp, "ai_batches.json")

    def test_job_lifecycle(self):
        jid = self.m.add_job([1, 2, 3], {"def", "ipa"})
        jobs = self.m.active_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["nids"], [1, 2, 3])
        self.assertEqual(jobs[0]["only_fields"], ["def", "ipa"])
        self.m.finish_job(jid)
        self.assertEqual(self.m.active_jobs(), [])

    def test_only_fields_none_persisted(self):
        self.m.add_job([5], None)
        self.assertIsNone(self.m.active_jobs()[0]["only_fields"])

    def test_inflight_fields_from_pending(self):
        self.m._append_record({
            "id": "b1", "provider": "openai", "status": "in_progress", "count": 2,
            "map": {"i0": {"nid": 1, "field": "def"},
                    "i1": {"nid": 2, "field": "ipa"}},
        })
        self.assertEqual(self.m.inflight_fields(), {(1, "def"), (2, "ipa")})

    def test_job_expired_after_window(self):
        from datetime import datetime, timedelta
        fresh = {"created_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        old = {"created_at": (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M")}
        self.assertFalse(self.m.job_expired(fresh))
        self.assertTrue(self.m.job_expired(old))
        self.assertFalse(self.m.job_expired({"created_at": "garbage"}))

    def test_mark_applied_persists_after_commit(self):
        self.m._append_record({"id": "b1", "provider": "openai",
                               "status": "in_progress", "map": {}})
        self.assertEqual(len(self.m.pending_batches()), 1)
        self.m.mark_applied(["b1"])
        self.assertEqual(self.m.pending_batches(), [])

    def test_pending_openai_tokens_sums_only_in_progress(self):
        self.m._append_record({"id": "b1", "provider": "openai",
                               "status": "in_progress", "enq_tokens": 1000, "map": {}})
        self.m._append_record({"id": "b2", "provider": "openai",
                               "status": "applied", "enq_tokens": 5000, "map": {}})
        self.assertEqual(self.m._pending_openai_tokens(), 1000)


if __name__ == "__main__":
    unittest.main()
