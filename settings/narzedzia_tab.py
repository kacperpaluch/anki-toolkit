"""Small configuration panels shared by the domain-oriented settings UI."""

from aqt.qt import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QCheckBox,
)

from ..common.ui import _expanding_line_edit, _scrollable, hint_label


def _csv(text: str) -> list:
    return [item.strip() for item in text.split(",") if item.strip()]


def _scroll_panel(widget: QWidget) -> None:
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    inner = QWidget()
    widget._panel_layout = QVBoxLayout(inner)
    widget._panel_layout.setContentsMargins(12, 12, 12, 12)
    widget._panel_layout.setSpacing(8)
    outer.addWidget(_scrollable(inner))


class FieldSplitterSettings(QWidget):
    """Field splitting belongs to content workflows, not system maintenance."""

    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        fs = cfg.get("field_splitter", {})
        group = QGroupBox("Rozdzielanie pól")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._source = _expanding_line_edit(fs.get("source_field", "przyklad"))
        self._separator = _expanding_line_edit(fs.get("separator", "<br><br>"))
        self._targets = _expanding_line_edit(
            fs.get("target_fields", "p1, p2, p3, p4, p5")
        )
        self._overwrite = QCheckBox(
            "Nadpisuj istniejące pola (inaczej wypełniaj tylko puste)"
        )
        self._overwrite.setChecked(fs.get("overwrite", True))
        form.addRow("Pole źródłowe:", self._source)
        form.addRow("Separator:", self._separator)
        form.addRow("Pola docelowe:", self._targets)
        form.addRow("", self._overwrite)
        form.addRow("", hint_label(
            "Ten etap jest dostępny w workflowach oraz w menu kontekstowym. "
            "Pole źródłowe nie jest modyfikowane.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        fs = cfg.setdefault("field_splitter", {})
        fs["source_field"] = self._source.text().strip()
        fs["separator"] = self._separator.text().strip()
        fs["target_fields"] = self._targets.text().strip()
        fs["overwrite"] = self._overwrite.isChecked()


class AudioEmbedSettings(QWidget):
    """Rewrite [sound:...] into inline <audio> players in chosen note types/fields."""

    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        ae = cfg.get("audio_embed", {})
        group = QGroupBox("Osadzanie audio — [sound:...] → <audio>")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._note_types = _expanding_line_edit(
            ", ".join(ae.get("note_types", ["angielski"]))
        )
        self._fields = _expanding_line_edit(
            ", ".join(ae.get("fields", ["przyklad", "p1", "p2", "p3", "p4", "p5"]))
        )
        self._css_class = _expanding_line_edit(ae.get("css_class", "ex-audio"))
        self._preload = _expanding_line_edit(ae.get("preload", "none"))
        self._scan_on_sync = QCheckBox("Skanuj kolekcję po synchronizacji")
        self._scan_on_sync.setChecked(ae.get("scan_on_sync", True))
        form.addRow("Typy notatek:", self._note_types)
        form.addRow("Pola:", self._fields)
        form.addRow("Klasa CSS:", self._css_class)
        form.addRow("preload:", self._preload)
        form.addRow("", self._scan_on_sync)
        form.addRow("", hint_label(
            "Zamienia [sound:plik.mp3] na <audio class=\"…\" src=\"plik.mp3\" "
            "preload=\"…\"></audio> w wybranych polach. Pole audio (główne) zostaw "
            "poza listą — zachowa klasyczne [sound:...]. Typy notatek puste = "
            "wszystkie. Operacja jest idempotentna.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        ae = cfg.setdefault("audio_embed", {})
        ae["note_types"] = _csv(self._note_types.text())
        ae["fields"] = _csv(self._fields.text())
        ae["css_class"] = self._css_class.text().strip()
        ae["preload"] = self._preload.text().strip()
        ae["scan_on_sync"] = self._scan_on_sync.isChecked()


class FilteredDeckSettings(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        fd = cfg.get("filtered_deck", {})
        group = QGroupBox("Presety powtórek — talia filtrowana")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._deck_name = _expanding_line_edit(
            fd.get("deck_name", "Angielski - Powtórka z wyprzedzeniem")
        )
        form.addRow("Nazwa bazowa talii:", self._deck_name)
        form.addRow("", hint_label(
            "Presety są uruchamiane z menu Narzędzia → Anki Toolkit.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("filtered_deck", {})["deck_name"] = (
            self._deck_name.text().strip()
        )


class HtmlCleanupSettings(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        _scroll_panel(self)
        values = cfg.get("nbsp_remover", {})
        group = QGroupBox("Czyszczenie pól HTML")
        box = QVBoxLayout(group)
        self._show_tooltip = QCheckBox("Pokazuj podsumowanie po wyczyszczeniu")
        self._show_tooltip.setChecked(values.get("show_tooltip", True))
        self._auto_run = QCheckBox("Automatycznie czyść kolekcję przy starcie Anki")
        self._auto_run.setChecked(values.get("auto_run_startup", False))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._skip_field = _expanding_line_edit(values.get("skip_field", "ang"))
        form.addRow("Pole traktowane jako zwykły tekst:", self._skip_field)
        box.addWidget(self._show_tooltip)
        box.addWidget(self._auto_run)
        box.addLayout(form)
        box.addWidget(hint_label(
            "Ręczne czyszczenie istniejących notatek pozostaje dostępne w menu "
            "Narzędzia → Anki Toolkit.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        values = cfg.setdefault("nbsp_remover", {})
        values["show_tooltip"] = self._show_tooltip.isChecked()
        values["auto_run_startup"] = self._auto_run.isChecked()
        values["skip_field"] = self._skip_field.text().strip()
