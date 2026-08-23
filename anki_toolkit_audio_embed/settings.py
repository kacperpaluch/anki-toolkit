"""Native configuration dialog for Anki Toolkit: Audio Embed."""

from aqt import mw
from aqt.qt import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QVBoxLayout,
)
from aqt.utils import tooltip


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class AudioEmbedSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Anki Toolkit: Audio Embed — Ustawienia")
        self.resize(560, 390)
        from . import get_config
        config = get_config()

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Zamienia znaczniki [sound:plik.mp3] na osadzone odtwarzacze HTML5 "
            "wyłącznie w wybranych polach. Główne pole audio zostaw poza listą."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self._note_types = QLineEdit(", ".join(config.get("note_types", [])))
        self._note_types.setPlaceholderText("puste = wszystkie typy notatek")
        self._fields = QLineEdit(", ".join(config.get("fields", [])))
        self._css_class = QLineEdit(config.get("css_class", "ex-audio"))
        self._preload = QComboBox()
        self._preload.addItems(["none", "metadata", "auto"])
        self._preload.setCurrentText(config.get("preload", "none"))
        self._scan_on_sync = QCheckBox("Skanuj kolekcję po synchronizacji")
        self._scan_on_sync.setChecked(config.get("scan_on_sync", True))
        form.addRow("Typy notatek:", self._note_types)
        form.addRow("Pola do konwersji:", self._fields)
        form.addRow("Klasa CSS:", self._css_class)
        form.addRow("Atrybut preload:", self._preload)
        form.addRow("", self._scan_on_sync)
        layout.addLayout(form)

        hint = QLabel(
            "Typy notatek i pola oddzielaj przecinkami. Operacja jest idempotentna: "
            "ponowny skan nie zmienia istniejących elementów <audio>."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
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
            "note_types": _csv(self._note_types.text()),
            "fields": _csv(self._fields.text()),
            "css_class": self._css_class.text().strip() or "ex-audio",
            "preload": self._preload.currentText(),
            "scan_on_sync": self._scan_on_sync.isChecked(),
        })
        tooltip("Ustawienia Audio Embed zapisane.", parent=mw)
        self.accept()


def open_settings() -> None:
    AudioEmbedSettingsDialog().exec()
