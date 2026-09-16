from aqt.qt import QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLineEdit, QSpinBox, QWidget

from ..common.ui import collapsible_section, hint_label, scroll_panel, set_special_value
from .logic import SPLIT_HEAVIEST_FIRST, SPLIT_PROPORTIONAL

_STRATEGIES = (
    (SPLIT_PROPORTIONAL, "Proporcjonalnie — zachowaj wzajemne proporcje talii"),
    (SPLIT_HEAVIEST_FIRST, "Najpierw największa — małe talie zostaw w spokoju"),
)


_AUTO = "auto (z historii)"


def _spin(low, high, value, suffix, auto=False):
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(int(value))
    spin.setSuffix(suffix)
    if auto:
        set_special_value(spin, _AUTO)
    return spin


class WorkloadTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        from . import DEFAULTS
        config = {**DEFAULTS, **(cfg.get("workload") or {})}
        layout = scroll_panel(self)
        group = QGroupBox("Podstawowe")
        form = QFormLayout(group)
        form.addRow(hint_label(
            "Zwykły czas to punkt odniesienia; czas na dziś zmienisz w oknie planu.",
            small=True))
        self._minutes = _spin(5, 240, config["minutes_per_day"], " min")
        form.addRow("Zwykle celuję w:", self._minutes)
        self._max_minutes = _spin(self._minutes.value(), 240, config["max_minutes_per_day"], " min")
        self._minutes.valueChanged.connect(self._max_minutes.setMinimum)
        form.addRow("Najwyżej w zwykły dzień:", self._max_minutes)
        self._pace = _spin(0, 100, config["new_cards_per_day"], "")
        form.addRow("Spokojne tempo nowych/dzień (łącznie):", self._pace)
        self._decks = QLineEdit(", ".join(config.get("decks") or []))
        self._decks.setPlaceholderText("puste = wszystkie talie")
        form.addRow("Talie (po przecinku):", self._decks)
        layout.addWidget(group)

        advanced, advanced_layout = collapsible_section("Zaawansowane (pomiary i prognoza)")
        form = QFormLayout()
        advanced_layout.addLayout(form)
        form.addRow(hint_label(
            "„auto” liczy wartość z historii powtórek — zmieniaj tylko, gdy wynik "
            "wyraźnie odbiega od rzeczywistości.", small=True))
        self._seconds = _spin(0, 120, config["seconds_per_card"], " s", auto=True)
        form.addRow("Czas powtórki:", self._seconds)
        self._learn_seconds = _spin(0, 120, config["learn_seconds_per_card"], " s", auto=True)
        form.addRow("Czas odpowiedzi w nauce:", self._learn_seconds)
        self._learn_answers = QDoubleSpinBox()
        self._learn_answers.setRange(0.0, 10.0)
        self._learn_answers.setSingleStep(0.5)
        self._learn_answers.setDecimals(1)
        self._learn_answers.setSuffix("×")
        set_special_value(self._learn_answers, _AUTO)
        self._learn_answers.setValue(float(config["learn_answers_per_new_card"]))
        form.addRow("Odpowiedzi na nową kartę:", self._learn_answers)
        self._ratio = _spin(0, 40, config["reviews_per_new_card"], "×", auto=True)
        form.addRow("Powtórek na nową kartę:", self._ratio)
        self._days = _spin(7, 365, config["forecast_days"], " dni")
        form.addRow("Okno prognozy:", self._days)
        self._strategy = QComboBox()
        for key, label in _STRATEGIES:
            self._strategy.addItem(label, key)
        self._strategy.setCurrentIndex(max(0, self._strategy.findData(config["split_strategy"])))
        form.addRow("Podział limitów:", self._strategy)
        layout.addWidget(advanced)
        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("workload", {}).update({
            "minutes_per_day": self._minutes.value(),
            "max_minutes_per_day": self._max_minutes.value(),
            "new_cards_per_day": self._pace.value(),
            "seconds_per_card": self._seconds.value(),
            "learn_seconds_per_card": self._learn_seconds.value(),
            "learn_answers_per_new_card": round(self._learn_answers.value(), 1),
            "reviews_per_new_card": self._ratio.value(),
            "forecast_days": self._days.value(),
            "split_strategy": self._strategy.currentData(),
            "decks": [part.strip() for part in self._decks.text().split(",") if part.strip()],
        })
