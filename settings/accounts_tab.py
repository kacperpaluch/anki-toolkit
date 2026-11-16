"""Konta i klucze — every API key and connection in one panel.

Writes only credential/connection keys: `ai_generator.providers` and the TTS
OpenRouter key. The feature panels (prompts, TTS) read these live through the
callbacks below.
"""
from aqt.qt import QCheckBox, QFormLayout, QGroupBox, QVBoxLayout, QWidget

from ..common.ui import _api_key_widget, scroll_panel
from .ai_generator_tab import AIProvidersBox


class AccountsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        layout = scroll_panel(self)
        self.providers = AIProvidersBox(cfg)
        layout.addWidget(self.providers)

        t = cfg.get("tts", {})
        tts = QGroupBox("Nagrania (TTS) — OpenRouter")
        form = QFormLayout(tts)
        self._tts_use_ai = QCheckBox("Użyj klucza OpenRouter z dostawców AI")
        self._tts_use_ai.setChecked(bool(t.get("use_ai_openrouter_key", False)))
        self._tts_key_box, self._tts_key = _api_key_widget(t.get("openrouter_api_key", ""))
        self._tts_use_ai.toggled.connect(lambda on: self._tts_key_box.setEnabled(not on))
        self._tts_key_box.setEnabled(not self._tts_use_ai.isChecked())
        form.addRow(self._tts_use_ai)
        form.addRow("Klucz API:", self._tts_key_box)
        layout.addWidget(tts)

        layout.addStretch()

    def provider_settings(self, name: str) -> dict:
        """Live AI provider values, including unsaved edits."""
        return self.providers._current_provider_settings(name)

    def tts_key_settings(self) -> dict:
        """Live TTS key, already resolved, for previews in the TTS panel."""
        if self._tts_use_ai.isChecked():
            key = self.provider_settings("openrouter").get("api_key", "")
        else:
            key = self._tts_key.text().strip()
        return {"openrouter_api_key": key, "use_ai_openrouter_key": False}

    def apply(self, cfg: dict) -> None:
        self.providers.apply(cfg)
        cfg.setdefault("tts", {}).update({
            "openrouter_api_key": self._tts_key.text().strip(),
            "use_ai_openrouter_key": self._tts_use_ai.isChecked(),
        })
