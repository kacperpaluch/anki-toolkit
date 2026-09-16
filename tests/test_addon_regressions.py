"""Regression checks for the add-on modules; no Anki, network or user data."""
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
    """Import complete modules with narrow Qt/Anki stubs, isolated from other tests.

    The add-on root is a bare package (its __init__ would wire every hook), but
    `common` is imported for real — modules read their config section through it.
    """
    root = "review_" + addon
    package = root + "." + addon
    folder = ROOT / addon
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
    top = types.ModuleType(root)
    top.__path__ = [str(ROOT)]
    modules[root] = top
    parent = types.ModuleType(package)
    parent.__path__ = [str(folder)]
    parent.__package__ = package
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

    def test_plain_text_is_escaped_unless_html_is_requested(self):
        target = self.module._target
        self.module._apply_fields({"ang": "R&D <b>"}, target, append=True)
        self.assertEqual(self.editor.note["ang"], "word<br><br>R&amp;D &lt;b&gt;")
        self.module._apply_fields({"def": "<i>x</i>"}, target, is_html=True)
        self.assertEqual(self.editor.note["def"], "<i>x</i>")

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
        self.roles = {}
        self._flags = 1

    def data(self, _role): return self.row
    def flags(self): return self._flags
    def setFlags(self, flags): self._flags = flags
    def setCheckState(self, checked): self.checked = checked
    def checkState(self): return self.checked
    def setData(self, role, value): self.roles[role] = value
    def setText(self, text): self.text = text
    def setHidden(self, hidden): self.hidden = hidden
    def isHidden(self): return getattr(self, "hidden", False)


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.module = load("integrations", "panel.py")
        self.module.Qt = types.SimpleNamespace(
            ItemDataRole=types.SimpleNamespace(UserRole=0, ForegroundRole=1, FontRole=2),
            ItemFlag=types.SimpleNamespace(ItemIsUserCheckable=1),
            CheckState=types.SimpleNamespace(Checked=True, Unchecked=False),
            GlobalColor=types.SimpleNamespace(gray=0))
        self.module.QBrush = lambda x: x
        self.module.QFont = lambda: types.SimpleNamespace(setBold=lambda _bold: None)
        self.module.tooltip = lambda *a, **k: None
        self.panel = self.module.WordQueuePanel.__new__(self.module.WordQueuePanel)
        self.item = Item(1)
        self.panel._list = types.SimpleNamespace(count=lambda: 1, item=lambda i: self.item,
                                                currentItem=lambda: self.item,
                                                selectedItems=lambda: [], setEnabled=lambda on: None)
        from tempfile import TemporaryDirectory
        self.state_dir = TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)
        self.panel._state = self.module.QueueState("/test/collection.anki2", {}, self.state_dir.name)
        self.panel._collection = self.module.mw.col
        self.panel._stop_requested = False
        self.panel._progress = types.SimpleNamespace(setText=lambda text: None)
        self.panel._stop_btn = types.SimpleNamespace(setEnabled=lambda on: None)
        self.panel._resume_btn = types.SimpleNamespace(setEnabled=lambda on: None)
        self.panel._marked = set()
        self.panel._picked = set()
        self.panel._local_rows = []
        self.panel._adding = set()
        self.panel._added = {}
        self.panel._next_local_id = 0
        self.panel._busy = False
        self.panel._pending = {}
        self.panel._done_count = 0
        self.panel._refill_generation = self.panel._selection_generation = 0
        self.panel._suspend = False
        self.panel._cfg = {"word_field": "ang", "word_column": "Slowko", "flag_column": "Anki",
                            "ai_fields": {"pl": "pol"}}
        self.panel._hide_done = types.SimpleNamespace(isChecked=lambda: False)
        self.panel._counter = types.SimpleNamespace(setText=lambda _: None)
        self.panel._mark_row_done = lambda *a: (1, None)
        self.editor = Editor()
        self.panel._addcards = types.SimpleNamespace(editor=self.editor)
        self.jobs = []
        self.timers = []
        self.module.QTimer = types.SimpleNamespace(singleShot=lambda _ms, cb: self.timers.append(cb))
        self.module.mw.taskman = types.SimpleNamespace(run_in_background=lambda job, done, **_: self.jobs.append((job, done)))

    def test_choosing_a_word_starts_every_dictionary(self):
        """Wszystkie słowniki naraz — „AI: znaczenia" i tak czyta komplet."""
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._generation = 0
        tabs._labels = ["diki", "Cambridge", "Oxford", "LDoCE"]
        loaded, enabled, current = [], {}, [0]
        tabs._views = [types.SimpleNamespace(load=lambda url, i=i: loaded.append(i))
                       for i in range(4)]
        tabs.setTabEnabled = lambda i, on: enabled.__setitem__(i, on)
        tabs.isTabEnabled = lambda i: enabled.get(i, False)
        tabs.currentIndex = lambda: current[0]
        tabs.setCurrentIndex = lambda i: current.__setitem__(0, i)
        self.module.QUrl = lambda url: url

        tabs.set_urls({"diki": "d", "Cambridge": "c", "Oxford": "o", "LDoCE": "l"})
        self.assertEqual(sorted(loaded), [0, 1, 2, 3])
        self.assertEqual(loaded[0], 0)          # widoczna zakładka rusza pierwsza
        self.assertEqual(tabs._pending, {})     # nic nie czeka na kliknięcie

        loaded.clear()
        tabs.set_urls({"diki": "d", "Oxford": "", "Cambridge": "", "LDoCE": ""})
        self.assertEqual(loaded.count(0), 1)    # tylko diki ma adres
        self.assertFalse(enabled[2])            # reszta wyszarzona

    def test_page_text_never_comes_back_inside_the_engine_callback(self):
        """Wywołujący ładuje kolejną stronę albo otwiera okno — ze środka
        callbacku QtWebEngine to natywny crash Anki, nie wyjątek Pythona."""
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels = ["diki", "Oxford"]
        tabs._generation = 1
        tabs._word = "word"
        tabs._loaded = {0: True, 1: True}
        tabs.isTabEnabled = lambda _i: True
        tabs._views = [types.SimpleNamespace(page=lambda text=text: types.SimpleNamespace(
            runJavaScript=lambda script, callback: callback(text))) for text in ("po polsku", "in english")]
        got = []
        tabs._collect(got.append)
        self.assertFalse(got)                      # jeszcze nie — jesteśmy w callbacku silnika
        self.timers.pop()()
        self.assertEqual(got, [{"diki": "po polsku", "Oxford": "in english"}])

        tabs._loaded = {}                          # nic się nie wczytało: ta ścieżka też odbija
        got.clear()
        tabs._collect(got.append)
        self.assertFalse(got)
        self.timers.pop()()
        self.assertEqual(got, [{}])

    def test_closed_panel_drops_deferred_page_text(self):
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels = ["diki"]
        tabs._generation = 1
        tabs._word = "word"
        tabs._loaded = {0: True}
        tabs.isTabEnabled = lambda _i: True
        tabs._views = [types.SimpleNamespace(page=lambda: types.SimpleNamespace(
            runJavaScript=lambda script, callback: callback("tekst")))]
        tabs._collect(lambda _result: self.fail("zamknięty panel nie może dostać tekstu"))
        tabs.deleted = True                        # okno „Dodaj" zamknięte, zanim timer wystrzelił
        self.timers.pop()()

    def test_stalled_renderer_times_out_once_and_keeps_available_source(self):
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels, tabs._word, tabs._generation = ["diki", "Oxford"], "mother", 1
        tabs._loaded = {0: True, 1: True}
        tabs.isTabEnabled = lambda _i: True
        pending = []
        tabs._views = [types.SimpleNamespace(page=lambda: types.SimpleNamespace(
            runJavaScript=lambda script, cb: cb("matka"))),
            types.SimpleNamespace(page=lambda: types.SimpleNamespace(
                runJavaScript=lambda script, cb: pending.append(cb)))]
        got = []
        tabs._collect(got.append)
        self.assertFalse(got)
        self.timers.pop()()  # extraction deadline
        self.assertEqual(got, [{"diki": "matka"}])
        pending[0]("late English")
        self.assertEqual(got, [{"diki": "matka"}])

    def test_range_selection_does_not_prompt_to_replace_the_headword(self):
        """Qt wysyła currentItemChanged przed selectionChanged — w tej chwili
        zaznaczenie ma jeszcze jeden element i liczenie go tam nic nie daje."""
        items = [Item(1), Item(2)]
        selection = [items[0]]
        current = [items[1]]
        self.panel._list = types.SimpleNamespace(
            count=lambda: 2, item=lambda i: items[i], currentItem=lambda: current[0],
            selectedItems=lambda: selection, setEnabled=lambda on: None)
        prefilled = []
        self.panel._prefill = lambda word, *a, **k: prefilled.append(word)

        self.panel._on_item_changed(items[1], items[0])
        self.assertFalse(prefilled)          # decyzja odłożona, nic jeszcze nie pyta
        selection = [items[0], items[1]]     # Shift dokłada resztę zakresu
        self.timers.pop()()
        self.assertFalse(prefilled)          # paczka: notatka i zakładki bez zmian

        selection = [items[1]]               # zwykły klik w jedną pozycję
        self.panel._on_item_changed(items[1], items[0])
        self.timers.pop()()
        self.assertEqual(prefilled, ["word"])

    def test_stale_selection_callback_is_dropped(self):
        items = [Item(1), Item(2)]
        self.panel._list = types.SimpleNamespace(
            count=lambda: 2, item=lambda i: items[i], currentItem=lambda: items[1],
            selectedItems=lambda: [items[1]], setEnabled=lambda on: None)
        self.panel._prefill = lambda *a, **k: self.fail("nieaktualna pozycja nie może wypełniać notatki")
        self.panel._on_item_changed(items[0], None)  # zanim timer zdążył, wybór poszedł dalej
        self.timers.pop()()

    def batch_panel(self, words):
        """Panel z listą N haseł, wszystkie zaznaczone — tak wygląda paczka."""
        items = [Item(-(i + 1)) for i, _word in enumerate(words)]
        for item, word in zip(items, words):
            item.row["Slowko"] = word
        self.panel._list = types.SimpleNamespace(
            count=lambda: len(items), item=lambda i: items[i],
            currentItem=lambda: items[0], selectedItems=lambda: items,
            setEnabled=lambda on: None, setCurrentRow=lambda i: None)
        self.panel._update_ai_label = lambda: None
        self.enabled = []
        # Kolekcja w tych testach jest atrapą — kontrola duplikatów ma własny test.
        self.module.ai_senses.existing_senses = lambda word, cfg: []
        self.module.ai_senses.find_word_notes = lambda word, cfg: []
        self.module.ai_senses.prepare_provider = lambda cfg: ("provider", None)
        self.panel._ai_btn = types.SimpleNamespace(setEnabled=lambda on: self.enabled.append(on),
                                                   setText=lambda t: None)
        self.panel._local_label = ""
        self.loaded = []
        self.panel._tabs = types.SimpleNamespace(
            set_urls=lambda urls, word="": None,
            setEnabled=lambda on: None,
            whole_page=set(),
            texts=lambda callback: (self.loaded.append(self.panel._shown_word),
                                    callback({"diki": "tekst"}))[0])
        return items

    def test_word_already_in_anki_never_reaches_the_model(self):
        self.batch_panel(["mother", "father"])
        self.module.ai_senses.find_word_notes = lambda word, cfg: [7] if word == "mother" else []
        shown = []
        self.module.tooltip = lambda text, **k: shown.append(text)
        self.module.askUser = lambda *a, **k: False   # declined: nothing is ticked in n8n
        with patch.object(self.module.ai_senses, "pick_senses", return_value=[]):
            self.panel._ai_senses()
            self.answer("ojciec")
        self.assertEqual(self.loaded, ["father"])
        self.assertEqual(len(self.jobs), 1)
        self.assertIn("mother", shown[0])

        self.assertEqual(self.panel._marked, set())
        self.assertNotIn(-1, self.panel._picked)

    def test_accepted_prompt_ticks_known_words_and_continues(self):
        items = self.batch_panel(["mother", "father"])
        self.panel._picked = {-1, -2}
        self.module.ai_senses.find_word_notes = lambda word, cfg: [7] if word == "mother" else []
        asked = []
        self.module.askUser = lambda text, **k: asked.append(text) or True
        with patch.object(self.module.ai_senses, "pick_senses", return_value=[]):
            self.panel._ai_senses()
            self.answer("ojciec")
        self.assertIn("mother", asked[0])
        self.assertEqual(self.panel._marked, {-1})          # local row: ticked at once
        self.assertEqual(self.panel._picked, {-2})          # known word left the AI selection
        self.assertFalse(items[0].checked)
        self.assertEqual(self.panel._state.data["owed"], {})
        self.assertEqual(self.loaded, ["father"])

    def test_accepted_n8n_row_stays_owed_until_patch_succeeds(self):
        items = self.batch_panel(["mother"])
        items[0].row["id"] = 5
        self.module.ai_senses.find_word_notes = lambda word, cfg: [7]
        self.module.askUser = lambda *a, **k: True
        self.panel._ai_senses()
        self.assertEqual(self.panel._state.data["owed"], {"5": "mother"})
        self.finish((0, "offline"))
        self.assertEqual(self.panel._state.data["owed"], {"5": "mother"})  # retried after refill
        self.panel._set_row(items[0], True)
        self.finish((1, None))
        self.assertEqual(self.panel._state.data["owed"], {})
        self.assertEqual(self.panel._marked, {5})

    def test_already_ticked_known_word_is_not_asked_about(self):
        self.batch_panel(["mother"])
        self.panel._marked = {-1}
        self.module.ai_senses.find_word_notes = lambda word, cfg: [7]
        self.module.askUser = lambda *a, **k: self.fail("nothing to tick, nothing to ask")
        self.panel._ai_senses()
        self.assertEqual(self.jobs, [])

    def test_only_known_words_selected_means_no_batch(self):
        self.batch_panel(["mother"])
        self.module.ai_senses.find_word_notes = lambda word, cfg: [7]
        self.panel._ai_senses()
        self.assertEqual((self.loaded, self.jobs, self.enabled), ([], [], []))

    def test_failed_duplicate_check_stops_the_batch(self):
        self.batch_panel(["mother"])
        def broken(word, cfg):
            raise RuntimeError("db")
        self.module.ai_senses.find_word_notes = broken
        with self.assertLogs(level="ERROR"):
            self.panel._ai_senses()
        self.assertEqual((self.loaded, self.jobs), ([], []))

    def test_batch_walks_words_one_at_a_time_and_shows_one_picker(self):
        """Kolejno, nie równolegle: następne hasło rusza dopiero po wyniku poprzedniego."""
        items = self.batch_panel(["mother", "father"])
        picked = []
        with patch.object(self.module.ai_senses, "pick_senses", side_effect=lambda *a: picked.append(a) or []):
            self.panel._ai_senses()
            self.assertEqual(self.loaded, ["mother"])             # drugie hasło jeszcze nie ruszyło
            self.assertEqual(len(self.jobs), 1)
            self.answer("matka")
            self.assertEqual(self.loaded, ["mother", "father"])   # dopiero teraz
            self.assertFalse(picked)                              # okno po ostatnim wyniku
            self.answer("ojciec")
        proposals = picked[0][0]
        self.assertEqual([p["word"] for p in proposals], ["mother", "father"])
        self.assertEqual([p["senses"][0]["pl"] for p in proposals], ["matka", "ojciec"])
        self.assertEqual(self.enabled, [False, True])             # panel zablokowany na czas paczki
        self.assertFalse(self.panel._busy)
        self.assertEqual(self.panel._marked, set())               # anulowany wybór nic nie odhacza

    def answer(self, meaning=None, error=None):
        """Odpowiedź modelu na ostatnio wysłane zadanie."""
        future = Future()
        future.set_result(([] if error else [{"pl": meaning, "match": "none"}], error))
        self.jobs[-1][1](future)

    def test_stop_keeps_completed_word_and_skips_next_request(self):
        self.batch_panel(["mother", "father"])
        with patch.object(self.module.ai_senses, "pick_senses", return_value=[]) as picker:
            self.panel._ai_senses()
            self.panel._stop_batch()
            self.answer("matka")
        self.assertEqual(self.loaded, ["mother"])
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(picker.call_args.args[0][0]["word"], "mother")
        recovered = self.module.QueueState("/test/collection.anki2", {}, self.state_dir.name)
        self.assertEqual(recovered.data["drafts"][0]["senses"][0]["pl"], "matka")
        self.assertFalse(self.panel._busy)

    def test_failed_patch_is_owed_and_settled_after_refill(self):
        self.panel._owe({1: "word"})
        self.panel._set_row(self.item, True)
        self.finish((0, "offline"))
        recovered = self.module.QueueState("/test/collection.anki2", {}, self.state_dir.name)
        self.assertEqual(recovered.data["owed"], {"1": "word"})
        with patch.object(self.module.ai_senses, "find_word_notes", return_value=[42]):
            self.panel._settle_owed()           # cards exist → PATCH again, no AI
        self.finish((1, None))
        self.assertEqual(self.panel._state.data["owed"], {})
        self.assertEqual(self.panel._marked, {1})

    def test_owed_row_without_cards_is_dropped_but_keeps_its_draft(self):
        self.panel._state.data["drafts"] = [{"row_id": 1, "word": "word"}]
        self.panel._owe({1: "word"})
        with patch.object(self.module.ai_senses, "find_word_notes", return_value=[]):
            self.panel._settle_owed()           # crash before commit: nothing to report
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.panel._state.data["owed"], {})
        self.assertEqual(len(self.panel._state.data["drafts"]), 1)

    def test_owed_row_deleted_in_n8n_is_dropped_without_patch(self):
        self.panel._owe({99: "gone"})           # row 99 is no longer in the queue
        with patch.object(self.module.ai_senses, "find_word_notes", return_value=[42]) as find:
            self.panel._settle_owed()
        find.assert_not_called()
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.panel._state.data["owed"], {})

    def test_whole_page_fallback_is_flagged(self):
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels, tabs._word, tabs._generation = ["diki", "Oxford"], "mother", 1
        tabs._loaded = {0: True, 1: True}
        tabs.isTabEnabled = lambda _i: True
        answers = ["matka", {"text": "MENU mother a female parent", "whole": True}]
        tabs._views = [types.SimpleNamespace(page=lambda a=a: types.SimpleNamespace(
            runJavaScript=lambda script, cb: cb(a))) for a in answers]
        got = []
        tabs._collect(got.append)
        self.timers.pop()()
        self.assertEqual(got, [{"diki": "matka", "Oxford": "MENU mother a female parent"}])
        self.assertEqual(tabs.whole_page, {"Oxford"})

    def test_failed_load_and_empty_entry_are_excluded(self):
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels = ["diki", "Oxford", "Cambridge"]
        tabs._generation = 1
        tabs._word = "mother"
        tabs._loaded = {0: False, 1: True, 2: True}
        tabs.isTabEnabled = lambda _i: True
        tabs._views = [types.SimpleNamespace(page=lambda text=text: types.SimpleNamespace(
            runJavaScript=lambda script, callback: callback(text))) for text in ("error", "", "matka")]
        got = []
        tabs._collect(got.append)
        self.timers.pop()()
        self.assertEqual(got, [{"Cambridge": "matka"}])
        tabs._collect(got.append)
        tabs._generation += 1
        self.timers.pop()()
        self.assertEqual(len(got), 1)  # stale extraction cannot advance the next word

    def test_batch_refuses_to_start_without_a_provider(self):
        self.batch_panel(["mother"])
        self.module.ai_senses.prepare_provider = lambda cfg: (None, "wybierz dostawcę AI")
        self.panel._ai_senses()
        self.assertEqual(self.jobs, [])          # żadnego pytania do modelu
        self.assertFalse(self.panel._busy)       # i panel nie zostaje zablokowany

    def test_batch_adds_one_transaction_and_ticks_only_the_added_words(self):
        items = self.batch_panel(["mother", "father"])
        chosen = [("mother", {"pl": "matka", "match": "none"})]
        with patch.object(self.module.ai_senses, "pick_senses", return_value=chosen), \
             patch.object(self.module.ai_senses, "add_notes", return_value=(1, object())) as add, \
             patch.dict(sys.modules, {"aqt.operations": types.SimpleNamespace(on_op_finished=lambda *a: None)}):
            self.panel._ai_senses()
            self.answer("matka")
            self.answer("ojciec")
        add.assert_called_once()
        self.assertEqual(add.call_args.args[1], chosen)
        self.assertEqual(self.panel._marked, {-1})   # „mother" dostało karty → zrobione
        self.assertNotIn(-2, self.panel._marked)     # „father" odznaczone w oknie → zostaje

    def test_failed_word_does_not_sink_the_rest_of_the_batch(self):
        self.batch_panel(["mother", "father"])
        with patch.object(self.module.ai_senses, "pick_senses", return_value=[]) as picker:
            self.panel._ai_senses()
            self.answer(error="brak odpowiedzi modelu")
            self.answer("ojciec")
        self.assertEqual([p["word"] for p in picker.call_args.args[0]], ["father"])

    def test_closed_panel_discards_the_batch(self):
        self.batch_panel(["mother"])
        with patch.object(self.module.ai_senses, "pick_senses") as picker:
            self.panel._ai_senses()
            self.panel.deleted = True
            self.answer("matka")
            picker.assert_not_called()

    def finish(self, value):
        future = Future(); future.set_result(value)
        self.jobs[-1][1](future)

    def test_one_pending_write_and_zero_matches_roll_back(self):
        self.panel._set_row(self.item, True)
        self.panel._set_row(self.item, False)   # drugi zapis czeka na pierwszy
        self.assertEqual(len(self.jobs), 1)
        self.finish((0, None))                  # n8n nie trafił wiersza
        self.assertEqual(self.panel._marked, set())
        self.assertFalse(self.panel._pending)

    def test_callback_updates_rebuilt_item_and_allows_next_write(self):
        self.panel._set_row(self.item, True)
        self.item = Item(1)                     # tasowanie przebudowało listę w trakcie
        self.finish((1, None))
        self.assertEqual(self.panel._marked, {1})
        self.panel._set_row(self.item, False)
        self.finish((1, None))
        self.assertEqual(self.panel._marked, set())

    def test_checkbox_picks_for_ai_and_never_writes_to_n8n(self):
        """Ptaszek zbiera hasła do AI; stan „zrobione" siedzi w kolorze i n8n."""
        self.item.checked = True
        self.panel._update_ai_label = lambda: None
        self.panel._on_item_checked(self.item)
        self.assertEqual(self.panel._picked, {1})
        self.assertEqual(self.jobs, [])          # nic nie poszło do tabeli
        self.assertEqual(self.panel._marked, set())

        self.item.checked = False
        self.panel._on_item_checked(self.item)
        self.assertEqual(self.panel._picked, set())

    def test_picked_row_is_visible_without_hunting_for_the_checkbox(self):
        """Przy kilkuset pozycjach sam checkbox ginie — wybór ma być widać w wierszu."""
        self.item.checked = True
        self.panel._update_ai_label = lambda: None
        self.panel._on_item_checked(self.item)
        self.assertIsNotNone(self.item.roles[2])          # FontRole: pogrubione
        self.assertIsNone(self.item.roles[1])             # ForegroundRole: nie zrobione
        # Wskaźnik checkboxa rysuje motyw i bywa niewidoczny — tekst renderuje się zawsze
        self.assertEqual(self.item.text, "☑ word")
        self.item.checked = False
        self.panel._on_item_checked(self.item)
        self.assertIsNone(self.item.roles[2])
        self.assertEqual(self.item.text, "word")

    def test_newest_first_puts_the_words_you_just_added_on_top(self):
        """`id` rośnie z każdym dopisanym wierszem, a wiersz lokalny jest najnowszy."""
        rows = [{"id": 3}, {"id": 1}, {"id": -1}, {"id": 7}]
        self.panel._cfg["order"] = "id"
        self.assertEqual([r["id"] for r in self.panel._ordered(rows)], [1, 3, 7, -1])
        self.panel._cfg["order"] = "new"
        self.assertEqual([r["id"] for r in self.panel._ordered(rows)], [-1, 7, 3, 1])
        self.panel._cfg["order"] = "random"
        self.assertEqual(sorted(r["id"] for r in self.panel._ordered(rows)), [-1, 1, 3, 7])

    def test_picked_rows_win_over_the_highlight(self):
        items = [Item(1), Item(2)]
        self.panel._list = types.SimpleNamespace(
            count=lambda: 2, item=lambda i: items[i], currentItem=lambda: items[0],
            selectedItems=lambda: [items[0]], setEnabled=lambda on: None)
        self.assertEqual([r["id"] for r in self.panel._selected_rows()], [1])  # bez ptaszków
        self.panel._picked = {2}
        self.assertEqual([r["id"] for r in self.panel._selected_rows()], [2])

    def test_old_refill_cannot_overwrite_new_refill(self):
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

    def test_new_words_are_written_to_the_table(self):
        rebuilt = []
        self.panel._rebuild = rebuilt.append
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None,
                                                 setCurrentRow=lambda i: None)
        self.panel._select_word = lambda word: None
        self.panel._add_local_rows(self.module.word_queue.parse_words("mother, give up"))
        self.assertFalse(rebuilt)                    # najpierw zapis, potem lista
        self.finish(([{"id": 7, "Slowko": "mother"}, {"id": 8, "Slowko": "give up"}], None))
        self.assertEqual([row["id"] for row in rebuilt[0]], [7, 8])
        self.assertEqual(self.panel._local_rows, [])  # prawdziwe wiersze, nie zastępcze

    def test_word_being_written_is_not_written_again(self):
        """Zapis trwa, hasła nie ma jeszcze na liście — drugie wklejenie musi je pominąć."""
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None,
                                                 setCurrentRow=lambda i: None)
        self.panel._rebuild = lambda rows: None
        self.panel._select_word = lambda word: None
        self.panel._add_local_rows(["mother"])
        self.assertEqual(len(self.jobs), 1)
        self.panel._add_local_rows(["Mother"])           # w trakcie zapisu, inna wielkość liter
        self.assertEqual(len(self.jobs), 1)              # nadal jedno żądanie
        self.finish(([{"id": 7, "Slowko": "mother"}], None))
        self.assertEqual(self.panel._adding, set())      # po odpowiedzi blokada znika

    def test_words_already_on_the_list_are_not_written_again(self):
        """Panel trzyma całą tabelę, więc to jest zarazem kontrola duplikatów w n8n."""
        existing = Item(3)
        existing.row["Slowko"] = "Mother"
        self.panel._list = types.SimpleNamespace(count=lambda: 1, item=lambda i: existing,
                                                 currentItem=lambda: existing,
                                                 setCurrentRow=lambda i: None)
        self.panel._select_word = lambda word: None
        self.panel._add_local_rows(["mother"])        # inna wielkość liter, to samo hasło
        self.assertEqual(self.jobs, [])

    def test_failed_write_leaves_the_words_usable_in_the_panel(self):
        """Offline: hasła zostają jako wiersze lokalne (ujemne id), bez PATCH-a."""
        rebuilt = []
        self.panel._rebuild = rebuilt.append
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None,
                                                 setCurrentRow=lambda i: None)
        self.panel._select_word = lambda word: None
        self.panel._add_local_rows(["mother", "give up"])
        self.finish(([], "Connection error"))
        self.assertEqual([row["id"] for row in rebuilt[0]], [-1, -2])
        self.assertEqual([row["id"] for row in self.panel._local_rows], [-1, -2])

        local = Item(-1)
        self.panel._list = types.SimpleNamespace(count=lambda: 1, item=lambda i: local,
                                                 currentItem=lambda: local)
        self.jobs.clear()
        self.panel._set_row(local, True)
        self.assertEqual(self.jobs, [])                  # odhaczanie nie ma czego wysłać
        self.assertEqual(self.panel._marked, {-1})
        self.panel._set_row(local, False)                # pomyłkę dalej da się cofnąć
        self.assertEqual(self.panel._marked, set())

    def test_words_survive_closing_the_panel_during_a_failed_write(self):
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None)
        self.panel._add_local_rows(["mother"])
        self.panel.deleted = True                        # okno „Dodaj” zamknięte
        self.module.word_queue._panel = None
        self.finish(([], "Connection error"))
        again = self.module.QueueState("/test/collection.anki2", {}, self.state_dir.name)
        self.assertEqual([row["Slowko"] for row in again.data["local_rows"]], ["mother"])

    def test_refill_started_before_a_write_keeps_the_new_row(self):
        rebuilt = []
        self.panel._rebuild = rebuilt.append
        self.panel._settle_owed = lambda: None
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None)
        self.panel.refill()
        refill_done = self.jobs[-1][1]
        self.panel._add_local_rows(["mother"])
        self.finish(([{"id": 7, "Slowko": "mother"}], None))
        future = Future(); future.set_result(([{"id": 5, "Slowko": "cat"}], None))
        refill_done(future)                              # GET sprzed zapisu kończy się później
        self.assertEqual([row["id"] for row in rebuilt[-1]], [5, 7])
        self.jobs.clear()
        self.panel._add_local_rows(["Mother"])           # nadal „już na liście”
        self.assertEqual(self.jobs, [])

    def test_ticked_local_row_is_ticked_on_its_n8n_row(self):
        self.panel._local_rows[:] = [{"id": -1, "Slowko": "mother", "Anki": True}]
        self.panel._state.data["local_rows"] = self.panel._local_rows
        self.panel._marked = {-1}
        self.panel._rebuild = lambda rows: None
        self.panel._settle_owed = lambda: None
        self.panel.refill()
        future = Future(); future.set_result(([{"id": 9, "Slowko": "mother", "Anki": False}], None))
        self.jobs[-1][1](future)
        self.assertEqual(self.panel._pending, {9: True})  # PATCH „zrobione” wysłany
        self.assertEqual(self.panel._state.data["owed"], {"9": "mother"})

    def test_cards_are_not_added_when_the_debt_cannot_be_saved(self):
        added = []
        self.module.ai_senses.existing_senses = lambda *a: []
        self.module.ai_senses.pick_senses = lambda *a: [("mother", {"reviewed": True})]
        self.module.ai_senses.add_notes = lambda *a: added.append(a) or (1, None)
        self.panel._addcards.editor.note = {}
        self.panel._set_busy = lambda busy: None
        self.panel._state.save = lambda: (_ for _ in ()).throw(OSError("disk"))
        self.panel._finish_batch([{"word": "mother", "row_id": 3, "senses": []}], [], self.module.mw.col)
        self.assertEqual(added, [])
        self.assertEqual(self.panel._state.data["owed"], {})

    def test_refill_keeps_local_rows_and_their_ticks(self):
        self.panel._local_rows = [{"id": -1, "Slowko": "mother"}]
        self.panel._marked = {-1}
        rebuilt = []
        self.panel._rebuild = rebuilt.append
        self.panel.refill()
        future = Future(); future.set_result(([{"id": 5, "Anki": True}], None)); self.jobs[0][1](future)
        self.assertEqual([row["id"] for row in rebuilt[0]], [5, -1])
        self.assertEqual(self.panel._marked, {5, -1})

    def test_walking_the_list_does_not_ask_about_an_empty_note(self):
        """Hasło w polu wpisał panel przy poprzednim kliknięciu — nie ma czego bronić."""
        asked = []
        self.module.askUser = lambda *a, **k: asked.append(a) or True
        self.editor.note = {"ang": "curb", "def": "", "pol": ""}
        self.editor.web = types.SimpleNamespace(fields=dict(self.editor.note))
        self.panel._prefill("general election", confirm=True); self.editor.callback()
        self.assertFalse(asked)
        self.assertEqual(self.editor.note["ang"], "general election")

        self.editor.note["pol"] = "ograniczać"   # zacząłeś pisać notatkę
        self.editor.web.fields = dict(self.editor.note)
        self.panel._prefill("curb", confirm=True); self.editor.callback()
        self.assertTrue(asked)                   # teraz pytanie ma sens

    def test_unrelated_note_does_not_mark_current_row(self):
        self.panel._bound_note = self.editor.note
        self.panel._bound_row_id = 1
        self.editor.note["ang"] = "unrelated"
        self.panel.note_added(self.editor.note)
        self.assertFalse(self.jobs)


