"""Konta i klucze — every API key and connection in one panel.

Writes only credential/connection keys: `ai_generator.providers`, the TTS
OpenRouter key and the n8n / Cloudflare part of `word_queue`. The feature
panels (prompts, TTS, queue) read these live through the callbacks below.
"""
from aqt.qt import QCheckBox, QFormLayout, QGroupBox, QLineEdit, QVBoxLayout, QWidget

from ..common.ui import _api_key_widget, collapsible_section, hint_label, scroll_panel
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

        q = cfg.get("word_queue") or {}
        queue, body = collapsible_section("Kolejka słówek — połączenie z n8n")
        form = QFormLayout()
        self._url = QLineEdit(q.get("n8n_url", ""))
        self._fallback = QLineEdit(q.get("fallback_url", ""))
        key_widget, self._key = _api_key_widget(q.get("api_key", ""))
        self._table = QLineEdit(q.get("table_id", ""))
        self._word = QLineEdit(q.get("word_column", "Slowko"))
        self._flag = QLineEdit(q.get("flag_column", "Anki"))
        for label, widget in (("Adres główny:", self._url), ("Adres zapasowy:", self._fallback),
                              ("Klucz API n8n:", key_widget), ("ID tabeli:", self._table),
                              ("Kolumna słowa:", self._word), ("Kolumna flagi:", self._flag)):
            form.addRow(label, widget)
        body.addLayout(form)
        body.addWidget(hint_label("Zmiany połączenia działają po ponownym otwarciu panelu kolejki.", small=True))
        layout.addWidget(queue)

        access, body = collapsible_section("Kolejka słówek — Cloudflare Access")
        form = QFormLayout()
        self._cf_id = QLineEdit(q.get("cf_client_id", ""))
        self._cf_id.setPlaceholderText("puste = bez Cloudflare Access")
        secret_widget, self._cf_secret = _api_key_widget(q.get("cf_client_secret", ""))
        form.addRow("Client ID:", self._cf_id)
        form.addRow("Client Secret:", secret_widget)
        body.addLayout(form)
        body.addWidget(hint_label(
            "Token jest wysyłany tylko przez HTTPS. Reguła Access dla domeny musi mieć akcję „Service Auth”.",
            small=True))
        layout.addWidget(access)
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
        cfg.setdefault("word_queue", {}).update({
            "n8n_url": self._url.text().strip(),
            "fallback_url": self._fallback.text().strip(),
            "api_key": self._key.text().strip(),
            "cf_client_id": self._cf_id.text().strip(),
            "cf_client_secret": self._cf_secret.text().strip(),
            "table_id": self._table.text().strip(),
            "word_column": self._word.text().strip(),
            "flag_column": self._flag.text().strip(),
        })
