"""Run with Anki's Python: QT_QPA_PLATFORM=offscreen python tests/qt_ai_settings_smoke.py.

Real settings widgets; no collection, CLI requests, or user configuration writes.
"""
import copy
import importlib
import json
from pathlib import Path
import sys
import types

from aqt.qt import QApplication

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
    "fallback_provider": "codex_cli", "fallback_model": "gpt-test",
    "reasoning_effort": "high", "fallback_reasoning_effort": "xhigh",
    "unknown_setting": "preserve",
}}}
tab = module.AIGeneratorTab(copy.deepcopy(cfg))
try:
    prompts = tab._prompts
    prompts._load_key_to_editor(("Test", "task"))
    assert prompts._ed_effort.currentData() == "high"
    assert prompts._ed_fallback_effort.currentData() == "xhigh"
    tab._provider_widgets["claude_cli"]["reasoning_effort"].setCurrentText("medium")
    saved = copy.deepcopy(cfg)
    tab.apply(saved)
    task = saved["ai_generator"]["note_types"]["Test"]["task"]
    assert task["reasoning_effort"] == "high"
    assert task["fallback_reasoning_effort"] == "xhigh"
    assert task["unknown_setting"] == "preserve"
    assert saved["ai_generator"]["providers"]["claude_cli"]["reasoning_effort"] == "medium"
    prompts._ed_effort.setCurrentIndex(0)
    prompts._ed_fallback_effort.setCurrentIndex(0)
    tab.apply(saved)
    task = saved["ai_generator"]["note_types"]["Test"]["task"]
    assert "reasoning_effort" not in task and "fallback_reasoning_effort" not in task
    prompts._ed_provider.setCurrentIndex(prompts._ed_provider.findData("openai"))
    assert not prompts._ed_effort.isEnabled()
    assert prompts._ed_fallback_effort.isEnabled()
    prompts._ed_provider.setCurrentIndex(prompts._ed_provider.findData("codex_cli"))
    assert prompts._ed_effort.isEnabled()
    assert prompts._ed_effort.findData("ultra") >= 0
    queue_module = importlib.import_module("effort_smoke.integrations.settings")
    saved["word_queue"].update({"ai_provider": "claude_cli", "ai_reasoning_effort": "high"})
    queue = queue_module.IntegrationsTab(copy.deepcopy(saved))
    try:
        assert queue._effort.currentData() == "high"
        queue.apply(saved)
        assert saved["word_queue"]["ai_reasoning_effort"] == "high"
        queue._effort.setCurrentIndex(0)
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
