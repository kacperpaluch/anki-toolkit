"""One dialog for every Browser AI action: which fields, overwrite or not, cheaper Batch API."""

from aqt.qt import (
    QCheckBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, Qt,
    QVBoxLayout,
)

from ..common.ui import hint_label


class FieldsDialog(QDialog):
    """auto/manual: field names for the selection; batch: those with a Batch API provider."""

    def __init__(self, parent, note_count: int, auto: list, manual: list, batch: list):
        super().__init__(parent)
        self.setWindowTitle("Wygeneruj pola AI")
        self.setMinimumWidth(380)
        self._batch_fields = set(batch)
        layout = QVBoxLayout(self)
        layout.addWidget(hint_label(f"Zaznaczone notatki: {note_count}. Wybierz pola do wygenerowania:"))

        self._list = QListWidget()
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
        self._batch = QCheckBox("Tryb tańszy (Batch API): ok. 50% taniej, wynik do 24 h")
        self._batch.setVisible(bool(self._batch_fields))
        for box in (self._overwrite, self._batch):
            box.toggled.connect(self._sync)
            layout.addWidget(box)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generuj")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._sync()

    def _sync(self, *_):
        # Batch API fills only empty fields, so it excludes overwriting.
        self._batch.setEnabled(not self._overwrite.isChecked())
        self._overwrite.setEnabled(not self._batch.isChecked())
        batch = self._batch.isChecked()
        self._list.blockSignals(True)
        for row in range(self._list.count()):
            item = self._list.item(row)
            usable = not batch or item.data(Qt.ItemDataRole.UserRole) in self._batch_fields
            flags = item.flags() | Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags if usable else flags & ~Qt.ItemFlag.ItemIsEnabled)
            item.setToolTip("" if usable else "Dostawca tego pola nie obsługuje trybu tańszego.")
        self._list.blockSignals(False)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.fields()))

    def fields(self) -> list:
        return [item.data(Qt.ItemDataRole.UserRole)
                for item in (self._list.item(r) for r in range(self._list.count()))
                if item.checkState() == Qt.CheckState.Checked
                and item.flags() & Qt.ItemFlag.ItemIsEnabled]

    def choice(self) -> tuple:
        """(fields, overwrite, batch)"""
        return self.fields(), self._overwrite.isChecked(), self._batch.isChecked()
