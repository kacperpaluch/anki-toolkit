"""Modules tab — enable/disable individual modules."""

from aqt.qt import QWidget, QVBoxLayout, QLabel, QCheckBox, QSizePolicy


class ModulesTab(QWidget):
    _LABELS = {
        "dictionary":        "Słownik — pobieranie audio i IPA",
        "ai_generator":      "AI Generator — wypełnianie pól przez AI",
        "tts":               "TTS — generowanie audio (Kokoro / OpenRouter)",
        "filtered_deck":     "Talia filtrowana",
        "audio_normalizer":  "Audio Normalizer — normalizacja audio (ffmpeg)",
        "nbsp_remover":      "nbsp Remover — czyszczenie &nbsp;",
    }

    def __init__(self, cfg: dict):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        note = QLabel(
            "Zaznaczone moduły są ładowane przy starcie Anki.\n"
            "Zmiana wymaga restartu Anki."
        )
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)
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
