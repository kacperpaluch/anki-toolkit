"""Real Qt menus with synthetic notes; no live collection, requests or config writes.

QT_QPA_PLATFORM=offscreen <Anki Python> tests/qt_browser_menu_smoke.py
"""
import ast
import copy
import importlib
from pathlib import Path
import sys
import types
from unittest.mock import patch

from aqt.qt import QApplication, QAction, QMenu, QWidget
import aqt.utils

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication(["qt-browser-menu-smoke"])
for suffix in ("", "ai_generator", "dictionary", "tts", "field_splitter"):
    name = "menu_smoke" + ("." + suffix if suffix else "")
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / suffix)]
    sys.modules[name] = package

ai = importlib.import_module("menu_smoke.ai_generator.browser_ui")
dictionary = importlib.import_module("menu_smoke.dictionary.browser_ui")
tts = importlib.import_module("menu_smoke.tts")  # parent package: load menu functions below
# Parent package was stubbed above to avoid registering editor hooks.
source = ast.parse((ROOT / "tts/__init__.py").read_text())
selected = [n for n in source.body if not isinstance(n, ast.ImportFrom)
            or n.module != "editor_ui"]
exec(compile(ast.Module(body=selected, type_ignores=[]), str(ROOT / "tts/__init__.py"), "exec"), tts.__dict__)
splitter = sys.modules["menu_smoke.field_splitter"]
exec(compile((ROOT / "field_splitter/__init__.py").read_text(), str(ROOT / "field_splitter/__init__.py"), "exec"), splitter.__dict__)
workflow = importlib.import_module("menu_smoke.ai_generator.workflow")
common = importlib.import_module("menu_smoke.common")

class Note:
    def __init__(self, nid, name, fields):
        self.id, self.mid, self.name = nid, nid, name
        self.names = list(fields)
        self.fields = list(fields.values())
        self.tags = []
    def keys(self): return list(self.names)
    def note_type(self): return {"name": self.name}
    def __contains__(self, field): return field in self.names
    def __getitem__(self, field): return self.fields[self.names.index(field)]

class Browser(QWidget):
    def selected_notes(self): return list(notes)

notes = {1: Note(1, "English", {"ang": "cat", "def": "old", "manual": "", "audio": ""})}
browser = Browser()
config = {
    "ai_generator": {"note_types": {
        "English": {"definition": {"target": "def", "provider": "claude_cli"},
                    "manual": {"target": "manual", "provider": "claude_cli", "manual_only": True}},
        "Other": {"other": {"target": "other", "provider": "openai"}},
    }},
    "workflows": [{"name": "Przygotuj fiszki", "steps": [{"module": "ai", "action": "generate"}]}],
    "dictionary": {"source_field": "ang", "target_field": "audio", "buttons": [{"label": "Diki", "enabled": True, "dictionaries": ["diki_uk"]}]},
    "tts": {"tasks": [{"label": "Audio", "source_field": "ang", "target_field": "audio"},
                       {"label": "Niepasujące", "source_field": "absent", "target_field": "audio"}]},
    "context_menu": {},
}
manager = types.SimpleNamespace(getConfig=lambda _: copy.deepcopy(config))
mw = types.SimpleNamespace(col=types.SimpleNamespace(get_note=lambda nid: notes[nid]), addonManager=manager)

# Exercise the real root dispatcher without registering hooks/timers.
root_source = ast.parse((ROOT / "__init__.py").read_text())
context = next(n for n in root_source.body if isinstance(n, ast.FunctionDef) and n.name == "_context")
namespace = {"__package__": "menu_smoke", "mw": mw, "ai_generator": ai,
             "dictionary": dictionary, "tts": tts, "field_splitter": splitter}
exec(compile(ast.Module(body=[context], type_ignores=[]), str(ROOT / "__init__.py"), "exec"), namespace)

def labels(menu): return [a.text() for a in menu.actions() if not a.isSeparator()]

