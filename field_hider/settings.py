"""Field Hider settings panel — hidden fields per note type."""

from aqt.qt import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..common.ui import (
    get_fields_for_note_type, get_note_type_names, hint_label, scroll_panel,
)


class FieldHiderTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._hidden = {
            note_type: list(fields)
            for note_type, fields in ((cfg.get("field_hider") or {}).get("hidden_fields") or {}).items()
        }
        self._current_type: str | None = None
        self._checks: dict[str, QCheckBox] = {}

        layout = scroll_panel(self)
        layout.addWidget(hint_label(
            "Zaznaczone pola są ukryte tylko w oknie „Dodaj” (przycisk 👁 pokazuje je "
            "tymczasowo). Pozostają widoczne w przeglądarce i podczas edycji istniejących notatek."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Typ notatki:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(get_note_type_names())
        self._type_combo.currentTextChanged.connect(self._change_note_type)
        row.addWidget(self._type_combo, 1)
        layout.addLayout(row)
        self._fields_layout = QVBoxLayout()
        layout.addLayout(self._fields_layout)
        layout.addStretch()

        if self._type_combo.count():
            self._change_note_type(self._type_combo.currentText())
        else:
            self._fields_layout.addWidget(QLabel("Brak dostępnych typów notatek."))

    def _store_current(self) -> None:
        if self._current_type is None:
            return
        fields = [name for name, checkbox in self._checks.items() if checkbox.isChecked()]
        if fields:
            self._hidden[self._current_type] = fields
        else:
            self._hidden.pop(self._current_type, None)

    def _change_note_type(self, note_type: str) -> None:
        self._store_current()
        self._current_type = note_type or None
        self._checks.clear()
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        hidden = set(self._hidden.get(note_type, []))
        for name in get_fields_for_note_type(note_type):
            checkbox = QCheckBox(name)
            checkbox.setChecked(name in hidden)
            self._checks[name] = checkbox
            self._fields_layout.addWidget(checkbox)

    def apply(self, cfg: dict) -> None:
        self._store_current()
        cfg.setdefault("field_hider", {})["hidden_fields"] = self._hidden
