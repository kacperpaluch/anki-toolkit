"""Statystyki tab — AI usage dashboard (tokens, requests, fields, notes)."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QDateEdit, QDate, Qt,
)

from ..common.ui import hint_label

_CUSTOM = "custom"

# (etykieta, liczba dni; None = całość, _CUSTOM = własny zakres dat)
_RANGES = [
    ("Dziś", 1),
    ("Ostatnie 7 dni", 7),
    ("Ostatnie 30 dni", 30),
    ("Ostatnie 365 dni", 365),
    ("Wszystko", None),
    ("Własny zakres", _CUSTOM),
]


def _fmt(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _fmt_cost(value: float) -> str:
    if value >= 100:
        return f"${value:,.2f}"
    return f"${value:.4f}"


class StatsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        pricing_cfg = cfg.get("pricing", {})
        # Matched prices: {stat_key: [input_usd_per_token, output_usd_per_token]}
        # (for TTS: [usd_per_char, 0]). Derived from the catalog on refresh.
        self._pricing: dict = dict(pricing_cfg.get("models", {}))
        # Full OpenRouter price catalog {model_id: [in, out]} — persisted, so
        # models that appear in stats later are matched without re-fetching.
        self._catalog: dict = dict(pricing_cfg.get("catalog", {}))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Zakres:"))
        self._range = QComboBox()
        for label, days in _RANGES:
            self._range.addItem(label, days)
        self._range.setCurrentIndex(4)  # domyślnie: Wszystko
        self._range.currentIndexChanged.connect(self._on_range_changed)
        range_row.addWidget(self._range)

        today = QDate.currentDate()
        self._date_from_label = QLabel("od:")
        self._date_from = QDateEdit(QDate(today.year(), today.month(), 1))
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.dateChanged.connect(self._refresh)
        self._date_to_label = QLabel("do:")
        self._date_to = QDateEdit(today)
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.dateChanged.connect(self._refresh)
        range_row.addWidget(self._date_from_label)
        range_row.addWidget(self._date_from)
        range_row.addWidget(self._date_to_label)
        range_row.addWidget(self._date_to)

        range_row.addStretch()
        layout.addLayout(range_row)
        self._set_custom_visible(False)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._summary)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Model", "Requesty", "Błędy", "Tokeny wej.", "Tokeny wyj.", "Pola", "Koszt (szac.)"]
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        # -- TTS usage (audio generation) --
        self._tts_label = QLabel("TTS — generowanie audio")
        self._tts_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._tts_label)

        self._tts_table = QTableWidget(0, 6)
        self._tts_table.setHorizontalHeaderLabels(
            ["Model", "Requesty", "Błędy", "Znaki", "Pliki", "Koszt (szac.)"]
        )
        self._tts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tts_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tts_table.verticalHeader().setVisible(False)
        self._tts_table.setMaximumHeight(100)
        tts_header = self._tts_table.horizontalHeader()
        tts_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            tts_header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._tts_table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Odśwież")
        refresh_btn.clicked.connect(self._refresh)
        self._prices_btn = QPushButton("Pobierz ceny (OpenRouter)")
        self._prices_btn.setToolTip(
            "Pobiera cennik modeli z OpenRouter i dopasowuje go do modeli "
            "z Twoich statystyk. Koszt jest szacunkiem (ceny katalogowe OpenRouter)."
        )
        self._prices_btn.clicked.connect(self._fetch_prices)
        reset_btn = QPushButton("Resetuj statystyki")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(self._prices_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(hint_label(
            "Statystyki obejmują wywołania AI Generatora (przycisk AI, batch, workflow) "
            "oraz generowanie audio TTS (Kokoro i OpenRouter — requesty, znaki, pliki) "
            "i są zliczane per dzień — zakres powyżej agreguje dni kalendarzowe. "
            "Tokeny pochodzą z pola usage w odpowiedziach API — niektóre modele/proxy mogą go nie zwracać "
            "(wtedy liczone są tylko requesty). Koszt to szacunek wg cennika OpenRouter "
            "(przycisk „Pobierz ceny”; TTS rozliczane per znak); „—” = brak dopasowanej ceny, "
            "np. lokalne Kokoro jest darmowe. Dane są lokalne (user_files/usage_stats.json)."
        ))

        self._refresh()

    def _set_custom_visible(self, visible: bool) -> None:
        for w in (self._date_from_label, self._date_from,
                  self._date_to_label, self._date_to):
            w.setVisible(visible)

    def _on_range_changed(self) -> None:
        self._set_custom_visible(self._range.currentData() == _CUSTOM)
        self._refresh()

    def _match_prices_from_catalog(self, stat_keys: list) -> None:
        """Update self._pricing for the given keys using the stored catalog."""
        if not self._catalog:
            return
        from ..ai_generator import stats
        catalog_models = [
            {"id": model_id, "prompt_price": prices[0], "completion_price": prices[1]}
            for model_id, prices in self._catalog.items()
            if isinstance(prices, (list, tuple)) and len(prices) >= 2
        ]
        matched = stats.match_pricing(stat_keys, catalog_models)
        self._pricing.update({k: list(v) for k, v in matched.items()})

    def _refresh(self) -> None:
        from ..ai_generator import stats

        selected = self._range.currentData()
        if selected == _CUSTOM:
            start = self._date_from.date().toString("yyyy-MM-dd")
            end = self._date_to.date().toString("yyyy-MM-dd")
            data = stats.get_stats(start=start, end=end)
            range_label = f"Zakres: {start} – {end}"
        else:
            data = stats.get_stats(days=selected)
            range_label = (
                f"Od: {data.get('since', '?')}"
                if selected is None
                else self._range.currentText()
            )
        models = data.get("models", {})
        tts_models = data.get("tts", {})
        self._match_prices_from_catalog(list(models.keys()) + list(tts_models.keys()))

        def _model_cost(name: str, m: dict):
            prices = self._pricing.get(name)
            if not prices:
                return None
            try:
                in_price, out_price = float(prices[0]), float(prices[1])
            except (TypeError, ValueError, IndexError):
                return None
            return (
                m.get("input_tokens", 0) * in_price
                + m.get("output_tokens", 0) * out_price
            )

        total_req = sum(m.get("requests", 0) for m in models.values())
        total_err = sum(m.get("errors", 0) for m in models.values())
        total_in = sum(m.get("input_tokens", 0) for m in models.values())
        total_out = sum(m.get("output_tokens", 0) for m in models.values())
        costs = {name: _model_cost(name, m) for name, m in models.items()}
        known_costs = [c for c in costs.values() if c is not None]
        summary = (
            f"{range_label}    ·    "
            f"Zaktualizowane notatki: {_fmt(data.get('notes_processed', 0))}    ·    "
            f"Requesty: {_fmt(total_req)} (błędy: {_fmt(total_err)})    ·    "
            f"Tokeny: {_fmt(total_in)} wej. / {_fmt(total_out)} wyj."
        )
        if known_costs:
            suffix = "" if len(known_costs) == len(models) else " (część modeli bez ceny)"
            summary += f"    ·    Koszt: ~{_fmt_cost(sum(known_costs))}{suffix}"

        # TTS — audio generation usage
        def _tts_cost(name: str, t: dict):
            prices = self._pricing.get(name)
            if not prices:
                return None
            try:
                per_char = float(prices[0])
            except (TypeError, ValueError, IndexError):
                return None
            return t.get("chars", 0) * per_char

        tts_costs = {name: _tts_cost(name, t) for name, t in tts_models.items()}
        if tts_models:
            tts_files = sum(t.get("files", 0) for t in tts_models.values())
            tts_chars = sum(t.get("chars", 0) for t in tts_models.values())
            summary += f"    ·    TTS: {_fmt(tts_files)} plików / {_fmt(tts_chars)} zn."
            known_tts = [c for c in tts_costs.values() if c is not None]
            if known_tts:
                summary += f" (~{_fmt_cost(sum(known_tts))})"
        self._summary.setText(summary)

        self._tts_label.setVisible(bool(tts_models))
        self._tts_table.setVisible(bool(tts_models))
        tts_rows = sorted(
            tts_models.items(), key=lambda kv: kv[1].get("requests", 0), reverse=True
        )
        self._tts_table.setRowCount(len(tts_rows))
        for i, (name, t) in enumerate(tts_rows):
            cost = tts_costs.get(name)
            values = [
                name,
                t.get("requests", 0),
                t.get("errors", 0),
                t.get("chars", 0),
                t.get("files", 0),
                _fmt_cost(cost) if cost is not None else "—",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(_fmt(val) if isinstance(val, int) else str(val))
                if col > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._tts_table.setItem(i, col, item)

        rows = sorted(
            models.items(), key=lambda kv: kv[1].get("requests", 0), reverse=True
        )
        self._table.setRowCount(len(rows))
        for i, (name, m) in enumerate(rows):
            cost = costs.get(name)
            values = [
                name,
                m.get("requests", 0),
                m.get("errors", 0),
                m.get("input_tokens", 0),
                m.get("output_tokens", 0),
                m.get("fields", 0),
                _fmt_cost(cost) if cost is not None else "—",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(_fmt(val) if isinstance(val, int) else str(val))
                if col > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(i, col, item)

    def _fetch_prices(self) -> None:
        """Fetch the OpenRouter price list and match it to models seen in stats."""
        from aqt import mw
        from aqt.utils import showWarning, tooltip

        self._prices_btn.setEnabled(False)
        self._prices_btn.setText("Pobieranie...")

        def task():
            from ..ai_generator.providers.model_discovery import fetch_openrouter_chat_models
            from ..tts.api import fetch_openrouter_tts_models
            chat_catalog = fetch_openrouter_chat_models(force=True)
            tts_catalog = fetch_openrouter_tts_models(force=True)
            catalog_map: dict = {}
            for m in list(chat_catalog) + list(tts_catalog):
                prompt_price = m.get("prompt_price")
                completion_price = m.get("completion_price")
                if prompt_price is None and completion_price is None:
                    continue
                model_id = m.get("id")
                if model_id:
                    catalog_map[model_id] = [
                        float(prompt_price or 0.0),
                        float(completion_price or 0.0),
                    ]
            return catalog_map

        def on_done(fut):
            try:
                try:
                    catalog_map = fut.result()
                except Exception:
                    catalog_map = {}
                self._prices_btn.setEnabled(True)
                self._prices_btn.setText("Pobierz ceny (OpenRouter)")
                if not catalog_map:
                    showWarning(
                        "Nie udało się pobrać cennika z OpenRouter.\n"
                        "Sprawdź połączenie z internetem."
                    )
                    return
                self._catalog = catalog_map

                # Persist immediately — the catalog should survive even if the
                # dialog is later cancelled. Matching against stats happens on
                # every refresh, so models that show up later get prices too.
                from ..common import get_full_config, save_full_config
                cfg = get_full_config()
                cfg.setdefault("pricing", {})["catalog"] = catalog_map
                save_full_config(cfg)

                self._refresh()
                tooltip(
                    f"Pobrano cennik {len(catalog_map)} modeli OpenRouter.",
                    period=4000,
                )
            except RuntimeError:
                pass  # dialog was closed while fetching

        mw.taskman.run_in_background(task, on_done)

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
