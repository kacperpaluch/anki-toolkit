"""Panel ustawień: kolejka słówek n8n, „AI: znaczenia” i Web Bridge.

Lista dostawców i modeli pochodzi z sekcji `ai_generator` — tam są klucze.
"""
from aqt.qt import QPushButton, QComboBox, QFormLayout, QGroupBox, QLineEdit, QSizePolicy, QSpinBox, QWidget

from ..common.ui import (
    _api_key_widget, hint_label, scroll_panel, collapsible_section, set_effort_choices,
)
from . import ai_senses


class IntegrationsTab(QWidget):
    def __init__(self, cfg: dict, provider_settings=None):
        super().__init__()
        layout = scroll_panel(self)
        q = cfg.get("word_queue") or {}
        self._providers = dict((cfg.get("ai_generator") or {}).get("providers") or {})
        self._provider_settings = provider_settings or (
            lambda name: self._providers.get(name, {}))

        ai = QGroupBox("AI: znaczenia")
        form = QFormLayout(ai)
        form.addRow(hint_label("Model dopasowuje definicje. Treść kart pochodzi ze słowników.", small=True))
        self._provider = QComboBox()
        self._provider.addItem("— nie wybrano —", "")
        for key, label in getattr(ai_senses._providers(), "PROVIDER_LABELS", {}).items():
            configured = key in self._providers
            self._provider.addItem(label if configured else f"{label} (nieskonfigurowany)", key)
        self._provider.setCurrentIndex(max(0, self._provider.findData(q.get("ai_provider", ""))))
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.lineEdit().setPlaceholderText("puste = model domyślny dostawcy")
        self._effort = QComboBox()
        self._effort.setToolTip(
            "Poziom rozumowania dla dopasowania definicji. Dziedzicz = ustawienie\n"
            "dostawcy w AI Generatorze. Dostępność poziomów zależy od modelu i wersji CLI.")
        self._fill_effort(q.get("ai_reasoning_effort"))
        self._provider.currentIndexChanged.connect(lambda _i: self._fill_effort())
        self._provider.currentIndexChanged.connect(lambda _i: self._fill_models())
        self._fill_models(q.get("ai_model", ""))
        self._senses = QSpinBox()
        self._senses.setRange(1, 10)
        self._senses.setMaximumWidth(100)
        self._senses.setValue(int(q.get("ai_max_senses", 3) or 3))
        self._senses.setToolTip("Pozostałe znaczenia nadal widzisz i możesz zaznaczyć ręcznie.")
        for combo in (self._provider, self._model, self._effort):
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for label, widget in (("Dostawca AI:", self._provider), ("Model:", self._model),
                              ("Poziom rozumowania:", self._effort),
                              ("Domyślnie zaznacz znaczeń:", self._senses)):
            form.addRow(label, widget)
        layout.addWidget(ai)

        self._fields_section, body = collapsible_section("Pola notatki, tagi i limit czasu")
        form = QFormLayout()
        fields = q.get("ai_fields") or {}
        self._field = QLineEdit(q.get("word_field", "ang"))
        self._pl = QLineEdit(fields.get("pl", "pol"))
        self._definition = QLineEdit(fields.get("definition", "def"))
        self._example = QLineEdit(fields.get("example", "przyklad"))
        self._example.setToolTip("Cel przycisków „+ przykład” na stronach słowników. AI go nie wypełnia.")
        self._tag = QLineEdit(q.get("ai_tag", ""))
        self._review_tag = QLineEdit(q.get("ai_review_tag", ""))
        for field in (self._tag, self._review_tag):
            field.setPlaceholderText("puste = bez tagu")
            field.setToolTip("Kilka tagów rozdziel spacją lub przecinkiem.")
        self._review_tag.setToolTip("Definicje dobrane przez AI, przy których odznaczysz „Sprawdziłem…” albo zmienisz treść.\n"
                                    "Kilka tagów rozdziel spacją lub przecinkiem.")
        self._timeout = QSpinBox()
        self._timeout.setRange(10, 600)
        self._timeout.setMaximumWidth(120)
        self._timeout.setSuffix(" s")
        self._timeout.setValue(int(q.get("ai_timeout", 120) or 120))
        for label, widget in (("Pole angielskie:", self._field), ("Pole polskie:", self._pl),
                              ("Pole definicji:", self._definition), ("Pole przykładu:", self._example),
                              ("Tag kart z AI:", self._tag), ("Tag do weryfikacji:", self._review_tag),
                              ("Limit czasu:", self._timeout)):
            form.addRow(label, widget)
        body.addLayout(form)
        layout.addWidget(self._fields_section)

        queue, body = collapsible_section("Połączenie z n8n")
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

        access, body = collapsible_section("Cloudflare Access")
        form = QFormLayout()
        self._cf_id = QLineEdit(q.get("cf_client_id", ""))
        self._cf_id.setPlaceholderText("puste = bez Cloudflare Access")
        secret_widget, self._cf_secret = _api_key_widget(q.get("cf_client_secret", ""))
        form.addRow("Client ID:", self._cf_id)
        form.addRow("Client Secret:", secret_widget)
        body.addLayout(form)
        info, info_body = collapsible_section("Więcej informacji")
        info_body.addWidget(hint_label(
            "Token jest wysyłany tylko przez HTTPS. Reguła Access dla domeny musi mieć akcję „Service Auth”.",
            small=True))
        body.addWidget(info)
        layout.addWidget(access)

        bridge, body = collapsible_section("Web Bridge")
        form = QFormLayout()
        self._port = QSpinBox()
        self._port.setRange(1024, 65535)
        self._port.setMaximumWidth(120)
        self._port.setValue(int((cfg.get("web_bridge") or {}).get("port") or 8767))
        form.addRow("Port lokalny:", self._port)
        self._port.setToolTip("Nasłuch tylko na 127.0.0.1. Ten sam port ustaw w userscripcie.")
        body.addLayout(form)
        body.addWidget(hint_label("Zmiana portu wymaga restartu Anki.", small=True))
        layout.addWidget(bridge)
        layout.addStretch()

    def refresh_provider_defaults(self, *_args):
        self._fill_effort(self._effort.currentData())

    def _fill_effort(self, current=None):
        name = self._provider.currentData() or ""
        levels = getattr(ai_senses._providers(), "CLI_REASONING_EFFORTS", {}).get(name, [])
        default = self._provider_settings(name).get("reasoning_effort")
        set_effort_choices(self._effort, levels, default, current)

    def _fill_models(self, current=None):
        """Modele znane dla wybranego dostawcy. Pole zostaje edytowalne."""
        if current is None:
            current = self._model.currentText()
        cfg = self._providers.get(self._provider.currentData() or "", {})
        known = {cfg.get("model", "")} | set(cfg.get("cached_models") or [])
        self._model.clear()
        self._model.addItem("")
        self._model.addItems(sorted(m for m in known if m))
        self._model.setCurrentText(current or "")

    def validate(self):
        error = ai_senses.validate_mapping({
            "word_field": self._field.text().strip(),
            "ai_fields": {"pl": self._pl.text().strip(),
                          "definition": self._definition.text().strip(),
                          "example": self._example.text().strip()},
        })
        if error:
            self._fields_section.findChild(QPushButton).setChecked(True)
        return error

    def apply(self, cfg: dict) -> None:
        fields = cfg.setdefault("word_queue", {}).setdefault("ai_fields", {})
        cfg["word_queue"].update({
            "n8n_url": self._url.text().strip(),
            "fallback_url": self._fallback.text().strip(),
            "api_key": self._key.text().strip(),
            "cf_client_id": self._cf_id.text().strip(),
            "cf_client_secret": self._cf_secret.text().strip(),
            "table_id": self._table.text().strip(),
            "word_field": self._field.text().strip(),
            "word_column": self._word.text().strip(),
            "flag_column": self._flag.text().strip(),
            "ai_provider": self._provider.currentData() or "",
            "ai_model": self._model.currentText().strip(),
            "ai_max_senses": self._senses.value(),
            "ai_timeout": self._timeout.value(),
            "ai_tag": " ".join(ai_senses.parse_tags(self._tag.text())),
            "ai_review_tag": " ".join(ai_senses.parse_tags(self._review_tag.text())),
            "ai_fields": {**fields, "pl": self._pl.text().strip(),
                          "definition": self._definition.text().strip(),
                          "example": self._example.text().strip()},
        })
        effort = self._effort.currentData()
        if effort:
            cfg["word_queue"]["ai_reasoning_effort"] = effort
        else:
            cfg["word_queue"].pop("ai_reasoning_effort", None)
        cfg.setdefault("web_bridge", {})["port"] = self._port.value()
