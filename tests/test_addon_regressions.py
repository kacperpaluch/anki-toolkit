"""Regression checks for the standalone add-ons; no Anki, network or user data."""
import ast
import importlib.util
import json
import queue
import sys
import tempfile
import types
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Widget:
    pass


def load(addon, filename="__init__.py"):
    """Import complete modules with narrow Qt/Anki stubs, isolated from other tests."""
    package = "review_" + addon
    folder = ROOT / ("anki_toolkit_" + addon)
    modules = {}
    for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.operations", "aqt.browser", "anki", "anki.collection"):
        modules[name] = types.ModuleType(name)
    mw = types.SimpleNamespace(col=object(), addonManager=types.SimpleNamespace(getConfig=lambda _: {}))
    modules["aqt"].mw = mw
    modules["aqt"].gui_hooks = types.SimpleNamespace(**{
        name: [] for name in ("editor_did_load_note", "editor_did_init_buttons", "profile_did_open",
                             "profile_will_close", "main_window_did_init", "browser_will_show_context_menu",
                             "sync_did_finish", "add_cards_did_init", "add_cards_will_add_note")})
    modules["aqt.qt"].__getattr__ = lambda _: Widget
    modules["aqt.qt"].sip = types.SimpleNamespace(isdeleted=lambda obj: getattr(obj, "deleted", False))
    modules["aqt.utils"].__getattr__ = lambda _: lambda *a, **k: None
    modules["aqt.operations"].CollectionOp = Widget
    modules["aqt.browser"].Browser = Widget
    modules["anki.collection"].Collection = Widget
    modules["anki.collection"].OpChanges = Widget
    parent = types.ModuleType(package)
    parent.__path__ = [str(folder)]
    modules[package] = parent
    name = package if filename == "__init__.py" else package + "." + Path(filename).stem
    spec = importlib.util.spec_from_file_location(name, folder / filename)
    module = importlib.util.module_from_spec(spec)
    modules[name] = module
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class Editor:
    def __init__(self):
        self.addMode = True
        self.note = {"ang": "word", "def": "old"}
        self.web = types.SimpleNamespace(fields={"ang": "word", "def": "unsaved text"})
        self.parentWindow = types.SimpleNamespace(activateWindow=lambda: None)
        self.callback = None

    def saveNow(self, callback):
        self.note.update(self.web.fields)
        self.callback = callback

    def loadNote(self):
        self.web.fields = dict(self.note)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.module = load("integrations", "bridge.py")
        self.editor = Editor()
        self.module.track_editor(self.editor)
        self.queue = queue.Queue()
        self.module.mw.taskman = types.SimpleNamespace(run_on_main=self.queue.put)

    def test_save_before_apply_preserves_other_fields(self):
        with ThreadPoolExecutor() as pool:
            result = pool.submit(self.module._run_on_main_sync, {"ang": "new"})
            self.queue.get(timeout=1)()
            self.editor.callback()
            self.assertIsNone(result.result(timeout=1))
        self.assertEqual(self.editor.web.fields, {"ang": "new", "def": "unsaved text"})

    def test_timeout_cancels_queued_start(self):
        self.assertIsNotNone(self.module._run_on_main_sync({"ang": "new"}, timeout=0))
        self.queue.get_nowait()()
        self.assertIsNone(self.editor.callback)
        self.assertEqual(self.editor.note["ang"], "word")

    def test_timeout_cancels_pending_save_callback(self):
        with ThreadPoolExecutor() as pool:
            result = pool.submit(self.module._run_on_main_sync, {"ang": "new"}, timeout=.05)
            self.queue.get(timeout=1)()
            self.assertIsNotNone(result.result(timeout=1))
            self.editor.callback()
        self.assertEqual(self.editor.note["ang"], "word")

    def test_profile_switch_rejects_saved_callback(self):
        with ThreadPoolExecutor() as pool:
            result = pool.submit(self.module._run_on_main_sync, {"ang": "new"})
            self.queue.get(timeout=1)()
            self.module.mw.col = object()
            self.editor.callback()
            self.assertIsNotNone(result.result(timeout=1))
        self.assertEqual(self.editor.note["ang"], "word")


