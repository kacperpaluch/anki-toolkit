"""Start tab — dashboard for the unified settings dialog."""

from typing import Callable, Optional

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QGroupBox,
    QFrame, QPushButton, QSizePolicy, Qt,
)


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


_DICT_LABELS = {
    "oxford_uk": "Oxford UK",
    "oxford_us": "Oxford US",
    "cambridge_uk": "Cambridge UK",
    "cambridge_us": "Cambridge US",
    "diki_uk": "Diki UK",
    "diki_us": "Diki US",
    "longman_uk": "Longman UK",
    "longman_us": "Longman US",
}

def _palette() -> dict:
    """Theme-aware colors — hardcoded light values are unreadable in night mode."""
    try:
        from aqt.theme import theme_manager
        night = theme_manager.night_mode
    except Exception:
        night = False

    if night:
        return {
            "ok_bg": "#1e3327", "ok_fg": "#7fce9e",
            "warn_bg": "#3d3320", "warn_fg": "#e3b35c",
            "off_bg": "#2b2e33", "off_fg": "#9aa3ad",
            "frame_bg": "#2c2f33", "border": "#44484d",
            "muted": "#9aa3ad",
            "accent": "#7fb3e3", "accent_bg": "#2a3b4d",
            "card_bg": "#25282c", "detail": "#b6bec7",
            "issue_bg": "#3a3322", "issue_border": "#5c5230", "issue_fg": "#e0c98a",
            "ready_fg": "#7fce9e",
        }
    return {
        "ok_bg": "#eaf5ee", "ok_fg": "#1f7a3f",
        "warn_bg": "#fff4dc", "warn_fg": "#8a5a00",
        "off_bg": "#eef0f3", "off_fg": "#5c6570",
        "frame_bg": "#f7f8fa", "border": "#d9dde3",
        "muted": "#5c6570",
        "accent": "#1f4f7a", "accent_bg": "#eaf2fa",
        "card_bg": "white", "detail": "#4f5863",
        "issue_bg": "#fffaf0", "issue_border": "#ead8aa", "issue_fg": "#5c3d00",
        "ready_fg": "#1f7a3f",
    }


def _module_enabled(cfg: dict, key: str) -> bool:
    return cfg.get("modules", {}).get(key, True)


def _valid_prompt_count(ai_cfg: dict) -> tuple[int, int]:
    note_types = ai_cfg.get("note_types", {})
    note_type_count = 0
    task_count = 0
    for tasks in note_types.values():
        if not isinstance(tasks, dict):
            continue
        valid_for_type = 0
        for task in tasks.values():
            if not isinstance(task, dict):
                continue
            if task.get("target", "").strip() and task.get("prompt", "").strip():
                valid_for_type += 1
        if valid_for_type:
            note_type_count += 1
            task_count += valid_for_type
    return task_count, note_type_count


def _ready_ai_providers(ai_cfg: dict) -> list[str]:
    providers = ai_cfg.get("providers", {})
    return [
        name for name, provider_cfg in providers.items()
        if (
            isinstance(provider_cfg, dict)
            and _has_real_key(provider_cfg.get("api_key", ""))
            and provider_cfg.get("model", "").strip()
        )
    ]


def _enabled_dictionary_buttons(dictionary_cfg: dict) -> list[str]:
    return [
        button.get("label", "Słownik")
        for button in dictionary_cfg.get("buttons", [])
        if (
            isinstance(button, dict)
            and button.get("enabled")
            and button.get("dictionaries")
        )
    ]


def _valid_tts_tasks(tts_cfg: dict) -> list[dict]:
    return [
        task for task in tts_cfg.get("tasks", [])
        if (
            isinstance(task, dict)
            and task.get("source_field", "").strip()
            and task.get("target_field", "").strip()
        )
    ]


def _workflow_step_label(step: dict) -> str:
    module = step.get("module", "")
    action = step.get("action", "")
    if module == "ai" and action == "generate":
        return "AI"
    if module == "dictionary" and action == "fetch":
        dicts = step.get("dicts", [])
        labels = [_DICT_LABELS.get(item, item) for item in dicts]
        return "Słownik" + (": " + ", ".join(labels) if labels else "")
    if module == "tts" and action == "generate":
        return "TTS"
    return f"{module or 'Krok'} / {action or 'akcja'}"


