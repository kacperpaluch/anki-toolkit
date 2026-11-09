"""Regresje znalezione w audycie modułu Content (2026-09).

Każdy test pilnuje jednego błędu, który realnie gubił treść, pieniądze albo
wyniki:
  * regeneracja TTS kasowała stare audio zanim nowe powstało,
  * częściowo udany `split_audio` wyglądał na gotowy i nie dało się go dokończyć,
  * wynik z wątku roboczego nadpisywał tekst wpisany w międzyczasie w edytorze,
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
    for sub in ("common", "tts", "ai_generator", "field_splitter", "dictionary"):
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
http = _load("common.http", "common/http.py")
ipa = _load("dictionary.ipa_service", "dictionary/ipa_service.py")


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
    def test_single_never_replaces_text(self):
        """Tryb single pisze sam [sound:] — nie może skasować tekstu pola."""
        for fields, target in (({"ang": "cat", "audio": "moja notatka"}, "audio"),
                               ({"ang": "cat"}, "ang")):
            note = FakeNote(fields)
            task = {"source_field": "ang", "target_field": target, "mode": "single"}
            items, _ctx = processor.build_note_work_items(note, [task], ["v1"])
            self.assertEqual(items, [], fields)
        note = FakeNote({"ang": "cat", "audio": "<br>"})
        task = {"source_field": "ang", "target_field": "audio", "mode": "single"}
        self.assertEqual(len(processor.build_note_work_items(note, [task], ["v1"])[0]), 1)

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

    def test_separate_split_target_is_not_regenerated(self):
        task = {"source_field": "src", "target_field": "copy", "mode": "split",
                "split_separator": "<br><br>"}
        done = FakeNote({"src": "One<br><br>Two",
                         "copy": "One[sound:a.mp3]<br><br>Two[sound:b.mp3]"})
        self.assertEqual(processor.build_note_work_items(done, [task], ["v"])[0], [])
        stale = FakeNote({"src": "One<br><br>Three", "copy": done["copy"]})
        self.assertEqual(len(processor.build_note_work_items(stale, [task], ["v"])[0]), 2)

    def test_split_audio_copies_audio_already_in_the_source(self):
        task = {"source_field": "src", "target_field": "audio", "mode": "split_audio",
                "split_separator": "|"}
        note = FakeNote({"src": "one[sound:dict.mp3]|two", "audio": ""})
        items, ctx = processor.build_note_work_items(note, [task], ["v"])
        self.assertEqual([item["seg_i"] for item in items], [1])
        self.assertTrue(processor.apply_results_to_note(note, items, ctx, {(0, 1): "new.mp3"}))
        self.assertEqual(note["audio"], "[sound:dict.mp3][sound:new.mp3]")
        self.assertEqual(processor.build_note_work_items(note, [task], ["v"])[0], [])

    def test_speech_text_keeps_word_boundaries_and_drops_audio(self):
        task = {"source_field": "ang", "target_field": "audio", "mode": "single"}
        note = FakeNote({"ang": "<div>give</div><div>up</div>[sound:x.mp3] <b>c</b>at", "audio": ""})
        items, _ctx = processor.build_note_work_items(note, [task], ["v"])
        self.assertEqual(items[0]["text"], "give up cat")

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

class TestIpaMarkup(unittest.TestCase):
    def test_nested_markup_keeps_the_whole_transcription(self):
        cambridge = ipa.CambridgeIPAExtractor("water")
        cambridge.feed('<span class="uk dpron-i">/<span class="ipa dipa">ˈwɔː.'
                       '<span class="sp dsp">t</span>ər</span>/</span>')
        self.assertEqual(cambridge.uk_ipa, "ˈwɔː.tər")
        oxford = ipa.OxfordIPAExtractor("water")
        oxford.feed('<div class="phons_br"><span class="phon">/ˈwɔː<span>t</span>ə(r)/</span></div>')
        self.assertEqual(oxford.uk_ipa, "ˈwɔːtə(r)")


class TestSafeRedirects(unittest.TestCase):
    def _follow(self, url):
        import urllib.request
        request = urllib.request.Request("https://n8n.example/rows", headers={
            "X-N8N-API-KEY": "key", "CF-Access-Client-Secret": "secret", "User-Agent": "ua"})
        new = http._SafeRedirectHandler().redirect_request(request, None, 302, "Found", {}, url)
        return {k.lower(): v for k, v in new.header_items()}

    def test_credentials_stay_with_their_origin(self):
        self.assertEqual(self._follow("https://login.example/"), {"user-agent": "ua"})
        self.assertIn("x-n8n-api-key", self._follow("https://n8n.example:443/other"))

    def test_https_downgrade_is_refused(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):
            self._follow("http://n8n.example/rows")


class TestBrowserBatchMerge(unittest.TestCase):
    """Browser batches write only their own changes, into fresh notes."""

    class Col:
        def __init__(self, notes):
            self.notes, self.updated = notes, None

        def get_note(self, nid):
            stored = self.notes[nid]
            copy = FakeNote(dict(zip(stored.keys(), stored.fields)))
            copy.id, copy.mid = nid, stored.mid
            return copy

        def update_notes(self, notes):
            self.updated = notes
            for note in notes:
                self.notes[note.id].fields = list(note.fields)

    def _note(self, nid, **fields):
        note = FakeNote(fields)
        note.id, note.mid = nid, 7
        return note

    def test_changed_note_is_skipped_and_others_saved(self):
        stored = {1: self._note(1, ang="cat", audio=""), 2: self._note(2, ang="dog", audio="")}
        col = self.Col(stored)
        batch = [col.get_note(1), col.get_note(2)]
        before = editor_operation.snapshot_fields(batch)
        for note in batch:
            note["audio"] = f"[sound:{note['ang']}.mp3]"
        stored[2].fields[0] = "hound"  # another operation finished meanwhile
        skipped = []
        editor_operation.merge_detached_notes(col, col, batch, before, skipped)
        self.assertEqual(stored[1]["audio"], "[sound:cat.mp3]")
        self.assertEqual(stored[2].fields, ["hound", ""])
        self.assertEqual(skipped, [2])

    def test_other_profile_is_rejected(self):
        col = self.Col({1: self._note(1, ang="cat")})
        with self.assertRaises(RuntimeError):
            editor_operation.merge_detached_notes(object(), col, [], {}, [])


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
# HTTP
# ---------------------------------------------------------------------------

class TestHttpRequests(unittest.TestCase):
    def test_all_http_methods_share_default_user_agent_and_allow_override(self):
        from io import BytesIO
        calls = []
        def opener(request, timeout):
            calls.append(request)
            return BytesIO(b'{}')
        with patch.object(http, 'urlopen', opener):
            http.fetch_url('https://x/rows')
            http.post_json('https://x/rows', b'{}', {})
            http.post_json('https://x/rows', b'{}', {}, method='PATCH')
            http.post_create('https://x/rows', b'{}', {})
            http.post_json('https://x/rows', b'{}', {'User-Agent': 'custom'})
        self.assertTrue(calls[0].get_header('User-agent'))
        self.assertEqual([r.get_header('User-agent') for r in calls[:4]],
                         [calls[0].get_header('User-agent')] * 4)
        self.assertEqual(calls[-1].get_header('User-agent'), 'custom')

    def test_create_request_is_not_repeated_after_a_timeout(self):
        import urllib.error
        calls = []
        def opener(request, timeout):
            calls.append(request)
            raise TimeoutError("read timed out")
        with patch.object(http, "urlopen", opener):
            self.assertEqual(http.post_create("https://x/batches", b"{}", {})[2], True)
        self.assertEqual(len(calls), 1)
        calls.clear()
        def throttled(request, timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url, 429, "slow down", {}, None)
        with patch.object(http, "urlopen", throttled), patch.object(http.time, "sleep"):
            body, error, uncertain = http.post_create("https://x/batches", b"{}", {}, max_retries=3)
        self.assertEqual((len(calls), uncertain), (3, False))  # 429 = odrzucone, wolno ponowić


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


class TestCliPromptEffort(unittest.TestCase):
    def test_effort_comes_from_each_provider_only(self):
        fg = _load("ai_generator.field_generator", "ai_generator/field_generator.py")
        config = {"providers": {
            "claude_cli": {"model": "opus", "reasoning_effort": "medium"},
            "codex_cli": {"model": "gpt-test", "reasoning_effort": "low"},
        }, "note_types": {"Test": {"task": {
            "target": "def", "provider": "claude_cli", "prompt": "test",
            # Overrides left by older versions are ignored.
            "reasoning_effort": "high", "fallback_provider": "codex_cli",
            "fallback_model": "gpt-test", "fallback_reasoning_effort": "xhigh",
        }}}}
        generator = fg.FieldGenerator(config)
        self.assertIs(generator._resolve_provider("claude_cli"), generator._resolve_provider("claude_cli"))
        note = FakeNote({"def": ""})
        note.note_type = lambda: {"name": "Test"}
        calls = []
        def call(provider, prompt):
            calls.append((provider.__class__.__name__, provider.reasoning_effort))
            return None if isinstance(provider, fg.PROVIDERS["claude_cli"]) else "definition"
        with patch.object(fg.PROVIDERS["claude_cli"], "call_api", call), \
             patch.object(fg.PROVIDERS["codex_cli"], "call_api", call):
            self.assertEqual(generator.process_note(note), {"def": "definition"})
        self.assertEqual(calls, [("ClaudeCLIProvider", "medium"), ("CodexCLIProvider", "low")])

    def test_independent_fields_run_in_parallel_after_dependencies(self):
        import threading
        fg = _load("ai_generator.field_generator", "ai_generator/field_generator.py")
        task = lambda target, prompt: {"target": target, "provider": "claude_cli", "prompt": prompt}
        config = {"parallel_requests": 3, "providers": {"claude_cli": {"model": "opus"}},
                  "note_types": {"Test": {
                      "a": task("a", "A {{def}}"), "def": task("def", "D {{ang}}"),
                      "b": task("b", "B {{def}}"), "c": task("c", "{% if def %}C{% endif %}"),
                  }}}
        note = FakeNote({"ang": "cat", "def": "", "a": "", "b": "", "c": ""})
        note.note_type = lambda: {"name": "Test"}
        barrier = threading.Barrier(2, timeout=5)  # b and c must overlap
        def call(provider, prompt):
            if prompt.startswith("D"):
                return "definition"
            if prompt[0] in "BC":
                barrier.wait()
            return prompt
        with patch.object(fg.PROVIDERS["claude_cli"], "call_api", call):
            changed = fg.FieldGenerator(config).process_note(note)
        # "a" comes before "def" in config, so it keeps the sequential semantics
        # and sees the old (empty) value; later fields see the new one.
        self.assertEqual(changed, {"a": "A ", "def": "definition",
                                   "b": "B definition", "c": "C"})


class TestBrowserAiActions(unittest.TestCase):
    def setUp(self):
        self.browser = _load("ai_generator.browser_ui", "ai_generator/browser_ui.py")
        self.note = FakeNote({"ang": "cat", "def": "old", "manual": "", "audio": ""})
        self.note.note_type = lambda: {"name": "Test"}
        self.config = {"note_types": {"Test": {
            "definition": {"target": "def", "provider": "claude_cli"},
            "extra": {"target": "manual", "provider": "openai", "manual_only": True},
            "invalid": {"target": "missing", "provider": "openai"},
        }, "Other": {"other": {"target": "other", "provider": "openai"}}}}

    def test_menu_scope(self):
        fields = self.browser._selected_target_fields
        self.assertEqual(fields([self.note], self.config), ["def"])
        self.assertEqual(fields([self.note], self.config, True), ["manual"])
        self.note.tags = ["skip-ai"]
        self.config["skip_tags"] = ["skip-ai"]
        self.assertEqual(fields([self.note], self.config), [])

    def test_workflow_scope_checks_actual_fields(self):
        matches = self.browser._workflow_matches
        self.assertTrue(matches([self.note], [{"module": "ai", "action": "generate"}], self.config, {}))
        self.assertFalse(matches([self.note], [{"module": "ai", "action": "generate", "fields": ["missing"]}], self.config, {}))
        self.assertFalse(matches([self.note], [{"module": "field_splitter", "action": "split"}], self.config, {}))

    def test_regeneration_confirmation_and_scope(self):
        b = types.SimpleNamespace(selected_notes=lambda: [1, 2])
        unrelated = FakeNote({"ang": "dog"})
        unrelated.note_type = lambda: {"name": "Other"}
        col = types.SimpleNamespace(get_note=lambda nid: self.note if nid == 1 else unrelated)
        with patch.object(self.browser.mw, "col", col), \
             patch.object(self.browser, "get_config", return_value=self.config), \
             patch.object(self.browser, "askUser", return_value=False) as ask, \
             patch.object(self.browser, "_run_batch") as run:
            self.browser._on_regenerate_browser(b, ["def"])
            run.assert_not_called()
            self.assertIn("1 notatkach", ask.call_args.args[0])
            self.assertTrue(ask.call_args.kwargs["defaultno"])
            ask.return_value = True
            self.browser._on_regenerate_browser(b, ["def"])
            self.assertEqual(run.call_args.args[1], [1])
            self.assertEqual(run.call_args.kwargs["only_fields"], {"def"})
            self.assertTrue(run.call_args.kwargs["overwrite"])

    def test_report_counts_saved_results_after_conflict(self):
        import aqt.utils
        second = FakeNote({"def": "new"}); second.id = 2
        with patch.object(aqt.utils, "showText", create=True) as show:
            self.browser._show_run_report(None, "AI", 3, 3, [self.note, second],
                [(1, "error", "def: timeout"), (3, "skip", "pola mają treść")], False, [2])
            report = show.call_args.args[0]
            self.assertIn("Zapisano zmiany w notatkach: 1", report)
            self.assertIn("Notatki z błędami: 1", report)
            self.assertIn("nid:1 — Błąd: def: timeout", report)
            self.assertIn("nid:2 — nie zapisano", report)

    def test_report_is_kept_and_retries_only_failed_notes(self):
        import aqt.utils
        reports = sys.modules[self.browser.__name__.rsplit(".", 2)[0] + ".common.reports"]
        reports.clear_reports()
        retried = []
        with patch.object(aqt.utils, "showText", create=True):
            self.browser._show_run_report(None, "AI", 3, 3, [],
                [(1, "error", "timeout"), (3, "skip", "pełne"), (2, "error", "x")], False,
                retry=retried.append)
        report = reports.recent_reports()[0]
        self.assertEqual((report["title"], report["failed"]), ("AI", 2))
        self.assertIn("Diagnostyka", report["text"])
        report["retry"]()
        self.assertEqual(retried, [[1, 2]])

    def test_overwrite_failure_preserves_old_field(self):
        generator_module = _load("ai_generator.field_generator", "ai_generator/field_generator.py")
        generator = generator_module.FieldGenerator(self.config)
        provider = types.SimpleNamespace(model="test", last_error="timeout", call_api=lambda _: None)
        with patch.object(generator, "_resolve_provider", return_value=provider):
            self.assertEqual(generator.process_note(self.note, {"def"}, overwrite=True), {})
        self.assertEqual(self.note["def"], "old")
        self.assertIn("timeout", generator.errors[0])


class TestReviewFixes(unittest.TestCase):
    def test_reset_while_reading_body_is_a_failed_fetch_not_an_exception(self):
        class Broken:
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self): raise ConnectionResetError("reset")
        with patch.object(http, "urlopen", lambda request, timeout: Broken()):
            self.assertIsNone(http.fetch_url("https://x/a.mp3", max_retries=1))
            self.assertIsNone(http.post_json("https://x", b"{}", {}, max_retries=1)[0])
            self.assertTrue(http.post_create("https://x", b"{}", {}, max_retries=1)[2])

    def test_field_value_inside_if_block_is_not_rendered_twice(self):
        engine = _load("ai_generator.template_engine", "ai_generator/template_engine.py")
        fields = {"def": "see {{ang}}", "ang": "SECRET"}
        self.assertEqual(engine.render_template("{% if def %}{{def}}{% endif %} {{ang}}", fields),
                         "see {{ang}} SECRET")

    def test_tts_without_key_reports_instead_of_opening_a_dialog_per_note(self):
        # A dialog would crash here: the stubbed mw has no taskman.
        changed, error = processor.process_single_note(None, {"voices": ["a"], "openrouter_api_key": ""})
        self.assertFalse(changed)
        self.assertIn("Brak klucza", error)


if __name__ == "__main__":
    unittest.main()
