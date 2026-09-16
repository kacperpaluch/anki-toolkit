"""Regresje znalezione w audycie modułu Content (2026-09).

Każdy test pilnuje jednego błędu, który realnie gubił treść, pieniądze albo
wyniki:
  * regeneracja TTS kasowała stare audio zanim nowe powstało,
  * częściowo udany `split_audio` wyglądał na gotowy i nie dało się go dokończyć,
  * wynik z wątku roboczego nadpisywał tekst wpisany w międzyczasie w edytorze,
  * batche z jednego profilu były stosowane (albo kasowane) w innym,
  * ręczna wysyłka Batch API wysyłała ponownie pola już czekające w kolejce,
  * Field Splitter kasował pole źródłowe wpisane na listę celów.
"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent.parent
# Own package alias — inne moduły testowe rejestrują własne, uboższe "atc.*".
_PKG = "atc_regr"


# --- minimalne atrapy aqt/anki, wystarczające dla czystej logiki -----------

class _Any:
    """Zaślepka klasy/funkcji Qt — testy nie dotykają UI."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _name):
        return _Any()

    def __call__(self, *a, **k):
        return _Any()


def _module(name: str, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _stub_aqt() -> None:
    """Anki/Qt nie są instalowane w CI — logika i tak ich nie wywołuje."""
    if "aqt" in sys.modules:
        return
    aqt = _module("aqt", mw=types.SimpleNamespace(
        col=None, addonManager=None, taskman=None, progress=None))
    aqt.operations = _module("aqt.operations", CollectionOp=_Any)
    aqt.utils = _module("aqt.utils", tooltip=lambda *a, **k: None,
                        showWarning=lambda *a, **k: None,
                        askUser=lambda *a, **k: False)
    aqt.qt = _module("aqt.qt")
    aqt.qt.__all__ = []
    aqt.qt.__getattr__ = lambda _name: _Any
    aqt.browser = _module("aqt.browser", Browser=_Any)
    aqt.editor = _module("aqt.editor", Editor=_Any)
    aqt.sound = _module("aqt.sound", av_player=_Any())
    aqt.gui_hooks = _module("aqt.gui_hooks")

    anki = _module("anki")
    anki.notes = _module("anki.notes", Note=_Any)
    anki.collection = _module("anki.collection", Collection=_Any, OpChanges=_Any)


def _load(name: str, relative: str):
    """Załaduj moduł pakietu po ścieżce, bez uruchamiania Anki."""
    _stub_aqt()
    pkg = sys.modules.get(_PKG)
    if pkg is None:
        pkg = types.ModuleType(_PKG)
        pkg.__path__ = [str(ROOT)]
        sys.modules[_PKG] = pkg
    for sub in ("common", "tts", "ai_generator", "field_splitter"):
        key = f"{_PKG}.{sub}"
        if key in sys.modules:
            continue
        init = ROOT / sub / "__init__.py"
        # `common` re-exports from its __init__, the rest only needs to exist
        # as a package so relative imports resolve.
        if sub == "common":
            sub_spec = importlib.util.spec_from_file_location(
                key, init, submodule_search_locations=[str(ROOT / sub)])
            mod = importlib.util.module_from_spec(sub_spec)
            sys.modules[key] = mod
            sub_spec.loader.exec_module(mod)
        else:
            mod = types.ModuleType(key)
            mod.__path__ = [str(ROOT / sub)]
            sys.modules[key] = mod
    spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


processor = _load("tts.processor", "tts/processor.py")
editor_operation = _load("common.editor_operation", "common/editor_operation.py")
splitter = _load("field_splitter.splitting", "field_splitter/splitting.py")


class FakeNote:
    """Notatka Anki w zakresie, którego używa logika: pola po nazwie + .fields."""

    def __init__(self, fields: dict):
        self._names = list(fields)
        self.fields = list(fields.values())
        self.tags: list = []
        self.id = 1

    def keys(self):
        return list(self._names)

    def __contains__(self, name):
        return name in self._names

    def __getitem__(self, name):
        return self.fields[self._names.index(name)]

    def __setitem__(self, name, value):
        self.fields[self._names.index(name)] = value


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

class TestTtsRegeneration(unittest.TestCase):
    def test_failed_regeneration_keeps_old_audio(self):
        """overwrite=True nie może usunąć audio przed wygenerowaniem nowego."""
        note = FakeNote({"ang": "cat", "audio": "[sound:old.mp3]"})
        task = {"source_field": "ang", "target_field": "audio", "mode": "single"}

        items, ctx = processor.build_note_work_items(note, [task], ["v1"], overwrite=True)

        self.assertEqual(len(items), 1)
        self.assertEqual(note["audio"], "[sound:old.mp3]", "notatka tknięta przed wynikiem")
        # Generowanie padło — brak wyników, więc apply nie ma czego wpisać.
        processor.apply_results_to_note(note, items, ctx, {})
        self.assertEqual(note["audio"], "[sound:old.mp3]")

    def test_partial_split_regeneration_keeps_failed_segment(self):
        """Gdy drugi segment padnie, zostaje przy swoim starym nagraniu."""
        note = FakeNote({"przyklad": "One[sound:a.mp3]<br><br>Two[sound:b.mp3]"})
        task = {"source_field": "przyklad", "target_field": "przyklad",
                "mode": "split", "split_separator": "<br><br>"}

        items, ctx = processor.build_note_work_items(note, [task], ["v1"], overwrite=True)
        self.assertEqual(len(items), 2)

        processor.apply_results_to_note(note, items, ctx, {(0, 0): "new_a.mp3"})
        self.assertIn("[sound:new_a.mp3]", note["przyklad"])
        self.assertIn("[sound:b.mp3]", note["przyklad"], "stare audio segmentu 2 przepadło")

    def test_partial_split_audio_is_resumable(self):
        """Pole z 1 tagiem przy 2 segmentach to nie „gotowe" — trzeba dokończyć."""
        note = FakeNote({"przyklad": "One<br><br>Two", "p_audio": "[sound:a.mp3]"})
        task = {"source_field": "przyklad", "target_field": "p_audio",
                "mode": "split_audio", "split_separator": "<br><br>"}

        items, _ctx = processor.build_note_work_items(note, [task], ["v1"])
        self.assertEqual(len(items), 2, "pominięto zadanie mimo brakującego segmentu")

        complete = FakeNote({"przyklad": "One<br><br>Two",
                             "p_audio": "[sound:a.mp3][sound:b.mp3]"})
        items, _ctx = processor.build_note_work_items(complete, [task], ["v1"])
        self.assertEqual(items, [], "kompletne pole generowane po raz drugi")

    def test_partial_split_audio_retry_preserves_unmapped_old_recordings(self):
        task = {"source_field": "src", "target_field": "audio", "mode": "split_audio",
                "split_separator": "|"}
        for overwrite in (False, True):
            note = FakeNote({"src": "one|two", "audio": "[sound:old.mp3]"})
            items, ctx = processor.build_note_work_items(note, [task], ["v"], overwrite)
            self.assertFalse(processor.apply_results_to_note(note, items, ctx, {(0, 1): "new.mp3"}))
            self.assertEqual(note["audio"], "[sound:old.mp3]")
            self.assertTrue(processor.apply_results_to_note(
                note, items, ctx, {(0, 0): "one.mp3", (0, 1): "two.mp3"}))
            self.assertEqual(note["audio"], "[sound:one.mp3][sound:two.mp3]")

    def test_complete_split_audio_keeps_failed_segment_on_regeneration(self):
        note = FakeNote({"src": "one|two", "audio": "[sound:one.mp3][sound:two.mp3]"})
        task = {"source_field": "src", "target_field": "audio", "mode": "split_audio",
                "split_separator": "|"}
        items, ctx = processor.build_note_work_items(note, [task], ["v"], True)
        processor.apply_results_to_note(note, items, ctx, {(0, 1): "new.mp3"})
        self.assertEqual(note["audio"], "[sound:one.mp3][sound:new.mp3]")

    def test_split_to_separate_target_keeps_old_field_on_partial_failure(self):
        note = FakeNote({"src": "one|two", "target": "one[sound:a.mp3]|two[sound:b.mp3]"})
        task = {"source_field": "src", "target_field": "target", "mode": "split", "split_separator": "|"}
        items, ctx = processor.build_note_work_items(note, [task], ["v"], True)
        previous = note["target"]
        self.assertFalse(processor.apply_results_to_note(note, items, ctx, {(0, 0): "new.mp3"}))
        self.assertEqual(note["target"], previous)

    def test_media_does_not_follow_profile_switch(self):
        media = types.SimpleNamespace(write_data=lambda *a: self.fail("wrote to wrong profile"))
        original = types.SimpleNamespace(media=media)
        other = types.SimpleNamespace(media=media)
        item = {"text": "hello", "voice": "v", "task_i": 0, "seg_i": -1}
        def generate(*args):
            processor.mw.col = other
            return b"audio"
        with patch.object(processor.mw, "col", original), patch.object(processor, "generate_audio", generate):
            results, errors, _ = processor.generate_for_items([item], {}, collection=original)
        self.assertEqual((results, errors), ({}, 1))


# ---------------------------------------------------------------------------
# Edytor — wynik z tła nie nadpisuje tego, co user wpisał w międzyczasie
# ---------------------------------------------------------------------------

class TestDetachedMerge(unittest.TestCase):
    def test_user_edit_wins_over_generated_result(self):
        note = FakeNote({"ang": "cat", "def": ""})
        clone, before = editor_operation.detach_note(note)

        clone["def"] = "wynik AI"          # wątek roboczy
        note["def"] = "wpisane ręcznie"    # user w tym czasie

        skipped = editor_operation.merge_note(note, clone, before)

        self.assertEqual(note["def"], "wpisane ręcznie")
        self.assertEqual(skipped, ["def"])

    def test_untouched_field_receives_result(self):
        note = FakeNote({"ang": "cat", "def": ""})
        clone, before = editor_operation.detach_note(note)
        clone["def"] = "wynik AI"

        self.assertEqual(editor_operation.merge_note(note, clone, before), [])
        self.assertEqual(note["def"], "wynik AI")

    def test_clone_is_independent(self):
        note = FakeNote({"ang": "cat", "def": ""})
        clone, _before = editor_operation.detach_note(note)
        clone["ang"] = "dog"
        self.assertEqual(note["ang"], "cat")

    def test_changed_source_invalidates_output(self):
        note = FakeNote({"ang": "cat", "audio": ""})
        clone, before = editor_operation.detach_note(note)
        clone["audio"] = "[sound:cat.mp3]"
        note["ang"] = "dog"
        self.assertEqual(editor_operation.merge_note(note, clone, before), ["audio"])
        self.assertEqual(note["audio"], "")

    def test_changed_schema_is_rejected(self):
        note = FakeNote({"a": "", "b": ""})
        clone, before = editor_operation.detach_note(note)
        clone["a"] = "result"
        note._names.reverse()
        with self.assertRaises(RuntimeError):
            editor_operation.merge_note(note, clone, before)
        self.assertEqual(note.fields, ["", ""])

    def test_editor_merge_refreshes_each_step_and_reads_switched_note_fresh(self):
        note = FakeNote({"a": "", "b": ""})
        fresh = FakeNote({"a": "user edit", "b": ""})
        writes = []
        col = types.SimpleNamespace(get_note=lambda nid: fresh,
                                    update_note=lambda n: writes.append(list(n.fields)))
        editor = types.SimpleNamespace(note=note, loadNote=lambda: refreshes.append(list(note.fields)))
        refreshes = []
        aqt = sys.modules["aqt"]
        with patch.object(aqt.mw, "col", col), patch.object(
                aqt.operations, "on_op_finished", lambda *a: None, create=True):
            clone, before = editor_operation.detach_note(note)
            clone["a"] = "first"
            editor_operation.merge_editor_note(editor, note, clone, before)
            self.assertEqual(refreshes, [["first", ""]])
            clone["b"] = "second"
            editor.note = None
            self.assertEqual(editor_operation.merge_editor_note(editor, note, clone, before), ["b"])
            self.assertEqual(fresh.fields, ["user edit", ""])
            aqt.mw.col = types.SimpleNamespace()
            with self.assertRaises(RuntimeError):
                editor_operation.merge_editor_note(editor, note, clone, before)

    def test_repeated_merge_rebaselines(self):
        """Workflow scala po każdym kroku — drugi krok nie może cofnąć pierwszego."""
        note = FakeNote({"a": "", "b": ""})
        clone, before = editor_operation.detach_note(note)

        clone["a"] = "krok 1"
        editor_operation.merge_note(note, clone, before)
        clone["b"] = "krok 2"
        editor_operation.merge_note(note, clone, before)

        self.assertEqual([note["a"], note["b"]], ["krok 1", "krok 2"])

    def test_workflow_flush_does_not_undo_previous_step(self):
        aqt = sys.modules["aqt"]
        pending = []
        note = FakeNote({"a": "", "b": ""})
        note.id = 0
        web_fields = list(note.fields)
        def save(callback):
            note.fields[:] = web_fields
            callback()
        def load():
            web_fields[:] = note.fields
        editor = types.SimpleNamespace(note=note, saveNow=save, loadNote=load)
        taskman = types.SimpleNamespace(run_in_background=lambda task, done, **_: pending.append((task, done)))
        manager = types.SimpleNamespace(getConfig=lambda name: {})
        with patch.object(aqt.mw, "col", object()), patch.object(aqt.mw, "taskman", taskman), \
                patch.object(aqt.mw, "addonManager", manager), patch.object(
                    aqt.operations, "on_op_finished", lambda *a: None, create=True):
            workflow = _load("ai_generator.workflow", "ai_generator/workflow.py")
            def step(clone, spec, **kwargs):
                clone[spec["target"]] = "first" if spec["target"] == "a" else clone["a"] + "/second"
                return True, None
            token = editor_operation.begin_editor_operation(editor, "workflow")
            with patch.object(workflow, "execute_step", step):
                workflow._execute_steps(editor, note, [{"target": "a"}, {"target": "b"}], token)
                while pending:
                    task, done = pending.pop(0)
                    future = Future()
                    future.set_result(task())
                    done(future)
        self.assertEqual(note.fields, ["first", "first/second"])
        self.assertEqual(web_fields, note.fields)
        self.assertFalse(hasattr(editor, "_anki_toolkit_operation"))


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------

class TestBatchStore(unittest.TestCase):
    def setUp(self):
        self.backfill = _load("ai_generator.batch_backfill",
                              "ai_generator/batch_backfill.py")
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.backfill._PATH = self.tmp.name
        self.backfill._USER_FILES = str(Path(self.tmp.name).parent)
        self.col = "/profiles/A/collection.anki2"
        self.backfill.current_col_id = lambda: self.col

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def _write(self, store):
        with open(self.tmp.name, "w", encoding="utf-8") as f:
            json.dump(store, f)

    def test_other_profiles_batches_are_invisible(self):
        self._write({"batches": [
            {"id": "b1", "col": self.col, "status": "in_progress",
             "map": {"i0": {"nid": 1, "field": "def"}}},
            {"id": "b2", "col": "/profiles/B/collection.anki2",
             "status": "in_progress", "map": {"i0": {"nid": 2, "field": "def"}}},
        ], "jobs": [
            {"id": "j1", "col": "/profiles/B/collection.anki2", "status": "active",
             "nids": [2]},
        ]})

        self.assertEqual([b["id"] for b in self.backfill.pending_batches()], ["b1"])
        self.assertEqual(self.backfill.active_jobs(), [])
        self.assertEqual(self.backfill.inflight_fields(), {(1, "def")})

    def test_openai_queue_counts_every_profile(self):
        """Limit kolejki tokenów jest per organizacja, nie per profil."""
        self._write({"batches": [
            {"id": "b2", "col": "/profiles/B/collection.anki2", "provider": "openai",
             "status": "in_progress", "enq_tokens": 900, "map": {}},
        ]})
        self.assertEqual(self.backfill._pending_openai_tokens(), 900)

    def test_legacy_records_without_owner_are_preserved_but_not_applied(self):
        self._write({"batches": [
            {"id": "old", "status": "in_progress", "map": {}},
        ]})
        self.assertEqual(self.backfill.pending_batches(), [])
        self.assertEqual(len(self.backfill._all_pending()), 1)

    def test_submit_serializes_and_deduplicates_and_keeps_original_owner(self):
        item = {"custom_id": "i0", "nid": 1, "field": "def", "provider": "anthropic",
                "model": "model", "prompt": "test", "temperature": None}
        owner = self.col
        calls = []
        def submit(items, config):
            calls.append(items)
            self.col = "/profiles/B/collection.anki2"
            return self.backfill._new_record("batch", "anthropic", items), None
        with patch.object(self.backfill, "_submit_anthropic", submit), ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(self.backfill.submit, [item, item], {}, owner) for _ in range(2)]
            records = [r for f in futures for r in f.result()[0]]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 1)
        self.assertEqual(records[0]["col"], owner)

    def test_apply_rejects_other_collection_even_with_matching_note_id(self):
        col = types.SimpleNamespace(path=self.col, get_note=lambda nid: self.fail("read wrong note"))
        ended = {"b": {"record": {"col": "/profiles/B/collection.anki2",
                                  "map": {"i0": {"nid": 1, "field": "def"}}},
                       "results": [{"custom_id": "i0", "ok": True, "text": "wrong"}]}}
        self.assertEqual(self.backfill.apply_results(col, ended)["filled"], 0)

    def test_poll_callback_after_profile_switch_does_not_apply(self):
        browser = _load("ai_generator.browser_ui", "ai_generator/browser_ui.py")
        original = types.SimpleNamespace(path=self.col)
        tasks = []
        taskman = types.SimpleNamespace(run_in_background=lambda task, done, **_: tasks.append((task, done)))
        self._write({"batches": [{"id": "b", "col": self.col, "status": "in_progress"}]})
        with patch.object(browser, "get_config", lambda: {}), patch.object(browser.mw, "col", original), \
                patch.object(browser.mw, "taskman", taskman), patch.object(
                    browser.batch_backfill, "apply_results", side_effect=AssertionError("applied after switch")):
            browser.check_pending_batches()
            browser.check_pending_batches()
            self.assertEqual(len(tasks), 1)
            browser.mw.col = types.SimpleNamespace(path="B")
            future = Future()
            future.set_result(({"b": {}}, 0, []))
            tasks[0][1](future)
            self.assertFalse(browser._checking)

    def test_scan_reaches_other_provider_past_full_openai_queue(self):
        browser = _load("ai_generator.browser_ui", "ai_generator/browser_ui.py")
        jobs = [{"id": "j", "nids": [1, 2]}]
        sent = []
        def submit(items, config, **kwargs):
            sent.extend(items)
            return [], []
        def background(task, done, **_):
            future = Future()
            future.set_result(task())
            done(future)
        backfill = browser.batch_backfill
        with patch.object(browser.mw, "col", types.SimpleNamespace(path=self.col, get_note=lambda nid: nid)), \
                patch.object(browser.mw, "taskman", types.SimpleNamespace(run_in_background=background)), \
                patch.multiple(backfill, active_jobs=lambda: jobs, openai_budget_left=lambda cfg: 0,
                               slice_tokens=lambda cfg: 1, job_expired=lambda job: False,
                               inflight_fields=lambda: set(), est_item_tokens=lambda item, cfg: 1,
                               submit=submit, build_items=lambda notes, cfg, **kw: ([{
                                   "nid": notes[0], "field": "def",
                                   "provider": "openai" if notes[0] == 1 else "openrouter"}], 0)):
            browser._advance_jobs({})
            browser._advance_jobs({})
        self.assertEqual([item["provider"] for item in sent], ["openrouter"])


# ---------------------------------------------------------------------------
# Field Splitter
# ---------------------------------------------------------------------------

class TestFieldSplitter(unittest.TestCase):
    def test_source_field_is_never_a_target(self):
        fs = _load("field_splitter", "field_splitter/__init__.py")
        note = FakeNote({"przyklad": "One<br><br>Two", "p2": ""})
        cfg = {"source_field": "przyklad", "separator": "<br><br>",
               "target_fields": "przyklad, p2", "overwrite": True}

        fs._process_note(note, cfg)

        self.assertEqual(note["przyklad"], "One<br><br>Two", "pole źródłowe okrojone")
        self.assertEqual(note["p2"], "One")

    def test_split_still_maps_parts_in_order(self):
        result = splitter.split_field_value("A<br><br>B<br><br>C", "<br><br>",
                                            ["p1", "p2", "p3"])
        self.assertEqual(result, {"p1": "A", "p2": "B", "p3": "C"})


if __name__ == "__main__":
    unittest.main()
