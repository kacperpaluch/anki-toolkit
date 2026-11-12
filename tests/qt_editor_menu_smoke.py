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

saved = []
root_source = ast.parse((ROOT / "__init__.py").read_text())
editor_code = [n for n in root_source.body
               if getattr(n, "name", "") in ("_editor_groups", "_pinned", "_toggle_pin", "_run_pinned",
                                             "_show_editor_menu", "_editor_buttons")
               or isinstance(n, ast.Assign) and n.targets[0].id == "_SHORT"]
dictionary.ACTION_PREFIX  # the root reads it from the dictionary module
tips = []
namespace = {"__package__": "editor_smoke", "dictionary": dictionary, "tts": tts, "field_hider": hider,
             "integrations": queue, "unique": common.unique, "tooltip": lambda text, **_kw: tips.append(text),
             "get_module_config": common.get_module_config,
             "update_module_config": lambda key, changes: (saved.append(changes),
                                                           config.setdefault(key, {}).update(changes)),
             "ai_generator": types.SimpleNamespace(workflow_actions=ai.workflow_actions,
                                                   editor_actions=ai.editor_actions)}
exec(compile(ast.Module(body=editor_code, type_ignores=[]), str(ROOT / "__init__.py"), "exec"), namespace)

shown = []
def texts(menu):
    return ["—" if a.isSeparator() else
            a.text() + (" ☑" if a.isChecked() else " ☐" if a.isCheckable() else "")
            for a in menu.actions()]

def fake_exec(menu, *_args):
    shown.append(texts(menu))
    pins.append({a.text(): a for a in menu.actions() if a.menu()}["Przypnij do paska"].menu())

pins = []
ALL = ["Przygotuj fiszki", "Uzupełnij puste pola AI", "Pobierz wymowę: Diki", "Nagraj audio (TTS)",
       "📚 Kolejka słówek", "Pokaż schowane pola"]
widget = QWidget()
with patch.object(QMenu, "exec", fake_exec), patch.object(workflow, "mw", mw), \
        patch.object(common.config, "mw", mw), patch.object(dictionary, "mw", mw), \
        patch.object(ai, "get_config", lambda: config["ai_generator"]):
    editor = types.SimpleNamespace(widget=widget, addMode=True, web=types.SimpleNamespace(eval=lambda _js: None),
                                   note=Note({"ang": "cat", "def": "", "audio": ""}))
    # Nothing pinned: every fitting action is in the menu and can be pinned.
    namespace["_show_editor_menu"](editor)
    assert shown[-1] == ["Przygotuj fiszki", "—", "Uzupełnij puste pola AI", "Pobierz wymowę: Diki",
                         "Nagraj audio (TTS)", "—", "📚 Kolejka słówek ☐", "Pokaż schowane pola ☐",
                         "—", "Przypnij do paska", "—", "Ustawienia…"], shown[-1]
    assert texts(pins[-1]) == [label + " ☐" for label in ALL], texts(pins[-1])
    hider._toggle_hidden_fields(editor)
    namespace["_show_editor_menu"](editor)
    assert "Pokaż schowane pola ☑" in shown[-1], shown[-1]

    # Pinning from the submenu saves the label; the open editor keeps its menu until reopened.
    for label in ("Pobierz wymowę: Diki", "Nagraj audio (TTS)", "Przygotuj fiszki", "Stara sekwencja"):
        namespace["_toggle_pin"](label)
    assert saved[-1] == {"pinned": ["Pobierz wymowę: Diki", "Nagraj audio (TTS)", "Przygotuj fiszki",
                                    "Stara sekwencja"]}, saved
    namespace["_show_editor_menu"](editor)
    assert "Pobierz wymowę: Diki" in shown[-1], shown[-1]

    # A new editor builds the buttons and drops them from its menu.
    added, ran = {}, []
    editor.addButton = lambda _icon, cmd, func, tip, label, disables: added.update({label: (tip, func)}) or cmd
    namespace["_editor_buttons"]([], editor)
    assert {k: v[0] for k, v in added.items()} == {
        "D": "Pobierz wymowę: Diki", "TTS": "Nagraj audio (TTS)", "Przygotuj fiszki": "Przygotuj fiszki",
        "Stara sekwencja": "Stara sekwencja", "Toolkit ▾": "Anki Toolkit"}, added
    namespace["_show_editor_menu"](editor)
    assert shown[-1] == ["Uzupełnij puste pola AI", "—", "📚 Kolejka słówek ☐", "Pokaż schowane pola ☑",
                         "—", "Przypnij do paska", "—", "Ustawienia…"], shown[-1]
    assert texts(pins[-1])[-1] == "Stara sekwencja ☑", texts(pins[-1])  # stale pin stays removable
    with patch.object(dictionary, "_on_fetch_audio_editor", lambda ed, d: ran.append(d)):
        added["D"][1](editor)
    assert ran == [["diki_uk"]], ran
    added["Stara sekwencja"][1](editor)
    assert "nie pasuje" in tips[-1], tips

    editor.addMode, editor.note = False, Note({"front": "x"})
    namespace["_show_editor_menu"](editor)
    assert shown[-1] == ["Przypnij do paska", "—", "Ustawienia…"], shown[-1]
    added["D"][1](editor)
    assert "nie pasuje" in tips[-1], tips
widget.close()
print("Qt editor Toolkit menu: OK")
