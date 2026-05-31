"""Narzędzia tab — Filtered Deck, nbsp Remover."""

from aqt.qt import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QCheckBox,
)

from ..common.ui import _expanding_line_edit, _scrollable


class NarzedziaTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)

        fd = cfg.get("filtered_deck", {})
        fd_group = QGroupBox("Talia filtrowana")
        fd_form = QFormLayout(fd_group)
        fd_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._deck_name = _expanding_line_edit(
            fd.get("deck_name", "Angielski - Powtórka z wyprzedzeniem")
        )
        self._search_deck = _expanding_line_edit(
            fd.get("search_deck", "angielski")
        )
        fd_form.addRow("Nazwa tworzonej talii:", self._deck_name)
        fd_form.addRow("Wyszukiwana talia (deck:):", self._search_deck)
        layout.addWidget(fd_group)
        layout.addSpacing(8)

        s = cfg.get("nbsp_remover", {})
        nbsp_group = QGroupBox("nbsp Remover")
        nbsp_vlayout = QVBoxLayout(nbsp_group)
        self._show_tooltip_cb = QCheckBox("Pokazuj tooltip po wyczyszczeniu")
        self._show_tooltip_cb.setChecked(s.get("show_tooltip", True))
        self._auto_run_startup = QCheckBox(
            "Automatycznie czyść kolekcję przy starcie Anki"
        )
        self._auto_run_startup.setChecked(s.get("auto_run_startup", False))
        nbsp_form = QFormLayout()
        nbsp_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._skip_field = _expanding_line_edit(s.get("skip_field", "ang"))
        nbsp_form.addRow("Pole pomijane (usuń <div>):", self._skip_field)
        nbsp_vlayout.addWidget(self._show_tooltip_cb)
        nbsp_vlayout.addWidget(self._auto_run_startup)
        nbsp_vlayout.addLayout(nbsp_form)
        layout.addWidget(nbsp_group)

        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scrollable(inner))

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("filtered_deck", {})
        cfg["filtered_deck"]["deck_name"] = self._deck_name.text().strip()
        cfg["filtered_deck"]["search_deck"] = self._search_deck.text().strip()

        cfg.setdefault("nbsp_remover", {})
        cfg["nbsp_remover"]["show_tooltip"] = self._show_tooltip_cb.isChecked()
        cfg["nbsp_remover"]["auto_run_startup"] = self._auto_run_startup.isChecked()
        cfg["nbsp_remover"]["skip_field"] = self._skip_field.text().strip()
