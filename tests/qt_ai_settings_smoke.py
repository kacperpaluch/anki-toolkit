"""Run with Anki's Python: QT_QPA_PLATFORM=offscreen python tests/qt_ai_settings_smoke.py.

Real settings widgets; no collection, CLI requests, or user configuration writes.
"""
import copy
from concurrent.futures import Future
from unittest.mock import patch
import importlib
import json
from pathlib import Path
import sys
import types

from aqt.qt import QApplication, QPushButton

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication(["qt-ai-settings-smoke"])
for name, path in (("effort_smoke", ROOT),
                   ("effort_smoke.settings", ROOT / "settings"),
                   ("effort_smoke.ai_generator", ROOT / "ai_generator"),
                   ("effort_smoke.integrations", ROOT / "integrations")):
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules[name] = package
module = importlib.import_module("effort_smoke.settings.ai_generator_tab")
cfg = json.loads((ROOT / "config.json").read_text())
cfg["ai_generator"]["note_types"] = {"Test": {"task": {
    "target": "def", "provider": "claude_cli", "model": "opus", "prompt": "test",
    "temperature": 0.55,
    "fallback_provider": "codex_cli", "fallback_model": "gpt-test",
    "reasoning_effort": "high", "fallback_reasoning_effort": "xhigh",
    "unknown_setting": "preserve",
}}}
tab = module.AIGeneratorTab(copy.deepcopy(cfg))
try:
    prompts = tab._prompts
    prompts._load_key_to_editor(("Test", "task"))
    assert not prompts._ed_temperature.isEnabled()
    assert not prompts._task_section.findChild(QPushButton).isChecked()
    assert not prompts._fallback_section.findChild(QPushButton).isChecked()
    assert prompts._ed_effort.currentData() == "high"
    assert prompts._ed_fallback_effort.currentData() == "xhigh"
    tab._provider_widgets["claude_cli"]["reasoning_effort"].setCurrentText("medium")
    saved = copy.deepcopy(cfg)
    tab.apply(saved)
    task = saved["ai_generator"]["note_types"]["Test"]["task"]
    assert task["reasoning_effort"] == "high"
    assert task["fallback_reasoning_effort"] == "xhigh"
    assert task["unknown_setting"] == "preserve"
    assert task["temperature"] == 0.55
    assert saved["ai_generator"]["providers"]["claude_cli"]["reasoning_effort"] == "medium"
    prompts._ed_effort.setCurrentIndex(0)
    assert prompts._ed_effort.currentText() == "Dziedzicz: medium"
    tab._provider_widgets["claude_cli"]["reasoning_effort"].setCurrentText("high")
    assert prompts._ed_effort.currentText() == "Dziedzicz: high"
    assert prompts._ed_effort.currentData() == ""
    tab._provider_widgets["claude_cli"]["reasoning_effort"].setCurrentText("medium")
    prompts._ed_fallback_effort.setCurrentIndex(0)
    tab.apply(saved)
    task = saved["ai_generator"]["note_types"]["Test"]["task"]
    assert "reasoning_effort" not in task and "fallback_reasoning_effort" not in task
    prompts._ed_provider.setCurrentIndex(prompts._ed_provider.findData("openai"))
    assert not prompts._ed_effort.isEnabled()
    assert prompts._ed_temperature.isEnabled()
    assert prompts._ed_fallback_effort.isEnabled()
    prompts._ed_provider.setCurrentIndex(prompts._ed_provider.findData("codex_cli"))
    assert prompts._ed_effort.isEnabled()
    assert prompts._ed_effort.findData("ultra") >= 0
    queue_module = importlib.import_module("effort_smoke.integrations.settings")
    saved["word_queue"].update({"ai_provider": "claude_cli", "ai_model": "claude-custom", "ai_reasoning_effort": "high"})
    queue = queue_module.IntegrationsTab(copy.deepcopy(saved), tab._current_provider_settings)
    try:
        assert queue._model.currentText() == "claude-custom"
        queue._provider.setCurrentIndex(queue._provider.findData("codex_cli"))
        assert queue._model.currentText() == ""
        assert "claude-custom" not in [queue._model.itemText(i) for i in range(queue._model.count())]
        queue.apply(saved)
        assert saved["word_queue"]["ai_model"] == ""
        pending = []
        def background(task, on_done, **kwargs):
            assert kwargs == {"uses_collection": False}
            future = Future()
            try:
                future.set_result(task())
            except Exception as error:
                future.set_exception(error)
            pending.append((on_done, future))
        codex = importlib.import_module("effort_smoke.ai_generator.providers.codex_cli")
        queue._model.setCurrentText("codex-custom")
        with patch("aqt.mw", types.SimpleNamespace(taskman=types.SimpleNamespace(run_in_background=background))), \
             patch.object(codex, "fetch_models", return_value=["codex-fresh"]) as fetch:
            queue._fetch_models_btn.click()
            assert not queue._fetch_models_btn.isEnabled()
            fetch.assert_called_once()
            callback, future = pending.pop()
            callback(future)
            assert queue._fetch_models_btn.isEnabled()
            assert queue._model.findText("codex-fresh") >= 0
            assert queue._model.currentText() == "codex-custom"
            queue._fetch_models_btn.click()
            queue._provider.setCurrentIndex(queue._provider.findData("claude_cli"))
            callback, future = pending.pop()
            callback(future)
            assert queue._model.findText("codex-fresh") == -1
            assert queue._model.currentText() == ""
        with patch("aqt.mw", types.SimpleNamespace(taskman=types.SimpleNamespace(run_in_background=background))), \
             patch("effort_smoke.ai_generator.providers.claude_cli.fetch_models", side_effect=RuntimeError("test failure")), \
             patch("aqt.utils.showWarning") as warning:
            before = [queue._model.itemText(i) for i in range(queue._model.count())]
            queue._fetch_models_btn.click()
            callback, future = pending.pop()
            callback(future)
            warning.assert_called_once()
            assert queue._fetch_models_btn.isEnabled()
            assert before == [queue._model.itemText(i) for i in range(queue._model.count())]
        queue._effort.setCurrentIndex(queue._effort.findData("high"))
        assert not queue._fields_section.findChild(QPushButton).isChecked()
        assert queue._effort.currentData() == "high"
        queue.apply(saved)
        assert saved["word_queue"]["ai_reasoning_effort"] == "high"
        original_field = queue._field.text()
        queue._field.clear()
        assert queue.validate()
        assert queue._fields_section.findChild(QPushButton).isChecked()
        queue._field.setText(original_field)
        queue._effort.setCurrentIndex(0)
        assert queue._effort.currentText() == "Dziedzicz: medium"
        tab._provider_widgets["claude_cli"]["reasoning_effort"].currentTextChanged.connect(
            queue.refresh_provider_defaults)
        tab._provider_widgets["claude_cli"]["reasoning_effort"].setCurrentText("high")
        assert queue._effort.currentText() == "Dziedzicz: high"
        tab._provider_widgets["claude_cli"]["reasoning_effort"].setCurrentText("medium")
        queue.apply(saved)
        assert "ai_reasoning_effort" not in saved["word_queue"]
        queue._provider.setCurrentIndex(queue._provider.findData("codex_cli"))
        assert queue._effort.isEnabled() and queue._effort.findData("ultra") >= 0
        queue._provider.setCurrentIndex(queue._provider.findData("openai"))
        assert not queue._effort.isEnabled()
        assert queue._effort.currentData() == ""
    finally:
        queue.close()
    print("Qt AI settings and word queue smoke: OK")
finally:
    tab.close()