def build():
    menu = QMenu(browser)
    namespace["_context"](browser, menu)
    return menu

with patch.object(ai, "mw", mw), patch.object(ai, "get_config", lambda: config["ai_generator"]), \
     patch.object(workflow, "mw", mw), \
     patch.object(common.config, "mw", mw), patch.object(dictionary, "mw", mw):
    menu = build(); sub = menu.actions()[0].menu()
    assert "Uzupełnij puste pola AI" in labels(sub)
    assert "Generuj pola tylko na żądanie" in labels(sub)
    assert "Wygeneruj ponownie wybrane pole…" in labels(sub)
    assert "Batch API" not in labels(sub)
    assert "Rozdziel pole" not in " ".join(labels(sub))
    tts_menu = next(a.menu() for a in sub.actions() if a.text() == "TTS")
    assert labels(tts_menu) == ["Audio"]
    menu.close()
    notes[2] = Note(2, "Other", {"other": ""})
    menu = build(); sub = menu.actions()[0].menu()
    assert "Batch API" in labels(sub)
    menu.close()
    config["context_menu"] = {"dictionary": False, "tts": False, "field_splitter": False}
    menu = build(); sub = menu.actions()[0].menu()
    assert "TTS" not in labels(sub) and "Pobierz wymowę" not in labels(sub)
    menu.close()
    notes.clear()
    menu = build(); assert not menu.actions(); menu.close()

# Check Tools grouping and the settings callback's QAction(bool) boundary.
settings_module = types.ModuleType("menu_smoke.settings_dialog")
opened = []
settings_module.open_settings = lambda page=None: opened.append(page)
manager.setConfigAction = lambda *_: None
mw.form = types.SimpleNamespace(menuTools=QMenu(browser))
setup = next(n for n in root_source.body if isinstance(n, ast.FunctionDef) and n.name == "_setup_menu")
namespace.update({"QAction": QAction,
    "integrations": types.SimpleNamespace(open_queue=lambda: None),
    "audio_normalizer": types.SimpleNamespace(confirm_normalization=lambda: None),
    "html_cleanup": types.SimpleNamespace(confirm_collection_cleanup=lambda: None)})
exec(compile(ast.Module(body=[setup], type_ignores=[]), str(ROOT / "__init__.py"), "exec"), namespace)
with patch.dict(sys.modules, {"menu_smoke.settings_dialog": settings_module}):
    namespace["_setup_menu"]()
tools = mw.form.menuTools.actions()[0].menu()
assert labels(tools) == ["Kolejka słówek (n8n)…", "Ustawienia…",
                         "Pobierz i zastosuj wyniki Batch API", "Operacje na kolekcji"]
operations = tools.actions()[-1].menu()
assert len(labels(operations)) == 3
tools.actions()[1].trigger()
assert opened == [None]

workflows_tab = importlib.import_module("menu_smoke.settings.workflows_tab")
tab = workflows_tab.WorkflowsTab(config)
assert tab._list.item(0).toolTip() == "AI: wszystkie puste pola"
saved = copy.deepcopy(config); saved["context_menu"]["future_key"] = "keep"
tab.apply(saved)
assert saved["context_menu"]["future_key"] == "keep"
tab.close()

# Construct the actual selectable/copyable report dialog, without a modal wait.
real_show_text = aqt.utils.showText
reports = []
def show_report(text, **kwargs):
    dialog, _buttons = real_show_text(text, run=False, **kwargs)
    reports.append(dialog)
    assert dialog.windowTitle() == "Raport testowy"
    dialog.show(); APP.processEvents(); dialog.close()
with patch.object(aqt.utils, "showText", show_report), \
     patch.object(aqt.utils, "tr", types.SimpleNamespace(qt_misc_copy_to_clipboard=lambda: "Kopiuj")):
    ai._show_run_report(browser, "Raport testowy", 1, 1, [],
                        [(1, "error", "def: testowy błąd")], False)
browser.close()
print("Qt browser menus and report: OK")
