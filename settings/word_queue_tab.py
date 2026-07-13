"""Kolejka słówek — konfiguracja połączenia z n8n i mapowania kolumn."""

from aqt import mw
from aqt.qt import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, Qt, QVBoxLayout, QWidget,
)

from ..common.ui import (
    _api_key_widget, _expanding_line_edit, _filterable_combo, get_all_field_names,
    hint_label,
)

_PLACEHOLDER = "(kliknij „Pobierz listę”)"


class WordQueueTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        wq = cfg.get("word_queue", {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(hint_label(
            "Panel „Kolejka słówek” (przycisk 📚 w oknie „Dodaj”) bierze hasła z tabeli "
            "DataTable w n8n i po dodaniu karty odhacza wiersz.\n"
            "Adres zapasowy jest używany, gdy domowy nie odpowiada — np. Tailscale, "
            "gdy jesteś poza domem."
        ))
        layout.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)
        # Bez tego macOS trzyma pola przy sizeHint — adresy i klucz API są nieczytelne.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._url = _expanding_line_edit(wq.get("n8n_url", ""))
        self._url.setPlaceholderText("http://192.168.1.50:5678")
        form.addRow("Adres n8n (domowy)", self._url)

        self._fallback = _expanding_line_edit(wq.get("fallback_url", ""))
        self._fallback.setPlaceholderText("https://n8n.twoj-tailnet.ts.net")
        form.addRow("Adres zapasowy", self._fallback)

        key_container, self._api_key = _api_key_widget(wq.get("api_key", ""))
        form.addRow("Klucz API", key_container)

        table_row = QWidget()
        table_layout = QHBoxLayout(table_row)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self._table = QComboBox()
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._table.addItem(_PLACEHOLDER, wq.get("table_id", ""))
        table_layout.addWidget(self._table, 1)
        self._fetch_btn = QPushButton("Pobierz listę")
        self._fetch_btn.clicked.connect(self._load_tables)
        table_layout.addWidget(self._fetch_btn)
        form.addRow("Tabela", table_row)

        self._status = QLabel("")
        form.addRow("", self._status)

        self._word_field = _filterable_combo(get_all_field_names(), wq.get("word_field", "ang"))
        self._word_field.setToolTip("Pole notatki, do którego wpisywane jest hasło")
        form.addRow("Pole notatki", self._word_field)

        self._word_column = _expanding_line_edit(wq.get("word_column", "Slowko"))
        form.addRow("Kolumna z hasłem", self._word_column)

        self._flag_column = _expanding_line_edit(wq.get("flag_column", "Anki"))
        self._flag_column.setToolTip("Kolumna boolean: false = do zrobienia")
        form.addRow("Kolumna „zrobione”", self._flag_column)

        self._random = QCheckBox("Losowa kolejność słówek na starcie")
        self._random.setChecked(bool(wq.get("random_order", False)))
        form.addRow("", self._random)

        layout.addLayout(form)
        layout.addStretch()

    # -- pobieranie listy tabel ---------------------------------------------

    def _current_cfg(self) -> dict:
        """Wartości Z PÓL, nie z zapisanej konfiguracji — testujesz to, co widzisz."""
        return {
            "n8n_url": self._url.text().strip(),
            "fallback_url": self._fallback.text().strip(),
            "api_key": self._api_key.text().strip(),
        }

    def _load_tables(self) -> None:
        from ..word_queue import fetch_tables

        cfg = self._current_cfg()
        if not (cfg["n8n_url"] or cfg["fallback_url"]) or not cfg["api_key"]:
            self._status.setText("Uzupełnij adres i klucz API.")
            return

        wanted = self._table.currentData()  # zachowaj wybór między odświeżeniami
        self._fetch_btn.setEnabled(False)
        self._status.setText("Łączę…")

        def done(future):
            self._fetch_btn.setEnabled(True)
            try:
                tables, error = future.result()
            except Exception as e:  # noqa: BLE001
                self._status.setText(f"Błąd: {e}")
                return
            if error:
                self._status.setText(f"Nie udało się: {error}")
                return
            self._table.clear()
            for table in tables:
                self._table.addItem(table["name"], table["id"])
            index = self._table.findData(wanted)
            if index >= 0:
                self._table.setCurrentIndex(index)
            self._status.setText(f"Znaleziono {len(tables)} tabel.")

        mw.taskman.run_in_background(lambda: fetch_tables(cfg), done)

    # -- zapis ---------------------------------------------------------------

    def apply(self, cfg: dict) -> None:
        wq = cfg.setdefault("word_queue", {})
        wq["n8n_url"] = self._url.text().strip()
        wq["fallback_url"] = self._fallback.text().strip()
        wq["api_key"] = self._api_key.text().strip()
        # Placeholder trzyma table_id z konfiguracji, więc brak kliknięcia
        # „Pobierz listę” nie kasuje wybranej wcześniej tabeli.
        wq["table_id"] = self._table.currentData() or ""
        wq["word_field"] = self._word_field.currentText().strip()
        wq["word_column"] = self._word_column.text().strip()
        wq["flag_column"] = self._flag_column.text().strip()
        wq["random_order"] = self._random.isChecked()
