"""Field-splitting settings panel."""

from aqt.qt import (
    QWidget, QFormLayout, QGroupBox, QCheckBox, QSizePolicy,
)

from ..common.ui import (
    _expanding_line_edit, _filterable_combo, get_all_field_names, hint_label, scroll_panel,
)


def _csv(text: str) -> list:
    return [item.strip() for item in text.split(",") if item.strip()]


class FieldSplitterSettings(QWidget):
    """Field splitting belongs to content workflows, not system maintenance."""

    def __init__(self, cfg: dict):
        super().__init__()
        self._panel_layout = scroll_panel(self)
        fs = cfg.get("field_splitter", {})
        group = QGroupBox("Ustawienia")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._source = _filterable_combo(get_all_field_names(), fs.get("source_field", "przyklad"))
        self._source.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        form.addRow(hint_label(
            "Ten etap jest dostępny w sekwencjach oraz w menu kontekstowym. "
            "Pole źródłowe nie jest modyfikowane.", small=True,
        ))
        self._panel_layout.addWidget(group)
        self._panel_layout.addStretch()
        self._initial = (self._source.currentText().strip(), self._targets.text())

    def validate(self) -> str | None:
        """Literówka w nazwie pola po cichu nic by nie rozdzieliła.

        Tylko po zmianie: zapisany już config (np. domyślne p1…p5) nie może
        blokować zapisu ustawień innych stron."""
        current = (self._source.currentText().strip(), self._targets.text())
        if current == self._initial:
            return None
        known = set(get_all_field_names())  # [] bez kolekcji — wtedy nie ma z czym porównać
        unknown = [f for f in [current[0], *_csv(current[1])] if known and f not in known]
        if unknown:
            return f"Rozdzielanie pól: żaden typ notatki nie ma pól: {', '.join(unknown)}."
        return None

    def apply(self, cfg: dict) -> None:
        fs = cfg.setdefault("field_splitter", {})
        source = self._source.currentText().strip()
        fs["source_field"] = source
        fs["separator"] = self._separator.text().strip()
        # The source among the targets would overwrite it with its own first
        # part — drop it here so the saved config matches the promise above.
        fs["target_fields"] = ", ".join(
            f for f in _csv(self._targets.text()) if f != source
        )
        fs["overwrite"] = self._overwrite.isChecked()
