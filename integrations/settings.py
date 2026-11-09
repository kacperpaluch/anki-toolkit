"""Panel ustawień: kolejka słówek — pola notatki i Web Bridge.

Połączenie z n8n i klucze są na stronie „Konta i klucze” (`settings/accounts_tab.py`).
"""
from aqt.qt import QFormLayout, QGroupBox, QLineEdit, QSpinBox, QWidget

from ..common.ui import hint_label, scroll_panel, collapsible_section


class IntegrationsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        layout = scroll_panel(self)
        q = cfg.get("word_queue") or {}

        box = QGroupBox("Pola notatki")
        form = QFormLayout(box)
        form.addRow(hint_label("Hasło z kolejki trafia do pola angielskiego. Przyciski na stronach "
                               "słowników wpisują tłumaczenie, definicję i przykład.", small=True))
        fields = q.get("ai_fields") or {}
        self._field = QLineEdit(q.get("word_field", "ang"))
        self._pl = QLineEdit(fields.get("pl", "pol"))
        self._definition = QLineEdit(fields.get("definition", "def"))
        self._example = QLineEdit(fields.get("example", "przyklad"))
        for label, widget in (("Pole angielskie:", self._field), ("Pole polskie:", self._pl),
                              ("Pole definicji:", self._definition), ("Pole przykładu:", self._example)):
            form.addRow(label, widget)
        layout.addWidget(box)

        bridge, body = collapsible_section("Połączenie ze stronami słowników (Web Bridge)")
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

    def validate(self):
        if not self._field.text().strip():
            return "Kolejka słówek: podaj pole angielskie."
        return None

    def apply(self, cfg: dict) -> None:
        queue = cfg.setdefault("word_queue", {})
        queue["word_field"] = self._field.text().strip()
        queue["ai_fields"] = {**(queue.get("ai_fields") or {}), "pl": self._pl.text().strip(),
                              "definition": self._definition.text().strip(),
                              "example": self._example.text().strip()}
        cfg.setdefault("web_bridge", {})["port"] = self._port.value()
