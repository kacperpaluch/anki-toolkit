"""Run with Anki's Python: QT_QPA_PLATFORM=offscreen python tests/qt_ai_settings_smoke.py.

Real settings widgets; no collection, CLI requests, or user configuration writes.
"""
import copy
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
accounts = importlib.import_module("effort_smoke.settings.accounts_tab").AccountsTab(copy.deepcopy(cfg))
try:
    prompts = tab._prompts
    # Same wiring as SettingsDialog: prompts read provider defaults live from Konta i klucze.
    prompts._provider_settings = accounts.provider_settings
    widgets = accounts.providers._provider_widgets
    prompts._load_key_to_editor(("Test", "task"))
    assert not prompts._ed_temperature.isEnabled()
    assert not prompts._task_section.findChild(QPushButton).isChecked()
    assert not prompts._fallback_section.findChild(QPushButton).isChecked()
    widgets["claude_cli"]["reasoning_effort"].setCurrentText("high")
    saved = copy.deepcopy(cfg)
    tab.apply(saved)
    accounts.apply(saved)
    task = saved["ai_generator"]["note_types"]["Test"]["task"]
    # Effort is set per provider only: old per-prompt overrides are dropped on save.
    assert "reasoning_effort" not in task and "fallback_reasoning_effort" not in task
    assert task["unknown_setting"] == "preserve"
    assert task["temperature"] == 0.55
    assert saved["ai_generator"]["providers"]["claude_cli"]["reasoning_effort"] == "high"
    prompts._ed_provider.setCurrentIndex(prompts._ed_provider.findData("openai"))
    assert prompts._ed_temperature.isEnabled()
    queue_module = importlib.import_module("effort_smoke.integrations.settings")
    queue = queue_module.IntegrationsTab(copy.deepcopy(saved))
    try:
        queue._pl.setText("polski")
        queue.apply(saved)
        assert saved["word_queue"]["ai_fields"]["pl"] == "polski"
        original_field = queue._field.text()
        queue._field.clear()
        assert queue.validate()
        queue._field.setText(original_field)
        assert queue.validate() is None
    finally:
        queue.close()
    # Unused providers are hidden until added; the claude_cli prompt and codex fallback keep theirs.
    rows = {name: r for r, name in enumerate(module._PROVIDER_NAMES)}
    hidden = [n for n, r in rows.items() if accounts.providers._prov_list.isRowHidden(r)]
    assert "claude_cli" not in hidden and "codex_cli" not in hidden
    for name in hidden:
        accounts.providers._add_provider(rows[name])
    assert not accounts.providers._add_btn.isVisibleTo(accounts.providers)
    print("Qt AI settings and word queue smoke: OK")
finally:
    tab.close()
    accounts.close()
