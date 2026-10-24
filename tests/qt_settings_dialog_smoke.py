"""The real settings window: sidebar, start page, cross-panel wiring and save.

QT_QPA_PLATFORM=offscreen <Anki Python> tests/qt_settings_dialog_smoke.py
No collection, network or user configuration writes.
"""
import copy
import importlib
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch

from aqt.qt import QApplication

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication(["qt-settings-dialog-smoke"])
package = types.ModuleType("dialog_smoke")
package.__path__ = [str(ROOT)]
sys.modules["dialog_smoke"] = package

cfg = json.loads((ROOT / "config.json").read_text())
cfg["ai_generator"]["note_types"] = {"English": {"def": {"target": "def", "provider": "openrouter"}}}
cfg["ai_generator"]["providers"]["openrouter"]["api_key"] = "sk-or-test"
cfg["tts"].update({"use_ai_openrouter_key": True, "future_tts_key": "keep"})
cfg["word_queue"].update({"n8n_url": "https://n8n.example", "future_queue_key": "keep"})
cfg["workflows"] = [{"name": "Przygotuj fiszki", "steps": [{"module": "ai", "action": "generate"}]}]

mw = types.SimpleNamespace(col=None, addonManager=types.SimpleNamespace(getConfig=lambda _: copy.deepcopy(cfg)))
common_config = importlib.import_module("dialog_smoke.common.config")
saved = []
with patch.object(common_config, "mw", mw), patch("aqt.mw", mw):
    dialog_module = importlib.import_module("dialog_smoke.settings_dialog")
    with patch.object(dialog_module, "mw", None), \
            patch.object(dialog_module, "get_full_config", lambda: copy.deepcopy(cfg)), \
            patch.object(dialog_module, "save_full_config", saved.append), \
            patch.object(dialog_module, "tooltip", lambda *a, **k: None):
        dialog = dialog_module.SettingsDialog()
        sidebar = [dialog._sidebar.item(r).text() for r in range(dialog._sidebar.count())]
        assert sidebar[:2] == ["START", "🏠  Przegląd"], sidebar
        assert "🔑  Konta i klucze" in sidebar and "⚙️  Sekwencje" in sidebar
        assert not any("AI Generator" in row or "Workflow" in row for row in sidebar)
        assert dialog._sidebar.currentRow() == dialog._rows["overview"]

        by_type = {type(p).__name__: p for p in dialog._panels}
        rows = {key: text for key, text, _configured in
                importlib.import_module("dialog_smoke.settings.overview_tab").summary(cfg)}
        assert rows["workflows"].endswith("Przygotuj fiszki") and "OpenRouter" in rows["accounts"]
        by_type["OverviewTab"].go_to("accounts")
        assert dialog._sidebar.currentRow() == dialog._rows["accounts"]

        accounts = by_type["AccountsTab"]
        # TTS previews use the live OpenRouter key from the providers box.
        assert by_type["TTSTab"]._build_preview_config()["openrouter_api_key"] == "sk-or-test"
        accounts.providers._provider_widgets["openrouter"]["api_key"].setText("sk-or-new")
        assert by_type["TTSTab"]._build_preview_config()["openrouter_api_key"] == "sk-or-new"
        accounts._url.setText("https://n8n.changed")

        dialog.save()
        out = saved[-1]
        assert out["ai_generator"]["providers"]["openrouter"]["api_key"] == "sk-or-new"
        assert out["word_queue"]["n8n_url"] == "https://n8n.changed"
        assert out["word_queue"]["future_queue_key"] == "keep" and out["tts"]["future_tts_key"] == "keep"
        assert out["tts"]["use_ai_openrouter_key"] is True
        assert out["ai_generator"]["note_types"]["English"]["def"]["provider"] == "openrouter"
        dialog.deleteLater()
print("Qt settings dialog: OK")
