"""Regression checks for the add-on modules; no Anki, network or user data."""
import ast
import importlib.util
import json
import sys
import types
import unittest
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
        name: [] for name in ("profile_did_open", "add_cards_did_init", "add_cards_will_add_note")})
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

    def test_section_config_keeps_unknown_keys(self):
        module = load("html_cleanup")
        mw = module.get_module_config.__globals__["mw"]  # common.config reads the profile
        mw.addonManager.getConfig = lambda _: {
            "html_cleanup": {"rules": [], "future_option": True}}
        self.assertEqual(module.get_config()["future_option"], True)
        self.assertEqual(module.get_config()["rules"], [])


if __name__ == "__main__":
    unittest.main()
