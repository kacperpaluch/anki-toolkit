from aqt import mw
from aqt.qt import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout
from aqt.utils import tooltip


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__(mw); self.setWindowTitle("Anki Toolkit: Audio Normalizer — Ustawienia"); self.resize(560, 330)
        from . import get_config
        cfg = get_config(); layout = QVBoxLayout(self)
        label = QLabel("Wyrównuje głośność plików audio przez ffmpeg. Zmiana auto-normalizacji działa po restarcie Anki."); label.setWordWrap(True); layout.addWidget(label)
        form = QFormLayout(); self.path = QLineEdit(cfg["ffmpeg_path"]); self.opts = QLineEdit(cfg["loudnorm_opts"]); self.workers = QSpinBox(); self.workers.setRange(1, 32); self.workers.setValue(cfg["max_workers"])
        self.auto = QCheckBox("Automatycznie normalizuj nowe pliki audio"); self.auto.setChecked(cfg["auto_normalize"]); self.notice = QCheckBox("Pokazuj powiadomienie po auto-normalizacji"); self.notice.setChecked(cfg["show_tooltip"])
        form.addRow("Ścieżka ffmpeg (puste = wykryj):", self.path); form.addRow("Filtr loudnorm:", self.opts); form.addRow("Równoległe procesy:", self.workers); form.addRow("", self.auto); form.addRow("", self.notice); layout.addLayout(form); layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def save(self):
        from . import save_config
        save_config({"ffmpeg_path": self.path.text().strip(), "loudnorm_opts": self.opts.text().strip() or "loudnorm=I=-14:TP=-1.5:LRA=8", "max_workers": self.workers.value(), "auto_normalize": self.auto.isChecked(), "show_tooltip": self.notice.isChecked()}); tooltip("Ustawienia Audio Normalizer zapisane.", parent=mw); self.accept()

def open_settings(): SettingsDialog().exec()
