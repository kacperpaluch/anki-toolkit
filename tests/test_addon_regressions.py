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

    def test_values_are_always_escaped(self):
        target = self.module._target
        self.module._apply_fields({"ang": "R&D <b>"}, target, append=True)
        self.assertEqual(self.editor.note["ang"], "word<br><br>R&amp;D &lt;b&gt;")
        self.module._apply_fields({"def": "<i>x</i>"}, target)
        self.assertEqual(self.editor.note["def"], "&lt;i&gt;x&lt;/i&gt;")

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
            ItemDataRole=types.SimpleNamespace(UserRole=0, ForegroundRole=1),
            GlobalColor=types.SimpleNamespace(gray=0))
        self.module.QBrush = lambda x: x
        self.module.tooltip = lambda *a, **k: None
        self.panel = self.module.WordQueuePanel.__new__(self.module.WordQueuePanel)
        self.item = Item(1)
        self.panel._list = types.SimpleNamespace(count=lambda: 1, item=lambda i: self.item,
                                                currentItem=lambda: self.item)
        from tempfile import TemporaryDirectory
        self.state_dir = TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)
        self.panel._state = self.module.QueueState("/test/collection.anki2", {}, self.state_dir.name)
        self.panel._collection = self.module.mw.col
        self.panel._word_title = types.SimpleNamespace(setText=lambda text: None)
        self.panel._queue_status = types.SimpleNamespace(setText=lambda text: None)
        self.panel._marked = set()
        self.panel._adding = set()
        self.panel._added = {}
        self.typed = types.SimpleNamespace(value="")
        self.panel._word_input = types.SimpleNamespace(
            text=lambda: self.typed.value, setText=lambda v: setattr(self.typed, "value", v))
        self.panel._pending = {}
        self.panel._done_count = 0
        self.panel._refill_generation = self.panel._selection_generation = 0
        self.panel._suspend = False
        self.panel._cfg = {"word_field": "ang", "word_column": "Slowko", "flag_column": "Anki"}
        self.panel._status_filter = types.SimpleNamespace(currentData=lambda: "all")
        self.panel._search = types.SimpleNamespace(text=lambda: "")
        self.panel._counter = types.SimpleNamespace(setText=lambda _: None)
        self.panel._mark_row_done = lambda *a: (1, None)
        self.editor = Editor()
        self.panel._addcards = types.SimpleNamespace(editor=self.editor)
        self.jobs = []
        self.timers = []
        self.module.QTimer = types.SimpleNamespace(singleShot=lambda _ms, cb: self.timers.append(cb))
        self.module.mw.taskman = types.SimpleNamespace(run_in_background=lambda job, done, **_: self.jobs.append((job, done)))

    def test_choosing_a_word_loads_only_the_visible_dictionary(self):
        """Jedno zapytanie na słowo; reszta czeka na wejście w zakładkę."""
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels = ["diki", "Cambridge", "Oxford", "LDoCE"]
        tabs._challenged = set()
        loaded, enabled, current = [], {}, [0]
        tabs._views = [types.SimpleNamespace(load=lambda url, i=i: loaded.append(i))
                       for i in range(4)]
        tabs.setTabEnabled = lambda i, on: enabled.__setitem__(i, on)
        tabs.isTabEnabled = lambda i: enabled.get(i, False)
        tabs.currentIndex = lambda: current[0]
        tabs.setCurrentIndex = lambda i: current.__setitem__(0, i)
        self.module.QUrl = lambda url: url

        tabs.set_urls({"diki": "d", "Cambridge": "c", "Oxford": "o", "LDoCE": "l"})
        self.assertEqual(loaded, [0])           # tylko widoczna zakładka
        self.assertEqual(tabs._pending, {1: "c", 2: "o", 3: "l"})
        current[0] = 2
        tabs._load_current()                    # wejście w zakładkę Oxford
        self.assertEqual(loaded, [0, 2])
        self.assertNotIn(2, tabs._pending)

        loaded.clear()
        tabs.set_urls({"diki": "d", "Oxford": "", "Cambridge": "", "LDoCE": ""})
        self.assertEqual(loaded.count(0), 1)    # tylko diki ma adres
        self.assertFalse(enabled[2])            # reszta wyszarzona

    def test_cloudflare_check_gets_js_only_while_it_runs(self):
        """Cambridge bywa za weryfikacją Cloudflare, która bez JS stoi w miejscu."""
        tabs = self.module._DictTabs.__new__(self.module._DictTabs)
        tabs._labels, tabs._page_js = ["diki", "Cambridge"], {"diki"}
        tabs._challenged, tabs._passed = set(), {}
        page = types.SimpleNamespace(challenge=True, js=[], reloads=0)
        settings = types.SimpleNamespace(setAttribute=lambda _attr, on: page.js.append(on))
        view = types.SimpleNamespace(
            url=lambda: types.SimpleNamespace(toString=lambda: "https://cambridge/mother"),
            settings=lambda: settings,
            reload=lambda: setattr(page, "reloads", page.reloads + 1),
            page=lambda: types.SimpleNamespace(
                runJavaScript=lambda script, world, cb: cb(page.challenge)))
        tabs._views = [None, view]
        self.module.QWebEngineSettings = types.SimpleNamespace(
            WebAttribute=types.SimpleNamespace(JavascriptEnabled=0))

        def load():
            tabs._after_load(1)
            self.timers.pop()()                     # odpowiedź wraca poza callbackiem silnika

        load()                                      # weryfikacja bez JS
        self.assertEqual((page.js, page.reloads), ([True], 1))
        page.challenge = False
        load()                                      # weryfikacja przeszła, strona z JS
        self.assertEqual((page.js, page.reloads), ([True, False], 2))
        load()                                      # ta sama strona już bez JS
        self.assertEqual((page.js, page.reloads), ([True, False], 2))

        page.challenge = True                       # ciasteczko nie wystarczyło: bez pętli
        tabs._passed[1] = "https://cambridge/mother"
        load()
        self.assertEqual((page.js, page.reloads), ([True, False], 2))
        tabs._after_load(0)                         # diki ma własny JS — nie sprawdzamy
        self.assertEqual(self.timers, [])

    def test_stale_selection_callback_is_dropped(self):
        items = [Item(1), Item(2)]
        self.panel._list = types.SimpleNamespace(
            count=lambda: 2, item=lambda i: items[i], currentItem=lambda: items[1])
        self.panel._prefill = lambda *a, **k: self.fail("nieaktualna pozycja nie może wypełniać notatki")
        self.panel._on_item_changed(items[0], None)  # zanim timer zdążył, wybór poszedł dalej
        self.timers.pop()()

    def test_failed_patch_is_owed_and_settled_after_refill(self):
        self.panel._owe({1: "word"})
        self.panel._set_row(self.item, True)
        self.finish((0, "offline"))
        recovered = self.module.QueueState("/test/collection.anki2", {}, self.state_dir.name)
        self.assertEqual(recovered.data["owed"], {"1": "word"})
        with patch.object(self.module.word_queue, "find_word_notes", return_value=[42]):
            self.panel._settle_owed()           # cards exist → PATCH again
        self.finish((1, None))
        self.assertEqual(self.panel._state.data["owed"], {})
        self.assertEqual(self.panel._marked, {1})

    def test_owed_row_without_cards_is_dropped(self):
        self.panel._owe({1: "word"})
        with patch.object(self.module.word_queue, "find_word_notes", return_value=[]):
            self.panel._settle_owed()           # crash before commit: nothing to report
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.panel._state.data["owed"], {})

    def test_owed_row_deleted_in_n8n_is_dropped_without_patch(self):
        self.panel._owe({99: "gone"})           # row 99 is no longer in the queue
        with patch.object(self.module.word_queue, "find_word_notes", return_value=[42]) as find:
            self.panel._settle_owed()
        find.assert_not_called()
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.panel._state.data["owed"], {})

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

    def test_newest_first_puts_the_words_you_just_added_on_top(self):
        """`id` rośnie z każdym dopisanym wierszem."""
        rows = [{"id": 3}, {"id": 1}, {"id": 7}]
        self.panel._cfg["order"] = "id"
        self.assertEqual([r["id"] for r in self.panel._ordered(rows)], [1, 3, 7])
        self.panel._cfg["order"] = "new"
        self.assertEqual([r["id"] for r in self.panel._ordered(rows)], [7, 3, 1])
        self.panel._cfg["order"] = "random"
        self.assertEqual(sorted(r["id"] for r in self.panel._ordered(rows)), [1, 3, 7])

    def test_old_refill_cannot_overwrite_new_refill(self):
        self.panel._rebuild = lambda rows: self.assertEqual(rows, [{"id": 2}])
        self.panel.refill(); self.panel.refill()
        future = Future(); future.set_result(([{"id": 1}], None)); self.jobs[0][1](future)
        future = Future(); future.set_result(([{"id": 2}], None)); self.jobs[1][1](future)

    def test_n8n_error_stays_visible_and_keeps_current_list(self):
        messages = []
        self.panel._queue_status = types.SimpleNamespace(setText=messages.append)
        self.panel.refill()
        self.assertIn("Pobieranie", messages[-1])
        self.finish(([], "serwer w konserwacji"))
        self.assertIn("serwer w konserwacji", messages[-1])
        self.assertIn("Odśwież", messages[-1])
        self.assertIs(self.panel._list.item(0), self.item)

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
        self.panel._add_words(self.module.word_queue.parse_words("mother, give up"))
        self.assertFalse(rebuilt)                    # najpierw zapis, potem lista
        self.finish(([{"id": 7, "Slowko": "mother"}, {"id": 8, "Slowko": "give up"}], None))
        self.assertEqual([row["id"] for row in rebuilt[0]], [7, 8])

    def test_word_being_written_is_not_written_again(self):
        """Zapis trwa, hasła nie ma jeszcze na liście — drugie wklejenie musi je pominąć."""
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None,
                                                 setCurrentRow=lambda i: None)
        self.panel._rebuild = lambda rows: None
        self.panel._select_word = lambda word: None
        self.panel._add_words(["mother"])
        self.assertEqual(len(self.jobs), 1)
        self.panel._add_words(["Mother"])           # w trakcie zapisu, inna wielkość liter
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
        self.panel._add_words(["mother"])        # inna wielkość liter, to samo hasło
        self.assertEqual(self.jobs, [])

    def test_failed_write_puts_the_words_back_into_the_input(self):
        """n8n nie przyjął zapisu: nic nie trafia na listę, hasła wracają do pola."""
        rebuilt = []
        self.panel._rebuild = rebuilt.append
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None)
        self.typed.value = "cat"                         # coś już wpisano w międzyczasie
        self.panel._add_words(["mother", "give up"])
        self.finish(([], "Connection error"))
        self.assertEqual(rebuilt, [])
        self.assertEqual(self.typed.value, "cat, mother, give up")
        self.assertEqual(self.panel._adding, set())      # ponowienie nie jest blokowane
        self.panel._add_words(["mother"])
        self.assertEqual(len(self.jobs), 2)

    def test_refill_started_before_a_write_keeps_the_new_row(self):
        rebuilt = []
        self.panel._rebuild = rebuilt.append
        self.panel._settle_owed = lambda: None
        self.panel._list = types.SimpleNamespace(count=lambda: 0, item=None, currentItem=lambda: None)
        self.panel.refill()
        refill_done = self.jobs[-1][1]
        self.panel._add_words(["mother"])
        self.finish(([{"id": 7, "Slowko": "mother"}], None))
        future = Future(); future.set_result(([{"id": 5, "Slowko": "cat"}], None))
        refill_done(future)                              # GET sprzed zapisu kończy się później
        self.assertEqual([row["id"] for row in rebuilt[-1]], [5, 7])
        self.jobs.clear()
        self.panel._add_words(["Mother"])           # nadal „już na liście”
        self.assertEqual(self.jobs, [])

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
        for path in sorted(p for p in paths if p.parent.name != "tests"):
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

    def test_oversized_note_is_added_unchanged_not_refused(self):
        module = load("html_cleanup")
        module.get_config = lambda: {"rules": [{"find": "x", "to": "xx", "repeat": True}]}
        shown = []
        module.tooltip = lambda text, **_kw: shown.append(text)
        note = {"f": "x"}
        self.assertIsNone(module._on_add_note(None, note))
        self.assertEqual(note, {"f": "x"})
        self.assertTrue(shown)

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