class Item:
    def __init__(self, row_id):
        self.row = {"id": row_id, "Slowko": "word"}
        self.checked = False
        self._flags = 1

    def data(self, _role): return self.row
    def flags(self): return self._flags
    def setFlags(self, flags): self._flags = flags
    def setCheckState(self, checked): self.checked = checked
    def checkState(self): return self.checked
    def setData(self, *args): pass
    def setHidden(self, hidden): pass


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.module = load("integrations", "panel.py")
        self.module.Qt = types.SimpleNamespace(
            ItemDataRole=types.SimpleNamespace(UserRole=0, ForegroundRole=1),
            ItemFlag=types.SimpleNamespace(ItemIsUserCheckable=1),
            CheckState=types.SimpleNamespace(Checked=True, Unchecked=False),
            GlobalColor=types.SimpleNamespace(gray=0))
        self.module.QBrush = lambda x: x
        self.module.tooltip = lambda *a, **k: None
        self.panel = self.module.WordQueuePanel.__new__(self.module.WordQueuePanel)
        self.item = Item(1)
        self.panel._list = types.SimpleNamespace(count=lambda: 1, item=lambda i: self.item,
                                                currentItem=lambda: self.item)
        self.panel._marked = set()
        self.panel._pending = {}
        self.panel._done_count = 0
        self.panel._refill_generation = self.panel._selection_generation = 0
        self.panel._suspend = False
        self.panel._cfg = {"word_field": "ang", "word_column": "Slowko", "flag_column": "Anki"}
        self.panel._hide_done = types.SimpleNamespace(isChecked=lambda: False)
        self.panel._counter = types.SimpleNamespace(setText=lambda _: None)
        self.panel._mark_row_done = lambda *a: (1, None)
        self.editor = Editor()
        self.panel._addcards = types.SimpleNamespace(editor=self.editor)
        self.jobs = []
        self.module.mw.taskman = types.SimpleNamespace(run_in_background=lambda job, done: self.jobs.append((job, done)))

    def test_ai_result_is_discarded_after_selection_change(self):
        self.panel._ai_btn = types.SimpleNamespace(setEnabled=lambda enabled: None)
        callbacks = []
        self.panel._tabs = types.SimpleNamespace(texts=callbacks.append)
        with patch.object(self.module.ai_senses, "pick_senses") as picker:
            self.panel._ai_senses()
            callbacks[0]({"diki": "tekst"})
            self.panel._selection_generation += 1
            self.finish(([{"pl": "test"}], None))
            picker.assert_not_called()
        self.assertFalse(self.panel._pending)

    def test_ai_does_not_start_with_stale_pages(self):
        self.panel._ai_btn = types.SimpleNamespace(setEnabled=lambda enabled: None)
        callbacks = []
        self.panel._tabs = types.SimpleNamespace(texts=callbacks.append)
        self.panel._ai_senses()
        self.panel._selection_generation += 1
        callbacks[0]({"diki": "inne słowo"})
        self.assertEqual(self.jobs, [])

    def finish(self, value):
        future = Future(); future.set_result(value)
        self.jobs[-1][1](future)

    def test_one_pending_write_and_zero_matches_roll_back(self):
        self.panel._set_row(self.item, True)
        self.panel._set_row(self.item, False)
        self.assertEqual(len(self.jobs), 1)
        self.assertTrue(self.item.checked)
        self.finish((0, None))
        self.assertFalse(self.item.checked)
        self.assertEqual(self.panel._marked, set())
        self.assertFalse(self.panel._pending)

    def test_callback_updates_rebuilt_item_and_allows_next_write(self):
        self.panel._set_row(self.item, True)
        self.item = Item(1)
        self.finish((1, None))
        self.assertTrue(self.item.checked)
        self.panel._set_row(self.item, False)
        self.finish((1, None))
        self.assertFalse(self.item.checked)
        self.assertEqual(self.panel._marked, set())

    def test_old_refill_cannot_overwrite_new_refill(self):
        self.panel._shuffle = types.SimpleNamespace(isChecked=lambda: False)
        self.panel._rebuild = lambda rows: self.assertEqual(rows, [{"id": 2}])
        self.panel.refill(); self.panel.refill()
        future = Future(); future.set_result(([{"id": 1}], None)); self.jobs[0][1](future)
        future = Future(); future.set_result(([{"id": 2}], None)); self.jobs[1][1](future)

    def test_prefill_preserves_unsaved_fields_and_confirms_replacement(self):
        self.module.askUser = lambda *a, **k: False
        self.panel._prefill("new", confirm=True); self.editor.callback()
        self.assertEqual(self.editor.note["ang"], "word")
        self.module.askUser = lambda *a, **k: True
        self.panel._prefill("new", confirm=True); self.editor.callback()
        self.assertEqual(self.editor.web.fields["def"], "unsaved text")
        self.assertEqual(self.editor.note["ang"], "new")

    def test_unrelated_note_does_not_mark_current_row(self):
        self.panel._bound_note = self.editor.note
        self.panel._bound_row_id = 1
        self.editor.note["ang"] = "unrelated"
        self.panel.note_added(self.editor.note)
        self.assertFalse(self.jobs)


