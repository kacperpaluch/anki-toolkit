"""Modules tab — enable/disable individual modules."""

from aqt.qt import QWidget, QVBoxLayout, QCheckBox

from ..common.ui import hint_label


class ModulesTab(QWidget):
    _LABELS = {
        "dictionary":        "Słownik — pobieranie audio i IPA",
        "ai_generator":      "AI Generator — wypełnianie pól przez AI",
        "tts":               "TTS — generowanie audio (Kokoro / OpenRouter)",
        "filtered_deck":     "Talia filtrowana",
        "audio_normalizer":  "Normalizacja audio — wyrównywanie głośności (ffmpeg)",
        "nbsp_remover":      "Czyszczenie HTML — &nbsp; i tagi <div>",
        "field_splitter":    "Rozdzielanie pól — kopiowanie do p1, p2, p3...",
        "audio_embed":       "Osadzanie audio — [sound:...] → <audio> w wybranych polach",
        "homograph_manager": "Homograph Manager — rozdziela osobne notatki z tym samym słowem",
        "field_hider":       "Ukrywanie pól — chowa pola w oknie „Dodaj”",
        "web_bridge":        "Słowniki → Anki — mostek HTTP do okna „Dodaj” (diki/Oxford/Longman, port 8766)",
        "word_queue":        "Kolejka słówek — po dodaniu karty odhacza słówko w n8n DataTable",
    }

    def __init__(self, cfg: dict):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(hint_label(
            "Zaznaczone moduły są ładowane przy starcie Anki.\n"
            "Zmiana wymaga restartu Anki."
        ))
        layout.addSpacing(8)

        self._checks: dict[str, QCheckBox] = {}
        modules_cfg = cfg.get("modules", {})

        for key, label in self._LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(modules_cfg.get(key, True))
            self._checks[key] = cb
            layout.addWidget(cb)

        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("modules", {})
        for key, cb in self._checks.items():
            cfg["modules"][key] = cb.isChecked()