def _workflow_pipeline(steps: list[dict]) -> str:
    if not steps:
        return "Brak kroków workflow"
    return " -> ".join(_workflow_step_label(step) for step in steps)


def _workflow_uses(steps: list[dict], module: str) -> bool:
    return any(step.get("module") == module for step in steps if isinstance(step, dict))


def _short_join(items: list[str], empty: str) -> str:
    return ", ".join(items) if items else empty


class StatusTab(QWidget):
    def __init__(self, cfg: dict, open_tab: Optional[Callable[[str], None]] = None):
        super().__init__()
        self._open_tab = open_tab
        self._pal = _palette()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        data = self._build_dashboard_data(cfg)
        self._add_header(layout, data)
        self._add_cards(layout, data)
        self._add_pipeline(layout, data)
        self._add_issues(layout, data)
        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        return

    def set_tab_opener(self, open_tab: Callable[[str], None]) -> None:
        self._open_tab = open_tab

    def _build_dashboard_data(self, cfg: dict) -> dict:
        modules = cfg.get("modules", {})
        enabled_count = sum(1 for key in _MODULE_KEYS if modules.get(key, True))

        workflow = cfg.get("workflow", {})
        steps = [step for step in workflow.get("steps", []) if isinstance(step, dict)]
        workflow_enabled = workflow.get("enabled", True)

        ai = cfg.get("ai_generator", {})
        ready_providers = _ready_ai_providers(ai)
        prompt_count, note_type_count = _valid_prompt_count(ai)

        dictionary = cfg.get("dictionary", {})
        dictionary_buttons = _enabled_dictionary_buttons(dictionary)

        tts = cfg.get("tts", {})
        voices = [voice for voice in tts.get("voices", []) if str(voice).strip()]
        tts_tasks = _valid_tts_tasks(tts)
        tts_provider = tts.get("tts_provider", "kokoro")
        openrouter_key_ok = True
        if tts_provider == "openrouter":
            if tts.get("use_ai_openrouter_key", False):
                openrouter_cfg = ai.get("providers", {}).get("openrouter", {})
                openrouter_key_ok = _has_real_key(openrouter_cfg.get("api_key", ""))
            else:
                openrouter_key_ok = _has_real_key(tts.get("openrouter_api_key", ""))

        statuses = {
            "workflow": {
                "title": "Workflow",
                "level": self._level(
                    _module_enabled(cfg, "ai_generator") and workflow_enabled and bool(steps),
                    _module_enabled(cfg, "ai_generator"),
                ),
                "detail": _status_text(
                    workflow_enabled and bool(steps),
                    f"{len(steps)} kroki: {_workflow_pipeline(steps)}",
                    "brak włączonego workflow lub kroków",
                ),
                "target": "AI Generator",
            },
            "ai": {
                "title": "AI",
                "level": self._level(bool(ready_providers), _module_enabled(cfg, "ai_generator")),
                "detail": _short_join(ready_providers, "brak dostawcy z realnym kluczem API i modelem"),
                "target": "AI Generator",
            },
            "prompts": {
                "title": "Prompty",
                "level": self._level(prompt_count > 0, _module_enabled(cfg, "ai_generator")),
                "detail": _status_text(
                    prompt_count > 0,
                    f"{prompt_count} zadań w {note_type_count} typach notatek",
                    "brak skonfigurowanych zadań generowania",
                ),
                "target": "AI Generator",
            },
            "dictionary": {
                "title": "Słownik",
                "level": self._level(bool(dictionary_buttons), _module_enabled(cfg, "dictionary")),
                "detail": _short_join(dictionary_buttons, "brak aktywnych źródeł"),
                "target": "Słownik",
            },
            "tts": {
                "title": "TTS",
                "level": self._level(
                    bool(voices) and bool(tts_tasks) and openrouter_key_ok,
                    _module_enabled(cfg, "tts"),
                ),
                "detail": self._tts_detail(tts_provider, voices, tts_tasks, openrouter_key_ok),
                "target": "TTS",
            },
            "maintenance": {
                "title": "Utrzymanie",
                "level": "ok" if (
                    _module_enabled(cfg, "audio_normalizer")
                    or _module_enabled(cfg, "nbsp_remover")
                    or _module_enabled(cfg, "filtered_deck")
                ) else "off",
                "detail": self._maintenance_detail(cfg),
                "target": "Narzędzia",
            },
        }

        critical_keys = ("workflow", "ai", "prompts", "dictionary", "tts")
        ready_count = sum(1 for key in critical_keys if statuses[key]["level"] == "ok")

        return {
            "enabled_count": enabled_count,
            "module_count": len(_MODULE_KEYS),
            "statuses": statuses,
            "critical_ready": ready_count,
            "critical_total": len(critical_keys),
            "pipeline": _workflow_pipeline(steps),
            "workflow_steps": steps,
            "issues": self._issues(cfg, statuses, steps, tts_provider, openrouter_key_ok),
        }

    def _level(self, ok: bool, enabled: bool = True) -> str:
        if not enabled:
            return "off"
        return "ok" if ok else "warn"

    def _tts_detail(
        self,
        provider: str,
        voices: list[str],
        tasks: list[dict],
        openrouter_key_ok: bool,
    ) -> str:
        parts = [provider]
        parts.append(f"głosy: {len(voices)}" if voices else "brak głosów")
        parts.append(f"zadania: {len(tasks)}" if tasks else "brak zadań")
        if provider == "openrouter" and not openrouter_key_ok:
            parts.append("brak klucza OpenRouter")
        if provider == "kokoro":
            parts.append("wymaga lokalnego serwera")
        return ", ".join(parts)

    def _maintenance_detail(self, cfg: dict) -> str:
        parts = []
        if _module_enabled(cfg, "audio_normalizer"):
            parts.append("normalizacja audio")
        if _module_enabled(cfg, "nbsp_remover"):
            parts.append("czyszczenie HTML")
        if _module_enabled(cfg, "filtered_deck"):
            parts.append("talia filtrowana")
        return ", ".join(parts) if parts else "moduły pomocnicze wyłączone"

    def _issues(
        self,
        cfg: dict,
        statuses: dict,
        steps: list[dict],
        tts_provider: str,
        openrouter_key_ok: bool,
    ) -> list[tuple[str, str]]:
        issues = []

        if not _module_enabled(cfg, "ai_generator"):
            issues.append(("AI Generator jest wyłączony, więc workflow i prompty nie będą działać.", "Moduły"))
        elif statuses["ai"]["level"] != "ok":
            issues.append(("Dodaj realny klucz API i model dla co najmniej jednego dostawcy AI.", "AI Generator"))

        if statuses["prompts"]["level"] != "ok" and _module_enabled(cfg, "ai_generator"):
            issues.append(("Skonfiguruj co najmniej jedno zadanie promptu dla typu notatki.", "AI Generator"))

        if statuses["workflow"]["level"] != "ok":
            issues.append(("Włącz workflow i ustaw kroki dla przycisku Generuj fiszkę.", "AI Generator"))

        if _workflow_uses(steps, "dictionary"):
            if not _module_enabled(cfg, "dictionary"):
                issues.append(("Workflow ma krok Słownik, ale moduł Słownik jest wyłączony.", "Moduły"))
            elif statuses["dictionary"]["level"] != "ok":
                issues.append(("Włącz co najmniej jedno źródło słownika dla pobierania wymowy.", "Słownik"))

        if _workflow_uses(steps, "tts"):
            if not _module_enabled(cfg, "tts"):
                issues.append(("Workflow ma krok TTS, ale moduł TTS jest wyłączony.", "Moduły"))
            elif statuses["tts"]["level"] != "ok":
                issues.append(("Uzupełnij głosy, zadania i dostawcę TTS.", "TTS"))

        if tts_provider == "openrouter" and not openrouter_key_ok:
            issues.append(("TTS OpenRouter wymaga własnego klucza albo współdzielonego klucza z AI Generatora.", "TTS"))

        return issues

    def _add_header(self, layout: QVBoxLayout, data: dict) -> None:
        pal = self._pal
        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header.setStyleSheet(
            f"QFrame {{ background: {pal['frame_bg']}; border: 1px solid {pal['border']}; border-radius: 6px; }}"
            "QLabel { border: none; }"
        )
        row = QHBoxLayout(header)
        row.setContentsMargins(12, 10, 12, 10)

        title_box = QVBoxLayout()
        title = QLabel("Start")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        subtitle = QLabel("Dashboard konfiguracji workflow i najważniejszych modułów.")
        subtitle.setStyleSheet(f"color: {pal['muted']};")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)

        score = QLabel(f"{data['critical_ready']}/{data['critical_total']}")
        score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {pal['accent']}; "
            f"background: {pal['accent_bg']}; border-radius: 6px; padding: 8px 14px;"
        )
        score.setToolTip("Gotowe elementy głównego pipeline'u: Workflow, AI, Prompty, Słownik, TTS")
        row.addWidget(score)

        modules = QLabel(f"Moduły: {data['enabled_count']}/{data['module_count']}")
        modules.setStyleSheet(f"color: {pal['muted']};")
        row.addWidget(modules)
        layout.addWidget(header)

    def _add_cards(self, layout: QVBoxLayout, data: dict) -> None:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        order = ("workflow", "ai", "prompts", "dictionary", "tts", "maintenance")
        for i, key in enumerate(order):
            card = self._card(data["statuses"][key])
            grid.addWidget(card, i // 3, i % 3)

        layout.addLayout(grid)

    def _card(self, status: dict) -> QFrame:
        pal = self._pal
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumHeight(104)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        frame.setStyleSheet(
            f"QFrame {{ background: {pal['card_bg']}; border: 1px solid {pal['border']}; border-radius: 6px; }}"
            "QLabel { border: none; }"
        )

        box = QVBoxLayout(frame)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(5)

        header = QHBoxLayout()
        title = QLabel(status["title"])
        title.setStyleSheet("font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        _badges = {
            "ok": ("OK", pal["ok_bg"], pal["ok_fg"]),
            "warn": ("Uwaga", pal["warn_bg"], pal["warn_fg"]),
            "off": ("Wyłączone", pal["off_bg"], pal["off_fg"]),
        }
        badge_text, bg, fg = _badges.get(status["level"], _badges["warn"])
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 4px; "
            "padding: 2px 6px; font-weight: 600;"
        )
        header.addWidget(badge)
        box.addLayout(header)

        detail = QLabel(status["detail"])
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {pal['detail']};")
        box.addWidget(detail, 1)

        if status.get("target"):
            button = QPushButton("Otwórz")
            button.setMaximumWidth(90)
            button.clicked.connect(lambda _checked=False, t=status["target"]: self._go_to_tab(t))
            box.addWidget(button)

        return frame

    def _add_pipeline(self, layout: QVBoxLayout, data: dict) -> None:
        group = QGroupBox("Pipeline przycisku Generuj fiszkę")
        box = QVBoxLayout(group)
        pipeline = QLabel(data["pipeline"])
        pipeline.setWordWrap(True)
        pipeline.setStyleSheet(f"font-weight: 600; color: {self._pal['accent']};")
        box.addWidget(pipeline)

        note = QLabel(
            "To jest kolejność kroków uruchamianych z toolbaru edytora. "
            "Zmiany wykonasz w AI Generator -> Workflow."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {self._pal['muted']};")
        box.addWidget(note)
        layout.addWidget(group)

    def _add_issues(self, layout: QVBoxLayout, data: dict) -> None:
        group = QGroupBox("Co wymaga uwagi")
        box = QVBoxLayout(group)
        box.setSpacing(6)

        issues = data["issues"]
        if not issues:
            ready = QLabel(
                "Konfiguracja wygląda gotowo dla głównego pipeline'u. "
                "Możesz sprawdzić działanie na jednej karcie przyciskiem Generuj fiszkę."
            )
            ready.setWordWrap(True)
            ready.setStyleSheet(f"color: {self._pal['ready_fg']};")
            box.addWidget(ready)
        else:
            for text, target in issues:
                box.addWidget(self._issue_row(text, target))

        layout.addWidget(group)

    def _issue_row(self, text: str, target: str) -> QFrame:
        pal = self._pal
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            f"QFrame {{ background: {pal['issue_bg']}; border: 1px solid {pal['issue_border']}; border-radius: 5px; }}"
            "QLabel { border: none; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 6, 8, 6)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {pal['issue_fg']};")
        row.addWidget(label, 1)

        if target:
            button = QPushButton("Otwórz")
            button.setMaximumWidth(90)
            button.clicked.connect(lambda _checked=False, t=target: self._go_to_tab(t))
            row.addWidget(button)

        return frame

    def _go_to_tab(self, title: str) -> None:
        if self._open_tab is not None:
            self._open_tab(title)