class OtherAddonsTests(unittest.TestCase):
    def test_old_host_is_not_used_after_config_change(self):
        module = load("integrations", "word_queue.py")
        module._active_url = "https://old.example"
        self.assertEqual(module._base_urls({"n8n_url": "https://new.example/", "fallback_url": ""}), ["https://new.example"])

    def test_empty_rules_stay_empty_and_old_defaults_migrate(self):
        module = load("html_cleanup")
        module.mw.addonManager.getConfig = lambda _: {"rules": []}
        self.assertEqual(module.get_config()["rules"], [])
        module.mw.addonManager.getConfig = lambda _: {"rules": module.legacy_default_rules()}
        self.assertEqual(module.get_config()["rules"], module.default_rules())
        template = json.loads((ROOT / "anki_toolkit_html_cleanup/config.json").read_text())
        self.assertEqual(template["rules"], module.default_rules())

    def test_cleaning_before_add_has_no_collection_write(self):
        module = load("html_cleanup")
        module._tooltip = lambda *args: None
        note = {"def": "one<div>two</div>"}
        self.assertIsNone(module._on_add_note(None, note))
        self.assertEqual(note["def"], "one<br>two")
        self.assertIn(module._on_add_note, module.gui_hooks.add_cards_will_add_note)

    def test_growth_error_leaves_whole_note_untouched(self):
        module = load("html_cleanup")
        note = {"first": "a", "second": "x" * 1000}
        before = dict(note)
        rules = [{"find": "a", "to": "b"}, {"find": "x", "to": "xx", "repeat": True}]
        with self.assertRaises(ValueError):
            module._clean_note(note, rules)
        self.assertEqual(note, before)

    def test_regex_backreference_growth_is_rejected_before_expansion(self):
        module = load("html_cleanup", "cleaning.py")
        with self.assertRaises(ValueError):
            module.clean_field("f", "x" * 1000, [{"find": "(.+)", "to": r"\1" * 2000, "regex": True}])

    def test_sync_scan_rejects_closed_or_changed_collection(self):
        module = load("audio_embed")
        module._collection_note_ids = lambda _: self.fail("must not read collection")
        module._run_sync_scan(None)
        module._run_sync_scan(object())

    def test_audio_has_controls_and_escaped_url(self):
        module = load("audio_embed", "logic.py")
        converted = module.convert_text('[sound:part#1.mp3]', 'class"quote')
        self.assertIn("<audio controls ", converted)
        self.assertIn('src="part%231.mp3"', converted)
        self.assertIn("class&quot;quote", converted)
        self.assertEqual(module.convert_text(converted), converted)
        legacy = '<audio class="ex-audio" src="old.mp3" preload="none"></audio>'
        self.assertIn('<audio controls ', module.convert_text(legacy))
        foreign = legacy.replace('ex-audio', 'custom-player')
        self.assertEqual(module.convert_text(foreign), foreign)

    def test_history_is_scoped_and_keeps_other_collection(self):
        module = load("audio_normalizer", "logic.py")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            a, b = path / "A", path / "B"
            a.mkdir(); b.mkdir()
            self.assertNotEqual(module.history_path(str(a)), module.history_path(str(b)))
            with patch.object(module, "history_path", side_effect=lambda d: path / (Path(d).name + ".json")):
                module.save_history(str(a), {"file.mp3": [1, 2]})
                module.process_media_dir(str(b))
                self.assertEqual(module.load_history(str(a)), {"file.mp3": [1, 2]})

    def test_watcher_retains_events_during_normalization_and_stops(self):
        module = load("audio_normalizer")
        events = []
        timer = types.SimpleNamespace(start=lambda: events.append("start"), stop=lambda: events.append("stop"), deleteLater=lambda: None)
        module._timer = timer
        module._normalizing = True
        module._changed("media")
        self.assertTrue(module._rescan)
        module._stop_watcher()
        self.assertIsNone(module._timer)
        self.assertIn("stop", events)

    def test_normalizer_completion_is_profile_bound_and_schedules_rescan(self):
        module = load("audio_normalizer")
        original = types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: "/original"))
        module.mw.col = original
        jobs, syncs, scans = [], [], []
        module.mw.taskman = types.SimpleNamespace(run_in_background=lambda task, done: jobs.append(done))
        module.which = lambda _: "/ffmpeg"
        module._sync_media = lambda *args: syncs.append(args)
        module._timer = types.SimpleNamespace(start=lambda: scans.append(True))
        module.run_normalization(automatic=True)
        module._changed("media")
        module.mw.col = object()
        future = Future(); future.set_result((1, 0, ["file.mp3"]))
        jobs[0](future)
        self.assertFalse(syncs)
        self.assertFalse(module._normalizing)
        self.assertTrue(scans)

    def test_normalizer_does_not_replace_cancelled_or_changed_input(self):
        module = load("audio_normalizer", "logic.py")
        for cancel, stamps in ((lambda: False, [[1, 10], [2, 10]]), (None, [[1, 10]])):
            cancellation = iter((False, True))
            check = cancel or (lambda: next(cancellation))
            with patch.object(module, "_stamp", side_effect=stamps), \
                    patch.object(module.subprocess, "run"), \
                    patch.object(module.os, "remove") as remove, \
                    patch.object(module.os, "replace") as replace:
                self.assertEqual(module.normalize_file("/tmp/audio.mp3", "ffmpeg", "filter", check), (False, None))
                replace.assert_not_called()
                remove.assert_called_once()

    def test_learning_reuses_suffixed_filtered_deck(self):
        module = load("learning")
        base = module.get_config()["deck_name"] + " — " + module.PRESETS[0][0]
        filtered = {"id": 2, "dyn": 1, "terms": [["", 0, 0]]}
        module.mw.col = types.SimpleNamespace(decks=types.SimpleNamespace(
            by_name=lambda name: {"id": 1, "dyn": 0} if name == base else filtered,
            get=lambda _: filtered, save=lambda _: None, select=lambda _: None,
            new_filtered=lambda _: self.fail("must reuse")),
            sched=types.SimpleNamespace(rebuild_filtered_deck=lambda _: None))
        module.mw.reset = lambda: None
        module.showInfo = lambda msg: self.fail(msg)
        module.create_filtered_deck(0)
        self.assertFalse(filtered["resched"])

    def test_local_sources_preserves_nested_unknown_keys(self):
        tree = ast.parse((ROOT / "anki_toolkit_local_sources/__init__.py").read_text())
        tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "save_config"]
        saved = []
        env = {"_name": lambda: "test", "mw": types.SimpleNamespace(addonManager=types.SimpleNamespace(
            getConfig=lambda _: {"oxford": {"future": 42, "match_field": "old"}},
            writeConfig=lambda _, cfg: saved.append(cfg)))}
        exec(compile(tree, "local_sources", "exec"), env)
        env["save_config"]({"oxford": {"match_field": "new"}})
        self.assertEqual(saved[0]["oxford"], {"future": 42, "match_field": "new"})


if __name__ == "__main__":
    unittest.main()
