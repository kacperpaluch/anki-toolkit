from aqt import mw
from aqt.qt import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout
from aqt.utils import tooltip

class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__(mw); self.setWindowTitle("Anki Toolkit: Learning — Ustawienia")
        from . import get_config
        layout=QVBoxLayout(self); layout.addWidget(QLabel("Nazwa bazowa talii filtrowanej. Każdy preset otrzyma własny sufiks.")); form=QFormLayout(); self.name=QLineEdit(get_config()["deck_name"]); form.addRow("Nazwa bazowa talii:", self.name); layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def save(self):
        from . import save_config
        save_config({"deck_name":self.name.text().strip() or "Powtórka z wyprzedzeniem"}); tooltip("Ustawienia Learning zapisane.", parent=mw); self.accept()
def open_settings(): SettingsDialog().exec()
