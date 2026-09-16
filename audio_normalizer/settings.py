from aqt.qt import QCheckBox, QFormLayout, QGroupBox, QLineEdit, QSpinBox, QWidget

from ..common.ui import hint_label, scroll_panel
from .config import LOUDNORM_OPTS


class AudioNormalizerTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        from . import _DEFAULTS
        config = {**_DEFAULTS, **(cfg.get("audio_normalizer") or {})}
        layout = scroll_panel(self)
        group = QGroupBox("Ustawienia")
        form = QFormLayout(group)
        form.addRow(hint_label(
            "Wyrównuje głośność plików audio przez ffmpeg. Zmiana auto-normalizacji "
            "działa po restarcie Anki.", small=True))
        self._path = QLineEdit(config["ffmpeg_path"])
        self._opts = QLineEdit(config["loudnorm_opts"])
        self._workers = QSpinBox()
        self._workers.setRange(1, 32)
        self._workers.setValue(config["max_workers"])
        self._auto = QCheckBox("Automatycznie normalizuj nowe pliki audio")
        self._auto.setChecked(config["auto_normalize"])
        self._notice = QCheckBox("Pokazuj powiadomienie po auto-normalizacji")
        self._notice.setChecked(config["show_tooltip"])
        form.addRow("Ścieżka ffmpeg (puste = wykryj):", self._path)
        form.addRow("Filtr loudnorm:", self._opts)
        form.addRow("Równoległe procesy:", self._workers)
        form.addRow("", self._auto)
        form.addRow("", self._notice)
        layout.addWidget(group)
        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("audio_normalizer", {}).update({
            "ffmpeg_path": self._path.text().strip(),
            "loudnorm_opts": self._opts.text().strip() or LOUDNORM_OPTS,
            "max_workers": self._workers.value(),
            "auto_normalize": self._auto.isChecked(),
            "show_tooltip": self._notice.isChecked(),
        })
