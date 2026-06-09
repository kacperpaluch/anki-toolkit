"""Status tab — compact setup summary for the unified settings dialog."""

from aqt.qt import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout


def _has_real_key(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and not value.startswith("YOUR_")


def _status_text(ok: bool, ready: str, missing: str) -> str:
    return ready if ok else missing


_MODULE_KEYS = (
    "dictionary",
    "ai_generator",
    "tts",
    "filtered_deck",
    "audio_normalizer",
    "nbsp_remover",
)


class StatusTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Najważniejsze elementy konfiguracji")
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        summary = QGroupBox("Status")
        form = QFormLayout(summary)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        modules = cfg.get("modules", {})
        enabled_count = sum(1 for key in _MODULE_KEYS if modules.get(key, True))
        form.addRow("Moduły:", QLabel(f"włączone: {enabled_count}"))

        workflow = cfg.get("workflow", {})
        steps = workflow.get("steps", [])
        form.addRow(
            "Workflow:",
            QLabel(_status_text(bool(steps), f"kroki: {len(steps)}", "brak skonfigurowanych kroków")),
        )

        ai = cfg.get("ai_generator", {})
        providers = ai.get("providers", {})
        ready_providers = [
            name for name, provider_cfg in providers.items()
            if _has_real_key(provider_cfg.get("api_key", "")) and provider_cfg.get("model", "").strip()
        ]
        form.addRow(
            "AI:",
            QLabel(_status_text(bool(ready_providers), ", ".join(ready_providers), "brak aktywnego providera")),
        )

        note_types = ai.get("note_types", {})
        task_count = sum(len(fields) for fields in note_types.values() if isinstance(fields, dict))
        form.addRow(
            "Prompty:",
            QLabel(_status_text(task_count > 0, f"zadania: {task_count}", "brak zadań generowania")),
        )

        dictionary = cfg.get("dictionary", {})
        enabled_buttons = [
            b.get("label", "Słownik")
            for b in dictionary.get("buttons", [])
            if b.get("enabled") and b.get("dictionaries")
        ]
        form.addRow(
            "Słownik:",
            QLabel(_status_text(bool(enabled_buttons), ", ".join(enabled_buttons), "brak aktywnych źródeł")),
        )

        tts = cfg.get("tts", {})
        voices = tts.get("voices", [])
        tasks = tts.get("tasks", [])
        tts_ready = bool(voices) and bool(tasks)
        form.addRow(
            "TTS:",
            QLabel(_status_text(tts_ready, f"{tts.get('tts_provider', 'kokoro')}, zadania: {len(tasks)}", "brak głosów lub zadań")),
        )

        layout.addWidget(summary)

        hint = QLabel(
            "Najczęściej wystarczy skonfigurować Workflow, jednego dostawcę AI, prompty oraz TTS. "
            "Limity, retry i timeouty są ustawieniami zaawansowanymi."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)
        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        return
