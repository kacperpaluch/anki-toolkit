"""Field-splitting settings panel."""

from aqt.qt import (
    QWidget, QFormLayout, QGroupBox, QCheckBox,
)

from ..common.ui import _expanding_line_edit, hint_label, scroll_panel


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
        source = self._source.text().strip()
        fs["source_field"] = source
        fs["separator"] = self._separator.text().strip()
        # The source among the targets would overwrite it with its own first
        # part — drop it here so the saved config matches the promise above.
        fs["target_fields"] = ", ".join(
            f for f in _csv(self._targets.text()) if f != source
        )
        fs["overwrite"] = self._overwrite.isChecked()
