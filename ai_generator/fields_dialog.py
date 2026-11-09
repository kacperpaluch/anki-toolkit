"""One dialog for every Browser AI action: which fields, overwrite or not."""

from aqt.qt import (
    QCheckBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, Qt,
    QVBoxLayout,
)

from ..common.ui import hint_label, show_check_indicators


class FieldsDialog(QDialog):
    """auto/manual: field names for the selection."""

    def __init__(self, parent, note_count: int, auto: list, manual: list):
        super().__init__(parent)
        self.setWindowTitle("Wygeneruj pola AI")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(hint_label(f"Zaznaczone notatki: {note_count}. Wybierz pola do wygenerowania:"))

        self._list = QListWidget()
        show_check_indicators(self._list)
        for name in list(dict.fromkeys(auto + manual)):
            on_demand = name in manual and name not in auto
            item = QListWidgetItem(f"{name} — tylko na żądanie" if on_demand else name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if on_demand else Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._sync)
        layout.addWidget(self._list)

        self._overwrite = QCheckBox("Nadpisz pola, które mają już treść")
        layout.addWidget(self._overwrite)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generuj")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._sync()

    def _sync(self, *_):
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.fields()))

    def fields(self) -> list:
        return [item.data(Qt.ItemDataRole.UserRole)
                for item in (self._list.item(r) for r in range(self._list.count()))
                if item.checkState() == Qt.CheckState.Checked]

    def choice(self) -> tuple:
        """(fields, overwrite)"""
        return self.fields(), self._overwrite.isChecked()
