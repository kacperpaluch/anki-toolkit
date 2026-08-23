"""Pure-logic regression checks for the standalone Field Hider package."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


_PATH = Path(__file__).parent.parent / "anki_toolkit_field_hider" / "__init__.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "anki_toolkit_field_hider", _PATH
    )
    module = importlib.util.module_from_spec(spec)
    hooks = types.SimpleNamespace(
        editor_did_load_note=types.SimpleNamespace(append=lambda _callback: None),
        editor_did_init_buttons=types.SimpleNamespace(append=lambda _callback: None),
        main_window_did_init=types.SimpleNamespace(append=lambda _callback: None),
    )
    addon_manager = types.SimpleNamespace(getConfig=lambda _name: {})
    aqt = types.ModuleType("aqt")
    aqt.mw = types.SimpleNamespace(addonManager=addon_manager)
    aqt.gui_hooks = hooks
    qt = types.ModuleType("aqt.qt")
    qt.QAction = object
    qt.QTimer = types.SimpleNamespace(singleShot=lambda _delay, _callback: None)
    with patch.dict(sys.modules, {"aqt": aqt, "aqt.qt": qt}):
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return module


class StandaloneFieldHiderTests(unittest.TestCase):
    def test_indices_to_hide_is_independent_of_anki(self):
        module = _load_module()
        self.assertEqual(
            module.indices_to_hide(["front", "back", "audio"], ["back", "audio"]),
            [1, 2],
        )
        self.assertEqual(module.indices_to_hide(["front"], ["missing"]), [])

    def test_config_keeps_unknown_profile_keys(self):
        module = _load_module()
        module.mw.addonManager.getConfig = lambda _name: {
            "hidden_fields": {"Basic": ["Back"]},
            "future_option": True,
        }
        self.assertEqual(module.get_config()["future_option"], True)


if __name__ == "__main__":
    unittest.main()
