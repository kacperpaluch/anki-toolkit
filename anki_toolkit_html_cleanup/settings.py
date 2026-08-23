"""Native configuration dialog for Anki Toolkit: HTML Cleanup."""

from aqt import mw
from aqt.qt import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout
from aqt.utils import tooltip


class HtmlCleanupSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Anki Toolkit: HTML Cleanup — Ustawienia")
        self.resize(510, 300)
        from . import get_config
        config = get_config()

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Czyści &nbsp; oraz tagi <div> w dodawanych notatkach i na żądanie "
            "w całej kolekcji."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self._skip_field = QLineEdit(config.get("skip_field", "ang"))
        self._show_tooltip = QCheckBox("Pokazuj podsumowanie po czyszczeniu")
        self._show_tooltip.setChecked(config.get("show_tooltip", True))
        self._auto_startup = QCheckBox("Czyść całą kolekcję przy otwarciu profilu")
        self._auto_startup.setChecked(config.get("auto_run_startup", False))
        form.addRow("Pole bez podziału linii:", self._skip_field)
        form.addRow("", self._show_tooltip)
        form.addRow("", self._auto_startup)
        layout.addLayout(form)
        note = QLabel(
            "W podanym polu tagi <div> są usuwane. W pozostałych polach bloki "
            "<div> są zamieniane na <br>, aby zachować podział linii."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        from . import save_config
        save_config({
            "skip_field": self._skip_field.text().strip(),
            "show_tooltip": self._show_tooltip.isChecked(),
            "auto_run_startup": self._auto_startup.isChecked(),
        })
        tooltip("Ustawienia HTML Cleanup zapisane.", parent=mw)
        self.accept()


def open_settings() -> None:
    HtmlCleanupSettingsDialog().exec()
