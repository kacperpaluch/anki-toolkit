"""Pure tests for workflow module gating and the shared editor guard."""

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_workflow(editor_operation):
    root_pkg = types.ModuleType("_wf")
    root_pkg.__path__ = []
    ai_pkg = types.ModuleType("_wf.ai_generator")
    ai_pkg.__path__ = []
    common_pkg = types.ModuleType("_wf.common")
    common_pkg.__path__ = []
    common_pkg.ADDON_NAME = "anki-toolkit"
    common_pkg.plural_pl = lambda n, one, few, many: one if n == 1 else few

    aqt = types.ModuleType("aqt")
    aqt.mw = types.SimpleNamespace(
        addonManager=types.SimpleNamespace(getConfig=lambda _name: {})
    )
    aqt_utils = types.ModuleType("aqt.utils")
    aqt_utils.tooltip = lambda *args, **kwargs: None
    aqt_editor = types.ModuleType("aqt.editor")
    aqt_editor.Editor = object

    modules = {
        "_wf": root_pkg,
        "_wf.ai_generator": ai_pkg,
        "_wf.common": common_pkg,
        "_wf.common.editor_operation": editor_operation,
        "aqt": aqt,
        "aqt.utils": aqt_utils,
        "aqt.editor": aqt_editor,
    }
    name = "_wf.ai_generator.workflow"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "ai_generator/workflow.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class EditorOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_module(
            "_editor_operation", ROOT / "common/editor_operation.py"
        )

    def test_one_operation_per_editor(self):
        editor = types.SimpleNamespace()
        token = self.guard.begin_editor_operation(editor, "AI")

        self.assertIsNotNone(token)
        self.assertEqual(self.guard.active_editor_operation(editor), "AI")
        self.assertIsNone(self.guard.begin_editor_operation(editor, "TTS"))

        self.guard.finish_editor_operation(editor, token)
        self.assertIsNotNone(self.guard.begin_editor_operation(editor, "TTS"))

    def test_different_editors_are_independent(self):
        first = types.SimpleNamespace()
        second = types.SimpleNamespace()

        self.assertIsNotNone(self.guard.begin_editor_operation(first, "AI"))
        self.assertIsNotNone(self.guard.begin_editor_operation(second, "TTS"))

    def test_wrong_token_does_not_release_guard(self):
        editor = types.SimpleNamespace()
        self.guard.begin_editor_operation(editor, "AI")

        self.guard.finish_editor_operation(editor, object())

        self.assertIsNone(self.guard.begin_editor_operation(editor, "TTS"))


class WorkflowModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        guard = load_module(
            "_wf.common.editor_operation", ROOT / "common/editor_operation.py"
        )
        cls.workflow = load_workflow(guard)

    def test_returns_unique_disabled_modules_in_step_order(self):
        steps = [
            {"module": "ai"},
            {"module": "tts"},
            {"module": "ai"},
            {"module": "dictionary"},
        ]
        cfg = {
            "modules": {
                "ai_generator": False,
                "tts": False,
                "dictionary": True,
            }
        }

        self.assertEqual(
            self.workflow.disabled_step_modules(steps, cfg),
            ["AI", "TTS"],
        )

    def test_missing_module_flags_default_to_enabled(self):
        steps = [
            {"module": "ai"},
            {"module": "dictionary"},
            {"module": "tts"},
            {"module": "field_splitter"},
        ]

        self.assertEqual(self.workflow.disabled_step_modules(steps, {}), [])


if __name__ == "__main__":
    unittest.main()
