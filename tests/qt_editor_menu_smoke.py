"""The single "Toolkit ▾" editor button: real QMenu, synthetic note, no collection.

QT_QPA_PLATFORM=offscreen <Anki Python> tests/qt_editor_menu_smoke.py
"""
import ast
import copy
import importlib
from pathlib import Path
import sys
import types
from unittest.mock import patch

from aqt.qt import QApplication, QMenu, QWidget

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication(["qt-editor-menu-smoke"])
for suffix in ("", "ai_generator", "dictionary", "tts", "field_hider", "integrations"):
    name = "editor_smoke" + ("." + suffix if suffix else "")
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / suffix)]
    sys.modules[name] = package

ai = importlib.import_module("editor_smoke.ai_generator.editor_ui")
dictionary = importlib.import_module("editor_smoke.dictionary.editor_ui")
tts = importlib.import_module("editor_smoke.tts.editor_ui")
queue = importlib.import_module("editor_smoke.integrations.word_queue")
hider = sys.modules["editor_smoke.field_hider"]
exec(compile((ROOT / "field_hider/__init__.py").read_text(), str(ROOT / "field_hider/__init__.py"), "exec"),
     hider.__dict__)
common = importlib.import_module("editor_smoke.common")
workflow = importlib.import_module("editor_smoke.ai_generator.workflow")
settings_module = types.ModuleType("editor_smoke.settings_dialog")
settings_module.open_settings = lambda page=None: None
sys.modules["editor_smoke.settings_dialog"] = settings_module


class Note:
    def __init__(self, fields):
        self.names, self.fields, self.tags = list(fields), list(fields.values()), []
    def keys(self): return list(self.names)
    def note_type(self): return {"name": "English"}
    def __contains__(self, field): return field in self.names
    def __getitem__(self, field): return self.fields[self.names.index(field)]


config = {
    "ai_generator": {"note_types": {"English": {"definition": {"target": "def", "provider": "openai"}}}},
    "workflows": [{"name": "Przygotuj fiszki", "steps": [{"module": "ai", "action": "generate"}]},
                  {"name": "Inny typ", "steps": [{"module": "ai", "action": "generate", "fields": ["x"]}]}],
    "dictionary": {"source_field": "ang", "target_field": "audio",
                   "buttons": [{"label": "Diki", "enabled": True, "dictionaries": ["diki_uk"]},
                               {"label": "Oxford", "enabled": False, "dictionaries": ["oxford_uk"]}]},
    "tts": {"tasks": [{"label": "Audio", "source_field": "ang", "target_field": "audio"}]},
}
mw = types.SimpleNamespace(addonManager=types.SimpleNamespace(getConfig=lambda _: copy.deepcopy(config)))

root_source = ast.parse((ROOT / "__init__.py").read_text())
show = next(n for n in root_source.body if isinstance(n, ast.FunctionDef) and n.name == "_show_editor_menu")
namespace = {"__package__": "editor_smoke", "dictionary": dictionary, "tts": tts, "field_hider": hider,
             "integrations": queue,
             "ai_generator": types.SimpleNamespace(workflow_actions=ai.workflow_actions,
                                                   editor_actions=ai.editor_actions)}
exec(compile(ast.Module(body=[show], type_ignores=[]), str(ROOT / "__init__.py"), "exec"), namespace)

shown = []
def fake_exec(menu, *_args):
    shown.append([a.text() if not a.isSeparator() else "—" for a in menu.actions()])

widget = QWidget()
with patch.object(QMenu, "exec", fake_exec), patch.object(workflow, "mw", mw), \
        patch.object(common.config, "mw", mw), patch.object(dictionary, "mw", mw), \
        patch.object(ai, "get_config", lambda: config["ai_generator"]):
    editor = types.SimpleNamespace(widget=widget, addMode=True,
                                   note=Note({"ang": "cat", "def": "", "audio": ""}))
    namespace["_show_editor_menu"](editor)
    assert shown[-1] == ["Przygotuj fiszki", "—", "Uzupełnij puste pola AI", "Wymowa: Diki",
                         "Nagraj audio (TTS)", "—", "📚 Kolejka słówek (pokaż/ukryj)",
                         "Pokaż/ukryj schowane pola", "—", "Ustawienia…"], shown[-1]
    editor.addMode, editor.note = False, Note({"front": "x"})
    namespace["_show_editor_menu"](editor)
    assert shown[-1] == ["Ustawienia…"], shown[-1]
    editor.note = None
    namespace["_show_editor_menu"](editor)
    assert shown[-1] == ["Ustawienia…"], shown[-1]
widget.close()
print("Qt editor Toolkit menu: OK")
