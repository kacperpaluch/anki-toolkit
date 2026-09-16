"""Workload — raport obciążenia nauką i spójności limitów.

Dodatek tylko czyta kolekcję: zbiera migawkę (limity presetów, zapas nowych
kart, interwały, terminy powtórek, historię revlog), przekazuje ją do
`logic.analyze` i pokazuje raport. Nie zapisuje nic do kolekcji ani do opcji
talii.
"""

from aqt import mw
from aqt.qt import (
    QApplication, QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout, QSpinBox, QFormLayout
)
from aqt.utils import tooltip

from ..common import get_module_config
from . import logic
from .snapshot import build_snapshot

DEFAULTS = {
    "minutes_per_day": 15,
    "max_minutes_per_day": 30,
    "new_cards_per_day": 3,
    "seconds_per_card": 0,
    "learn_seconds_per_card": 0,
    "learn_answers_per_new_card": 0,
    "reviews_per_new_card": 0,
    "forecast_days": 60,
    "split_strategy": logic.SPLIT_PROPORTIONAL,
    "decks": [],
}

def get_config(): return get_module_config("workload", DEFAULTS)


# ── Okno raportu ───────────────────────────────────────────────────────────

class ReportDialog(QDialog):
    def __init__(self):
        super().__init__(mw)
        self.setWindowTitle("Anki Toolkit: Plan nauki")
        self.resize(760, 680)
        self.settings = get_config()
        self.snapshot = build_snapshot(mw.col, self.settings)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.minutes = QSpinBox()
        self.minutes.setRange(0, max(self.settings["minutes_per_day"], self.settings["max_minutes_per_day"]))
        self.minutes.setSuffix(" min")
        self.minutes.setValue(self.settings["minutes_per_day"])
        form.addRow("Dziś mam łącznie (tylko w tym oknie):", self.minutes)
        layout.addLayout(form)
        self.view = QTextBrowser()
        layout.addWidget(self.view)
        self.details = QPushButton("Pokaż szczegóły raportu")
        self.details.setCheckable(True)
        self.details.toggled.connect(self.render)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for title, callback in (("Odśwież", self.refresh), ("Kopiuj raport", self.copy_report),
                                ("Ustawienia…", self.open_settings)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addButton(button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.minutes.valueChanged.connect(self.render)
        self.render()

    def render(self, *_):
        self.report = logic.analyze(self.snapshot, self.settings, self.minutes.value())
        html = logic.render_plan_html(self.report)
        if self.details.isChecked():
            html += logic.render_html(self.report)
        self.details.setText("Ukryj szczegóły raportu" if self.details.isChecked() else "Pokaż szczegóły raportu")
        self.view.setHtml(html)

    def refresh(self):
        if mw.col is None:
            self.reject()
            return
        self.snapshot = build_snapshot(mw.col, self.settings)
        self.render()

    def copy_report(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            tooltip("Schowek jest niedostępny.", parent=mw)
            return
        clipboard.setText(logic.render_text(self.report))
        tooltip("Raport skopiowany.", parent=mw)

    def open_settings(self):
        from ..settings_dialog import open_settings
        if open_settings("workload"):
            self.settings = get_config()
            self.minutes.blockSignals(True)
            self.minutes.setMaximum(max(self.settings["minutes_per_day"], self.settings["max_minutes_per_day"]))
            self.minutes.setValue(self.settings["minutes_per_day"])
            self.minutes.blockSignals(False)
            self.refresh()


def show_report():
    if mw.col is None:
        tooltip("Najpierw otwórz profil.", parent=mw)
        return
    ReportDialog().exec()
