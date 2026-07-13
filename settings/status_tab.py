"""Compact operational start page for Anki Toolkit settings."""

from collections import Counter
from typing import Callable, Optional

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFrame,
    QProgressBar, QPushButton,
)

from ..common import plural_pl
from ..common.ui import _scrollable, palette as _palette


def _has_real_key(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and not value.startswith("YOUR_")


def _module_enabled(cfg: dict, key: str) -> bool:
    return cfg.get("modules", {}).get(key, True)


def _ready_ai_providers(cfg: dict) -> list[str]:
    providers = cfg.get("ai_generator", {}).get("providers", {})
    return [
        name for name, values in providers.items()
        if isinstance(values, dict)
        and _has_real_key(values.get("api_key", ""))
        and values.get("model", "").strip()
    ]


def _prompt_count(cfg: dict) -> int:
    note_types = cfg.get("ai_generator", {}).get("note_types", {})
    return sum(
        1
        for tasks in note_types.values() if isinstance(tasks, dict)
        for task in tasks.values() if isinstance(task, dict)
        and task.get("target", "").strip() and task.get("prompt", "").strip()
    )


def _tts_ready(cfg: dict) -> bool:
    tts = cfg.get("tts", {})
    if not tts.get("tasks") or not tts.get("voices"):
        return False
    if tts.get("tts_provider", "kokoro") != "openrouter":
        return True
    if tts.get("use_ai_openrouter_key", False):
        key = (
            cfg.get("ai_generator", {}).get("providers", {})
            .get("openrouter", {}).get("api_key", "")
        )
    else:
        key = tts.get("openrouter_api_key", "")
    return _has_real_key(key)


def _primary_workflow(cfg: dict) -> dict:
    workflows = [w for w in cfg.get("workflows", []) if isinstance(w, dict)]
    return next((w for w in workflows if w.get("editor_button")), None) or (
        workflows[0] if workflows else {}
    )


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            # Keep the reference before detaching. In Qt 6.11 setParent(None)
            # can make item.widget() return None immediately.
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


class StatusTab(QWidget):
    """Shows actions, live work and blockers for the primary workflow only."""

    def __init__(self, cfg: dict, open_tab: Optional[Callable[[str], None]] = None):
        super().__init__()
        self._open_tab = open_tab
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(14, 14, 14, 14)
        self._layout.setSpacing(12)
        outer.addWidget(_scrollable(content))
        self.refresh(cfg)

    def apply(self, cfg: dict) -> None:
        return

    def refresh(self, cfg: dict) -> None:
        self._cfg = cfg
        self._pal = _palette()
        _clear_layout(self._layout)
        workflow = _primary_workflow(cfg)
        issues = self._blocking_issues(cfg, workflow)
        self._add_header(workflow, issues)
        self._add_quick_actions()
        self._add_activity()
        self._add_issues(issues)
        self._layout.addStretch()

    def _blocking_issues(self, cfg: dict, workflow: dict) -> list[tuple[str, str]]:
        steps = [s for s in workflow.get("steps", []) if isinstance(s, dict)]
        modules = {s.get("module") for s in steps}
        issues: list[tuple[str, str]] = []
        if not steps:
            issues.append(("Utwórz przynajmniej jeden workflow z krokami.", "Workflowy"))
        if "ai" in modules:
            if not _module_enabled(cfg, "ai_generator"):
                issues.append(("Główny workflow wymaga wyłączonego modułu AI.", "Moduły"))
            elif not _ready_ai_providers(cfg):
                issues.append(("Skonfiguruj model i klucz co najmniej jednego dostawcy AI.", "Generowanie AI"))
            if _prompt_count(cfg) == 0:
                issues.append(("Główny workflow nie ma żadnego kompletnego promptu.", "Generowanie AI"))
        if "tts" in modules:
            if not _module_enabled(cfg, "tts"):
                issues.append(("Główny workflow wymaga wyłączonego modułu TTS.", "Moduły"))
            elif not _tts_ready(cfg):
                issues.append(("Uzupełnij zadania, głosy lub klucz używany przez TTS.", "Wymowa"))
        if "dictionary" in modules and not _module_enabled(cfg, "dictionary"):
            issues.append(("Główny workflow wymaga wyłączonego modułu Słownik.", "Moduły"))
        if "field_splitter" in modules and not _module_enabled(cfg, "field_splitter"):
            issues.append(("Główny workflow wymaga wyłączonego rozdzielania pól.", "Moduły"))
        return issues

    def _add_header(self, workflow: dict, issues: list[tuple[str, str]]) -> None:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            f"QFrame {{ background: {self._pal['frame_bg']}; border: 1px solid "
            f"{self._pal['border']}; border-radius: 6px; }} QLabel {{ border: none; }}"
        )
        row = QHBoxLayout(frame)
        title_box = QVBoxLayout()
        title = QLabel("Anki Toolkit")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        name = workflow.get("name") or "Brak głównego workflow"
        subtitle = QLabel(f"Główny proces: {name}")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {self._pal['muted']};")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)
        if issues:
            count = len(issues)
            label = f"{count} {plural_pl(count, 'problem', 'problemy', 'problemów')}"
            bg, fg = self._pal["warn_bg"], self._pal["warn_fg"]
        else:
            label, bg, fg = "Gotowe", self._pal["ok_bg"], self._pal["ok_fg"]
        pill = QLabel(label)
        pill.setStyleSheet(
            f"font-weight: 700; color: {fg}; background: {bg}; "
            "border-radius: 6px; padding: 8px 14px;"
        )
        row.addWidget(pill)
        self._layout.addWidget(frame)

    def _add_quick_actions(self) -> None:
        group = QGroupBox("Szybkie ustawienia")
        row = QHBoxLayout(group)
        for label, target in (
            ("Workflowy", "Workflowy"),
            ("Generowanie AI", "Generowanie AI"),
            ("Wymowa", "Wymowa"),
            ("Reguły kart", "Reguły kart"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, name=target: self._go(name))
            row.addWidget(button)
        row.addStretch()
        self._layout.addWidget(group)

    def _batch_state(self):
        try:
            from ..ai_generator import batch_backfill
            return batch_backfill.active_jobs(), batch_backfill.pending_batches()
        except Exception:
            return [], []

    def _add_activity(self) -> None:
        jobs, pending = self._batch_state()
        if not jobs and not pending:
            return
        group = QGroupBox("Aktywność")
        box = QVBoxLayout(group)
        if pending:
            per_provider = Counter(item.get("provider", "?") for item in pending)
            providers = ", ".join(
                f"{name}: {count}" for name, count in sorted(per_provider.items())
            )
            box.addWidget(QLabel(f"Batche AI w toku: {len(pending)} ({providers})"))
        for job in jobs:
            row = QHBoxLayout()
            total = int(job.get("total") or 0)
            sent = min(int(job.get("sent") or 0), total) if total else 0
            row.addWidget(QLabel("Backfill AI:"))
            if total:
                bar = QProgressBar()
                bar.setRange(0, total)
                bar.setValue(sent)
                bar.setFormat(f"{sent} / {total} (%p%)")
                row.addWidget(bar, 1)
            else:
                row.addWidget(QLabel("w toku"), 1)
            box.addLayout(row)
        actions = QHBoxLayout()
        check = QPushButton("Sprawdź batche")
        check.clicked.connect(self._check_batches)
        refresh = QPushButton("Odśwież")
        refresh.clicked.connect(lambda: self.refresh(self._cfg))
        actions.addWidget(check)
        actions.addWidget(refresh)
        actions.addStretch()
        box.addLayout(actions)
        self._layout.addWidget(group)

    def _add_issues(self, issues: list[tuple[str, str]]) -> None:
        group = QGroupBox("Wymaga uwagi")
        box = QVBoxLayout(group)
        if not issues:
            ready = QLabel(
                "Główny workflow jest gotowy. Uruchom go z menu Anki Toolkit "
                "w przeglądarce albo z przycisku edytora."
            )
            ready.setWordWrap(True)
            ready.setStyleSheet(f"color: {self._pal['ready_fg']};")
            box.addWidget(ready)
        for message, target in issues:
            row = QHBoxLayout()
            label = QLabel(f"⚠ {message}")
            label.setWordWrap(True)
            row.addWidget(label, 1)
            button = QPushButton("Napraw")
            button.clicked.connect(lambda _checked=False, name=target: self._go(name))
            row.addWidget(button)
            box.addLayout(row)
        self._layout.addWidget(group)

    def _check_batches(self) -> None:
        from ..ai_generator.browser_ui import check_pending_batches
        check_pending_batches(silent=False)

    def _go(self, title: str) -> None:
        if self._open_tab is not None:
            self._open_tab(title)
