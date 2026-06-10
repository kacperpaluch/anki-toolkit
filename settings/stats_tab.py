"""Statystyki tab — AI usage dashboard (tokens, requests, fields, notes)."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, Qt,
)

# (etykieta, liczba dni; None = całość)
_RANGES = [
    ("Dziś", 1),
    ("Ostatnie 7 dni", 7),
    ("Ostatnie 30 dni", 30),
    ("Ostatnie 365 dni", 365),
    ("Wszystko", None),
]


def _fmt(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class StatsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Zakres:"))
        self._range = QComboBox()
        for label, days in _RANGES:
            self._range.addItem(label, days)
        self._range.setCurrentIndex(len(_RANGES) - 1)  # domyślnie: Wszystko
        self._range.currentIndexChanged.connect(self._refresh)
        range_row.addWidget(self._range)
        range_row.addStretch()
        layout.addLayout(range_row)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._summary)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Model", "Requesty", "Błędy", "Tokeny wej.", "Tokeny wyj.", "Pola"]
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Odśwież")
        refresh_btn.clicked.connect(self._refresh)
        reset_btn = QPushButton("Resetuj statystyki")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        hint = QLabel(
            "Statystyki obejmują wywołania AI Generatora (przycisk AI, batch, workflow) "
            "i są zliczane per dzień — zakres powyżej agreguje dni kalendarzowe. "
            "Tokeny pochodzą z pola usage w odpowiedziach API — niektóre modele/proxy mogą go nie zwracać "
            "(wtedy liczone są tylko requesty). Dane są lokalne (usage_stats.json) i nie zawierają cen."
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._refresh()

    def _refresh(self) -> None:
        from ..ai_generator import stats

        days = self._range.currentData()
        data = stats.get_stats(days=days)
        models = data.get("models", {})

        total_req = sum(m.get("requests", 0) for m in models.values())
        total_err = sum(m.get("errors", 0) for m in models.values())
        total_in = sum(m.get("input_tokens", 0) for m in models.values())
        total_out = sum(m.get("output_tokens", 0) for m in models.values())
        prefix = (
            f"Od: {data.get('since', '?')}"
            if days is None
            else self._range.currentText()
        )
        self._summary.setText(
            f"{prefix}    ·    "
            f"Zaktualizowane notatki: {_fmt(data.get('notes_processed', 0))}    ·    "
            f"Requesty: {_fmt(total_req)} (błędy: {_fmt(total_err)})    ·    "
            f"Tokeny: {_fmt(total_in)} wej. / {_fmt(total_out)} wyj."
        )

        rows = sorted(
            models.items(), key=lambda kv: kv[1].get("requests", 0), reverse=True
        )
        self._table.setRowCount(len(rows))
        for i, (name, m) in enumerate(rows):
            values = [
                name,
                m.get("requests", 0),
                m.get("errors", 0),
                m.get("input_tokens", 0),
                m.get("output_tokens", 0),
                m.get("fields", 0),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(_fmt(val) if isinstance(val, int) else str(val))
                if col > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(i, col, item)

    def _reset(self) -> None:
        result = QMessageBox.question(
            self,
            "Resetuj statystyki",
            "Wyzerować wszystkie statystyki użycia AI?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            from ..ai_generator import stats
            stats.reset_stats()
            self._refresh()

    def apply(self, cfg: dict) -> None:
        return
