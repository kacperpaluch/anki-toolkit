"""Narzędzia tab — filtered deck, HTML cleanup, field splitter, sibling manager."""

from aqt.qt import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QCheckBox, QSpinBox,
)

from ..common.ui import _expanding_line_edit, _scrollable, hint_label


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
        nbsp_group = QGroupBox("Czyszczenie HTML")
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

        layout.addSpacing(8)

        fs = cfg.get("field_splitter", {})
        fs_group = QGroupBox("Rozdzielanie pól")
        fs_form = QFormLayout(fs_group)
        fs_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._fs_source = _expanding_line_edit(fs.get("source_field", "przyklad"))
        self._fs_separator = _expanding_line_edit(fs.get("separator", "<br><br>"))
        self._fs_targets = _expanding_line_edit(fs.get("target_fields", "p1, p2, p3, p4, p5"))
        fs_form.addRow("Pole źródłowe:", self._fs_source)
        fs_form.addRow("Separator:", self._fs_separator)
        fs_form.addRow("Pola docelowe (przecinkami):", self._fs_targets)
        self._fs_overwrite = QCheckBox("Nadpisuj istniejące pola (w przeciwnym razie wypełnia tylko puste)")
        self._fs_overwrite.setChecked(fs.get("overwrite", True))
        fs_form.addRow("", self._fs_overwrite)
        fs_hint = hint_label(
            "Kopiuje zawartość pola źródłowego rozdzieloną separatorem "
            "do kolejnych pól docelowych. Pole źródłowe nie jest modyfikowane.",
            small=True,
        )
        fs_form.addRow("", fs_hint)
        layout.addWidget(fs_group)

        layout.addSpacing(8)

        sm = cfg.get("sibling_manager", {})
        sm_group = QGroupBox("Sibling Manager — dynamiczne zawieszanie siblingów")
        sm_form = QFormLayout(sm_group)
        sm_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._sm_interval = QSpinBox()
        self._sm_interval.setRange(1, 365)
        self._sm_interval.setSuffix(" dni")
        self._sm_interval.setValue(sm.get("interval", 30))
        sm_form.addRow("Próg dojrzałości (interval):", self._sm_interval)
        self._sm_tag = _expanding_line_edit(sm.get("tag", "tk-sib-suspended"))
        sm_form.addRow("Tag zawieszonych:", self._sm_tag)
        self._sm_ignore_tag = _expanding_line_edit(sm.get("ignore_tag", "tk-sib-ignored"))
        sm_form.addRow("Tag ignorowanych:", self._sm_ignore_tag)
        self._sm_show_tooltip = QCheckBox("Pokazuj tooltip po synchronizacji (sync catch-up)")
        self._sm_show_tooltip.setChecked(sm.get("show_tooltip", True))
        sm_form.addRow("", self._sm_show_tooltip)
        sm_hint = hint_label(
            "Po odpowiedzi na kartę: jeśli interval < próg → zawiesza inne NEW siblingi. "
            "Gdy karta dojrzeje (interval ≥ próg) → uwalnia wszystkie zawieszone. "
            "Karty w nauce/review nie są dotykane. "
            "Tag ignorowanych wyłącza moduł dla danej notatki.",
            small=True,
        )
        sm_form.addRow("", sm_hint)
        layout.addWidget(sm_group)

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

        cfg.setdefault("field_splitter", {})
        cfg["field_splitter"]["source_field"] = self._fs_source.text().strip()
        cfg["field_splitter"]["separator"] = self._fs_separator.text().strip()
        cfg["field_splitter"]["target_fields"] = self._fs_targets.text().strip()
        cfg["field_splitter"]["overwrite"] = self._fs_overwrite.isChecked()

        cfg.setdefault("sibling_manager", {})
        cfg["sibling_manager"]["interval"] = self._sm_interval.value()
        cfg["sibling_manager"]["tag"] = self._sm_tag.text().strip()
        cfg["sibling_manager"]["ignore_tag"] = self._sm_ignore_tag.text().strip()
        cfg["sibling_manager"]["show_tooltip"] = self._sm_show_tooltip.isChecked()