class AttributeConsistencyTests(unittest.TestCase):
    """Literówka w `self._cos` w kodzie Qt wychodzi dopiero przy otwarciu okna.

    Testy nie budują widgetów, więc `_build_ui` i inne metody Qt nie mają żadnego
    pokrycia. To najtańsza siatka: każdy czytany atrybut `self._x` musi być gdzieś
    w tej samej klasie zapisany albo być jej metodą.
    """

    def test_every_private_attribute_is_assigned_somewhere_in_its_class(self):
        unknown = {}
        # Two levels: providers/ inherits helpers from a base class this check cannot see.
        paths = [*ROOT.glob("*.py"), *ROOT.glob("*/*.py")]
        for path in sorted(p for p in paths if p.parent.name not in ("tests", "workload_service")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for cls in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
                stored = {node.name for node in cls.body
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                stored |= {target.id for node in cls.body if isinstance(node, ast.Assign)
                           for target in node.targets if isinstance(target, ast.Name)}
                stored |= {node.target.id for node in cls.body
                           if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
                loaded = set()
                for node in ast.walk(cls):
                    if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                            and node.value.id == "self"):
                        (stored if isinstance(node.ctx, ast.Store) else loaded).add(node.attr)
                missing = sorted(a for a in loaded - stored if a.startswith("_"))
                if missing:
                    unknown[f"{path.relative_to(ROOT)}::{cls.name}"] = missing
        self.assertEqual(unknown, {})


class OtherAddonsTests(unittest.TestCase):
    def test_old_host_is_not_used_after_config_change(self):
        module = load("integrations", "word_queue.py")
        module._active_url = "https://old.example"
        self.assertEqual(module._base_urls({"n8n_url": "https://new.example/", "fallback_url": ""}), ["https://new.example"])

    def test_cloudflare_access_token_goes_only_to_https(self):
        module = load("integrations", "word_queue.py")
        cfg = {"api_key": "k", "cf_client_id": "id", "cf_client_secret": "sec"}
        https = module._headers(cfg, "https://n8n.example.com/api")
        self.assertEqual((https["CF-Access-Client-Id"], https["CF-Access-Client-Secret"]), ("id", "sec"))
        self.assertNotIn("CF-Access-Client-Secret", module._headers(cfg, "http://192.168.1.5:5678/api"))
        self.assertNotIn("CF-Access-Client-Id", module._headers({**cfg, "cf_client_secret": ""}, "https://x"))

    def test_cloudflare_login_page_gets_a_clear_error(self):
        module = load("integrations", "word_queue.py")
        self.assertIn("Cloudflare Access", module._json(b"<!DOCTYPE html>")[1])
        self.assertEqual(module._json(b'[{"id": 1}]'), ([{"id": 1}], None))

    def test_empty_rules_stay_empty_and_missing_rules_use_template(self):
        module = load("html_cleanup")
        module.mw.addonManager.getConfig = lambda _: {"html_cleanup": {"rules": []}}
        self.assertEqual(module.get_config()["rules"], [])
        module.mw.addonManager.getConfig = lambda _: {}
        template = json.loads((ROOT / "config.json").read_text())
        self.assertEqual(module.get_config()["rules"], template["html_cleanup"]["rules"])

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

    def test_field_hider_indices_follow_note_type_order(self):
        module = load("field_hider")
        self.assertEqual(module.indices_to_hide(["front", "back", "audio"], ["back", "audio"]), [1, 2])
        self.assertEqual(module.indices_to_hide(["front"], ["missing"]), [])

    def test_section_config_keeps_unknown_keys(self):
        module = load("field_hider")
        mw = module.get_module_config.__globals__["mw"]  # common.config reads the profile
        mw.addonManager.getConfig = lambda _: {
            "field_hider": {"hidden_fields": {"Basic": ["Back"]}, "future_option": True}}
        self.assertEqual(module.get_config()["future_option"], True)
        self.assertEqual(module.get_config()["hidden_fields"], {"Basic": ["Back"]})

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
        module.mw.taskman = types.SimpleNamespace(run_in_background=lambda task, done, **_: jobs.append(done))
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
            with tempfile.TemporaryDirectory() as temp:
                media = Path(temp, "collection.media"); media.mkdir()
                with patch.object(module, "_stamp", side_effect=stamps), \
                        patch.object(module, "_run_ffmpeg", return_value=True), \
                        patch.object(module.os, "replace") as replace:
                    self.assertEqual(module.normalize_file(str(media / "audio.mp3"), "ffmpeg", "filter", check),
                                     (False, None))
                    replace.assert_not_called()
                self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ["collection.media"])

    def test_normalizer_temp_file_never_touches_other_media(self):
        module = load("audio_normalizer", "logic.py")
        def fake_ffmpeg(args, _cancel=None):
            Path(args[-1]).write_bytes(b"normalized")
            return True
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp, "collection.media"); media.mkdir()
            (media / "clip.mp3").write_bytes(b"raw")
            (media / "clip.mp3.temp.mp3").write_bytes(b"someone else's recording")
            with patch.object(module, "_run_ffmpeg", side_effect=fake_ffmpeg):
                ok, _stamp = module.normalize_file(str(media / "clip.mp3"), "ffmpeg", "filter")
            self.assertTrue(ok)
            self.assertEqual((media / "clip.mp3").read_bytes(), b"normalized")
            self.assertEqual((media / "clip.mp3.temp.mp3").read_bytes(), b"someone else's recording")
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ["collection.media"])

    def test_ffmpeg_is_killed_on_cancel_and_deadline(self):
        module = load("audio_normalizer", "logic.py")
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        self.assertFalse(module._run_ffmpeg(sleeper, lambda: True))
        with self.assertRaises(TimeoutError):
            module._run_ffmpeg(sleeper, None, timeout=0.1)


class BridgeOriginTests(unittest.TestCase):
    """Strona czytnika ma własny origin — wpuszczamy ją, ale nie całego localhosta."""

    def setUp(self):
        self.module = load("integrations", "bridge.py")
        self.module._bound_port = 8767

    def test_own_page_allowed(self):
        self.assertTrue(self.module._origin_allowed("http://127.0.0.1:8767"))

    def test_other_local_port_rejected(self):
        self.assertFalse(self.module._origin_allowed("http://127.0.0.1:3000"))
        self.assertFalse(self.module._origin_allowed("http://localhost:8767"))

    def test_dictionary_sites_still_allowed(self):
        self.assertTrue(self.module._origin_allowed("https://www.diki.pl"))
        self.assertFalse(self.module._origin_allowed("https://evil.example"))

    def test_before_bind_no_local_origin(self):
        self.module._bound_port = None
        self.assertFalse(self.module._origin_allowed("http://127.0.0.1:8767"))


if __name__ == "__main__":
    unittest.main()
