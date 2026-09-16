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
        self.panel._marked = set()
        self.panel._picked = set()
        self.panel._local_rows = []
        self.panel._adding = set()
        self.panel._next_local_id = 0
        self.panel._busy = False
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
        self.timers = []
        self.module.QTimer = types.SimpleNamespace(singleShot=lambda _ms, cb: self.timers.append(cb))
        self.module.mw.taskman = types.SimpleNamespace(run_in_background=lambda job, done: self.jobs.append((job, done)))

    def test_choosing_a_word_starts_every_dictionary(self):
        """Wszystkie słowniki naraz — „AI: znaczenia" i tak czyta komplet."""
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
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
        tabs._no_text = set()
        tabs._loaded = {0: True, 1: True}
        tabs.isTabEnabled = lambda _i: True
        tabs._views = [types.SimpleNamespace(page=lambda text=text: types.SimpleNamespace(
            toPlainText=lambda callback: callback(text))) for text in ("po polsku", "in english")]
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
        tabs._no_text = set()
        tabs._loaded = {0: True}
        tabs.isTabEnabled = lambda _i: True
        tabs._views = [types.SimpleNamespace(page=lambda: types.SimpleNamespace(
            toPlainText=lambda callback: callback("tekst")))]
        tabs._collect(lambda _result: self.fail("zamknięty panel nie może dostać tekstu"))
        tabs.deleted = True                        # okno „Dodaj" zamknięte, zanim timer wystrzelił
        self.timers.pop()()

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
        self.module.ai_senses.prepare_provider = lambda cfg: ("provider", None)
        self.panel._ai_btn = types.SimpleNamespace(setEnabled=lambda on: self.enabled.append(on),
                                                   setText=lambda t: None)
        self.panel._local_label = ""
        self.loaded = []
        self.panel._tabs = types.SimpleNamespace(
            set_urls=lambda urls: None,
            texts=lambda callback: (self.loaded.append(self.panel._shown_word),
                                    callback({"diki": "tekst"}))[0])
        return items

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
        for path in sorted(ROOT.glob("anki_toolkit_*/*.py")):
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
                    unknown[f"{path.parent.name}/{path.name}::{cls.name}"] = missing
        self.assertEqual(unknown, {})


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
