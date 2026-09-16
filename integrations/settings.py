"""Panel ustawień: kolejka słówek n8n, „AI: znaczenia” i Web Bridge.

Lista dostawców i modeli pochodzi z sekcji `ai_generator` — tam są klucze.
"""
from aqt.qt import QComboBox, QFormLayout, QGroupBox, QLineEdit, QSizePolicy, QSpinBox, QWidget

from ..common.ui import _api_key_widget, hint_label, scroll_panel
from . import ai_senses


class IntegrationsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        layout = scroll_panel(self)
        q = cfg.get("word_queue") or {}

        queue = QGroupBox("Połączenie z n8n")
        form = QFormLayout(queue)
        form.addRow(hint_label(
            "Panel 📚 w oknie „Dodaj” pobiera DataTable z n8n. Najpierw próbuje adresu "
            "głównego, potem zapasowego. Zmiany działają po ponownym otwarciu panelu.",
            small=True))
        self._url = QLineEdit(q.get("n8n_url", ""))
        self._fallback = QLineEdit(q.get("fallback_url", ""))
        key_widget, self._key = _api_key_widget(q.get("api_key", ""))
        self._cf_id = QLineEdit(q.get("cf_client_id", ""))
        self._cf_id.setPlaceholderText("puste = bez Cloudflare Access")
        cf_secret_widget, self._cf_secret = _api_key_widget(q.get("cf_client_secret", ""))
        self._table = QLineEdit(q.get("table_id", ""))
        self._field = QLineEdit(q.get("word_field", "ang"))
        self._word = QLineEdit(q.get("word_column", "Slowko"))
        self._flag = QLineEdit(q.get("flag_column", "Anki"))
        for label, widget in (("Adres główny:", self._url), ("Adres zapasowy:", self._fallback),
                              ("Klucz API n8n:", key_widget),
                              ("CF Access Client ID:", self._cf_id),
                              ("CF Access Client Secret:", cf_secret_widget),
                              ("ID tabeli:", self._table),
                              ("Pole notatki:", self._field), ("Kolumna słowa:", self._word),
                              ("Kolumna flagi:", self._flag)):
            form.addRow(label, widget)
        form.addRow(hint_label(
            "Token Cloudflare Access (service token) jest wysyłany tylko na adresy "
            "https — adres w sieci lokalnej go nie dostaje. Reguła Access dla domeny "
            "musi mieć akcję „Service Auth”.", small=True))
        layout.addWidget(queue)

        ai = QGroupBox("AI: znaczenia")
        form = QFormLayout(ai)
        form.addRow(hint_label(
            "Przycisk „AI: znaczenia” w panelu robi z jednego hasła po jednej karcie na "
            "każde znaczenie. Definicje są dosłownymi cytatami ze słowników otwartych "
            "w zakładkach — model je dopasowuje, nie tłumaczy.", small=True))
        fields = q.get("ai_fields") or {}
        self._providers = dict((cfg.get("ai_generator") or {}).get("providers") or {})
        self._provider = QComboBox()
        self._provider.addItem("— nie wybrano —", "")
        for key, label in getattr(ai_senses._providers(), "PROVIDER_LABELS", {}).items():
            configured = key in self._providers
            self._provider.addItem(label if configured else f"{label} (nieskonfigurowany)", key)
        index = self._provider.findData(q.get("ai_provider", ""))
        self._provider.setCurrentIndex(max(0, index))
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.lineEdit().setPlaceholderText("puste = model domyślny dostawcy")
        self._provider.currentIndexChanged.connect(lambda _i: self._fill_models())
        self._fill_models(q.get("ai_model", ""))
        for combo in (self._provider, self._model):
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._senses = QSpinBox()
        self._senses.setRange(1, 10)
        self._senses.setValue(int(q.get("ai_max_senses", 3) or 3))
        self._senses.setToolTip("Ile kart maksymalnie powstaje z jednego hasła")
        self._timeout = QSpinBox()
        self._timeout.setRange(10, 600)
        self._timeout.setSuffix(" s")
        self._timeout.setValue(int(q.get("ai_timeout", 120) or 120))
        self._timeout.setToolTip("Lokalne CLI (Codex, Claude) myśli dłużej niż API")
        self._tag = QLineEdit(q.get("ai_tag", ""))
        self._tag.setPlaceholderText("puste = bez tagu")
        self._review_tag = QLineEdit(q.get("ai_review_tag", ""))
        self._review_tag.setPlaceholderText("puste = bez tagu")
        self._pl = QLineEdit(fields.get("pl", "pol"))
        self._definition = QLineEdit(fields.get("definition", "def"))
        self._example = QLineEdit(fields.get("example", "przyklad"))
        for label, widget in (("Dostawca AI:", self._provider), ("Model:", self._model),
                              ("Maks. znaczeń z hasła:", self._senses),
                              ("Limit czasu:", self._timeout),
                              ("Tag kart z AI:", self._tag),
                              ("Tag do weryfikacji:", self._review_tag),
                              ("Pole polskie:", self._pl), ("Pole definicji:", self._definition),
                              ("Pole przykładu:", self._example)):
            form.addRow(label, widget)
        form.addRow(hint_label(
            "Pole angielskie to „Pole notatki” z kolejki. Tagi rozdzielaj spacją lub "
            "przecinkiem; tag do weryfikacji znika tylko po ręcznym potwierdzeniu w podglądzie.", small=True))
        layout.addWidget(ai)

        bridge = QGroupBox("Web Bridge")
        form = QFormLayout(bridge)
        self._port = QSpinBox()
        self._port.setRange(1024, 65535)
        self._port.setValue(int((cfg.get("web_bridge") or {}).get("port") or 8767))
        form.addRow("Port (127.0.0.1):", self._port)
        form.addRow(hint_label(
            "Ten sam port musi być w stałej ENDPOINT userscriptu. Zmiana działa po "
            "restarcie Anki.", small=True))
        layout.addWidget(bridge)
        layout.addStretch()

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
        return ai_senses.validate_mapping({
            "word_field": self._field.text().strip(),
            "ai_fields": {"pl": self._pl.text().strip(),
                          "definition": self._definition.text().strip(),
                          "example": self._example.text().strip()},
        })

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
        cfg.setdefault("web_bridge", {})["port"] = self._port.value()
