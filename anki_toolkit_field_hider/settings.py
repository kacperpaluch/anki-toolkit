"""Native Anki configuration dialog for the standalone Field Hider add-on."""

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import tooltip


def _note_type_names() -> list[str]:
    try:
        return sorted(model["name"] for model in mw.col.models.all())
    except Exception:
        return []


def _field_names(note_type_name: str) -> list[str]:
    try:
        model = mw.col.models.by_name(note_type_name)
    except Exception:
        return []
    return [field["name"] for field in model["flds"]] if model else []


class FieldHiderSettingsDialog(QDialog):
    """Edit hidden fields per note type without exposing JSON to the user."""

    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Anki Toolkit: Field Hider — Ustawienia")
        self.resize(500, 460)
        self._hidden = {
            note_type: list(fields)
            for note_type, fields in (self._load_config().get("hidden_fields") or {}).items()
        }
        self._current_type: str | None = None
        self._checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Zaznaczone pola są ukryte tylko w oknie „Dodaj”. Pozostają widoczne "
            "w przeglądarce i podczas edycji istniejących notatek."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel("Typ notatki:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(_note_type_names())
        self._type_combo.currentTextChanged.connect(self._change_note_type)
        row.addWidget(self._type_combo, 1)
        layout.addLayout(row)

        self._fields_widget = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_widget)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidget(self._fields_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if self._type_combo.count():
            self._change_note_type(self._type_combo.currentText())
        else:
            self._fields_layout.addWidget(QLabel("Brak dostępnych typów notatek."))

    @staticmethod
    def _load_config() -> dict:
        from . import get_config
        return get_config()

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
        for name in _field_names(note_type):
            checkbox = QCheckBox(name)
            checkbox.setChecked(name in hidden)
            self._checks[name] = checkbox
            self._fields_layout.addWidget(checkbox)
        self._fields_layout.addStretch()

    def _save(self) -> None:
        self._store_current()
        from . import save_config
        save_config({"hidden_fields": self._hidden})
        tooltip("Ustawienia Field Hider zapisane.", parent=mw)
        self.accept()


def open_settings() -> None:
    FieldHiderSettingsDialog().exec()
