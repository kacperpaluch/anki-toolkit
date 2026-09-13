from aqt import mw
from aqt.qt import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QVBoxLayout
)
from aqt.utils import tooltip

from .logic import SPLIT_HEAVIEST_FIRST, SPLIT_PROPORTIONAL

_STRATEGIES = (
    (SPLIT_PROPORTIONAL, "Proporcjonalnie — zachowaj wzajemne proporcje talii"),
    (SPLIT_HEAVIEST_FIRST, "Najpierw największa — małe talie zostaw w spokoju"),
)


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__(mw); self.setWindowTitle("Anki Toolkit: Workload — Ustawienia")
        from . import get_config
        config = get_config()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Sufit czasowy jest Twoją decyzją — resztę raport wylicza z niego.\n"
            "Zero w polach pomiarowych oznacza: policz z historii powtórek."
        ))
        form = QFormLayout()
        self.minutes = self._spin(5, 240, config["minutes_per_day"], " min")
        form.addRow("Czas na naukę dziennie:", self.minutes)
        self.seconds = self._spin(0, 120, config["seconds_per_card"], " s")
        form.addRow("Czas powtórki (0 = zmierz):", self.seconds)
        self.learn_seconds = self._spin(0, 120, config["learn_seconds_per_card"], " s")
        form.addRow("Czas odpowiedzi w nauce (0 = zmierz):", self.learn_seconds)
        self.learn_answers = QDoubleSpinBox()
        self.learn_answers.setRange(0.0, 10.0); self.learn_answers.setSingleStep(0.5)
        self.learn_answers.setDecimals(1); self.learn_answers.setSuffix("×")
        self.learn_answers.setValue(float(config["learn_answers_per_new_card"]))
        form.addRow("Odpowiedzi na nową kartę (0 = zmierz):", self.learn_answers)
        self.ratio = self._spin(0, 40, config["reviews_per_new_card"], "×")
        form.addRow("Powtórek na nową kartę (0 = zmierz):", self.ratio)
        self.days = self._spin(7, 365, config["forecast_days"], " dni")
        form.addRow("Okno prognozy:", self.days)
        self.strategy = QComboBox()
        for key, label in _STRATEGIES:
            self.strategy.addItem(label, key)
        current = self.strategy.findData(config.get("split_strategy", SPLIT_PROPORTIONAL))
        self.strategy.setCurrentIndex(max(0, current))
        form.addRow("Podział limitów:", self.strategy)
        self.decks = QLineEdit(", ".join(config.get("decks") or []))
        self.decks.setPlaceholderText("puste = wszystkie talie")
        form.addRow("Talie (po przecinku):", self.decks)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _spin(self, low, high, value, suffix):
        spin = QSpinBox(); spin.setRange(low, high); spin.setValue(int(value)); spin.setSuffix(suffix)
        return spin

    def save(self):
        from . import save_config
        decks = [part.strip() for part in self.decks.text().split(",") if part.strip()]
        save_config({
            "minutes_per_day": self.minutes.value(),
            "seconds_per_card": self.seconds.value(),
            "learn_seconds_per_card": self.learn_seconds.value(),
            "learn_answers_per_new_card": round(self.learn_answers.value(), 1),
            "reviews_per_new_card": self.ratio.value(),
            "forecast_days": self.days.value(),
            "split_strategy": self.strategy.currentData(),
            "decks": decks,
        })
        tooltip("Ustawienia Workload zapisane.", parent=mw); self.accept()


def open_settings():
    """Zwraca True, gdy ustawienia zapisano — raport trzeba wtedy przeliczyć."""
    return SettingsDialog().exec() == QDialog.DialogCode.Accepted
