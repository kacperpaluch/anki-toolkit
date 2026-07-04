"""Start tab — pipeline-centric dashboard for the unified settings dialog.

Layout (top to bottom):
  1. Header — workflow name + one global status pill,
  2. Pipeline — clickable chips, one per workflow step, joined by arrows,
  3. "Do zrobienia" — the only place issues are listed (no duplication),
  4. "Pozostałe moduły" — compact one-line status of utility modules.

The tab is rebuilt by refresh(cfg) every time it becomes visible, so it
reflects unsaved changes made in the other tabs of the dialog.
"""

from collections import Counter
from typing import Callable, Optional

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QFrame, QProgressBar, QPushButton, Qt,
)

from ..common import plural_pl
from ..common.ui import _scrollable, palette as _palette, FlowLayout


def _has_real_key(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and not value.startswith("YOUR_")


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

_UTILITY_MODULES = (
    ("audio_normalizer", "Normalizacja audio", "Normalizacja"),
    ("nbsp_remover", "Czyszczenie HTML", "Narzędzia"),
    ("filtered_deck", "Talia filtrowana", "Narzędzia"),
)


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


def _valid_tts_tasks(tts_cfg: dict) -> list[dict]:
    return [
        task for task in tts_cfg.get("tasks", [])
        if (
            isinstance(task, dict)
            and task.get("source_field", "").strip()
            and task.get("target_field", "").strip()
        )
    ]


def _tts_key_ok(cfg: dict) -> bool:
    tts = cfg.get("tts", {})
    if tts.get("tts_provider", "kokoro") != "openrouter":
        return True
    if tts.get("use_ai_openrouter_key", False):
        openrouter_cfg = (
            cfg.get("ai_generator", {}).get("providers", {}).get("openrouter", {})
        )
        return _has_real_key(openrouter_cfg.get("api_key", ""))
    return _has_real_key(tts.get("openrouter_api_key", ""))


def _workflow_uses(steps: list[dict], module: str) -> bool:
    return any(step.get("module") == module for step in steps if isinstance(step, dict))


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            # setParent(None) removes it from view *now*; deleteLater() is async,
            # so without this the old widgets float as ghosts over a re-render.
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
            item.layout().deleteLater()


class _ChipFrame(QFrame):
    """Clickable pipeline-step chip."""

    def __init__(self, on_click: Optional[Callable[[], None]] = None):
        super().__init__()
        self._on_click = on_click
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if self._on_click is not None:
            self._on_click()
        super().mousePressEvent(event)


class StatusTab(QWidget):
    def __init__(self, cfg: dict, open_tab: Optional[Callable[[str], None]] = None):
        super().__init__()
        self._open_tab = open_tab
        self._pal = _palette()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(14, 14, 14, 14)
        self._layout.setSpacing(12)
        outer.addWidget(_scrollable(self._content))

        self.refresh(cfg)

    def apply(self, cfg: dict) -> None:
        return

    def set_tab_opener(self, open_tab: Callable[[str], None]) -> None:
        self._open_tab = open_tab

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self, cfg: dict) -> None:
        """Rebuild the dashboard from the given (possibly unsaved) config."""
        self._pal = _palette()
        self._last_cfg = cfg  # for the batch-progress "Odśwież" button
        _clear_layout(self._layout)

        # Dashboard shows one representative workflow as a module-readiness check.
        # Prefer the one with an editor button; otherwise the first. Every
        # workflow is always available from the browser right-click menu, so the
        # dashboard never treats a workflow as "disabled" — editor_button is just
        # an optional extra surface, not an on/off switch.
        workflows = cfg.get("workflows")
        if isinstance(workflows, list) and workflows:
            primary = next(
                (w for w in workflows if isinstance(w, dict) and w.get("editor_button")),
                None,
            ) or next((w for w in workflows if isinstance(w, dict)), {})
            workflow = {
                "editor_label": primary.get("name", "Generuj fiszkę"),
                "steps": primary.get("steps", []),
            }
        else:
            workflow = cfg.get("workflow", {})
        steps = [s for s in workflow.get("steps", []) if isinstance(s, dict)]
        statuses = [self._step_status(cfg, step) for step in steps]
        issues = self._issues(cfg, steps, statuses)

        self._add_header(cfg, workflow, steps, issues)
        self._add_quick_actions()
        self._add_batch_progress()
        self._add_pipeline(cfg, steps, statuses)
        self._add_issues(cfg, issues)
        self._add_utility_row(cfg)
        self._layout.addStretch()

    def _step_status(self, cfg: dict, step: dict) -> dict:
        """Compute {title, lines, level, target} for one workflow step."""
        module = step.get("module", "")

        if module == "ai":
            ai = cfg.get("ai_generator", {})
            providers = _ready_ai_providers(ai)
            prompt_count, note_type_count = _valid_prompt_count(ai)
            if not _module_enabled(cfg, "ai_generator"):
                return {"title": "AI", "level": "off",
                        "lines": ["moduł wyłączony"], "target": "Moduły"}
            lines = []
            if providers:
                lines.append(", ".join(providers))
            if prompt_count:
                lines.append(
                    f"{prompt_count} {plural_pl(prompt_count, 'prompt', 'prompty', 'promptów')}"
                    f" · {note_type_count} {plural_pl(note_type_count, 'typ notatki', 'typy notatek', 'typów notatek')}"
                )
            ok = bool(providers) and prompt_count > 0
            if not providers:
                lines.append("brak dostawcy z kluczem")
            if not prompt_count:
                lines.append("brak promptów")
            return {"title": "AI", "level": "ok" if ok else "warn",
                    "lines": lines, "target": "AI Generator"}

        if module == "dictionary":
            if not _module_enabled(cfg, "dictionary"):
                return {"title": "Słownik", "level": "off",
                        "lines": ["moduł wyłączony"], "target": "Moduły"}
            dicts = step.get("dicts", [])
            labels = [_DICT_LABELS.get(d, d) for d in dicts]
            if labels:
                return {"title": "Słownik", "level": "ok",
                        "lines": [", ".join(labels)], "target": "Słownik"}
            return {"title": "Słownik", "level": "warn",
                    "lines": ["brak wybranych słowników"], "target": "AI Generator"}

        if module == "tts":
            if not _module_enabled(cfg, "tts"):
                return {"title": "TTS", "level": "off",
                        "lines": ["moduł wyłączony"], "target": "Moduły"}
            tts = cfg.get("tts", {})
            provider = tts.get("tts_provider", "kokoro")
            voices = [v for v in tts.get("voices", []) if str(v).strip()]
            tasks = _valid_tts_tasks(tts)
            key_ok = _tts_key_ok(cfg)
            lines = [
                "Kokoro (lokalny)" if provider == "kokoro" else "OpenRouter",
                f"{len(voices)} {plural_pl(len(voices), 'głos', 'głosy', 'głosów')}"
                f" · {len(tasks)} {plural_pl(len(tasks), 'zadanie', 'zadania', 'zadań')}",
            ]
            problems = []
            if not voices:
                problems.append("brak głosów")
            if not tasks:
                problems.append("brak zadań")
            if not key_ok:
                problems.append("brak klucza API")
            ok = not problems
            if problems:
                lines = [lines[0], ", ".join(problems)]
            return {"title": "TTS", "level": "ok" if ok else "warn",
                    "lines": lines, "target": "TTS"}

        if module == "field_splitter":
            if not _module_enabled(cfg, "field_splitter"):
                return {"title": "Rozdziel pole", "level": "off",
                        "lines": ["moduł wyłączony"], "target": "Moduły"}
            fs = cfg.get("field_splitter", {})
            source = fs.get("source_field", "przyklad")
            targets = fs.get("target_fields", "")
            if targets:
                return {"title": "Rozdziel pole", "level": "ok",
                        "lines": [f"{source} → {targets}"], "target": "Narzędzia"}
            return {"title": "Rozdziel pole", "level": "warn",
                    "lines": ["brak pól docelowych"], "target": "Narzędzia"}

        return {"title": module or "Krok", "level": "warn",
                "lines": [step.get("action", "?")], "target": "AI Generator"}

    def _issues(self, cfg: dict, steps: list[dict], statuses: list[dict]) -> list[tuple[str, str]]:
        issues: list[tuple[str, str]] = []

        if not steps:
            issues.append((
                "Brak workflowów z krokami — dodaj workflow w zakładce Workflowy.",
                "Workflowy",
            ))

        if _workflow_uses(steps, "ai"):
            if not _module_enabled(cfg, "ai_generator"):
                issues.append((
                    "Workflow ma krok AI, ale moduł AI Generator jest wyłączony.",
                    "Moduły",
                ))
            else:
                ai = cfg.get("ai_generator", {})
                if not _ready_ai_providers(ai):
                    issues.append((
                        "Dodaj klucz API i model dla co najmniej jednego dostawcy AI.",
                        "AI Generator",
                    ))
                if _valid_prompt_count(ai)[0] == 0:
                    issues.append((
                        "Skonfiguruj co najmniej jeden prompt dla typu notatki.",
                        "AI Generator",
                    ))

        if _workflow_uses(steps, "dictionary"):
            if not _module_enabled(cfg, "dictionary"):
                issues.append((
                    "Workflow ma krok Słownik, ale moduł Słownik jest wyłączony.",
                    "Moduły",
                ))
            elif any(
                s.get("module") == "dictionary" and not s.get("dicts")
                for s in steps
            ):
                issues.append((
                    "Krok Słownik nie ma wybranych słowników.",
                    "Workflowy",
                ))

        if _workflow_uses(steps, "tts"):
            if not _module_enabled(cfg, "tts"):
                issues.append((
                    "Workflow ma krok TTS, ale moduł TTS jest wyłączony.",
                    "Moduły",
                ))

        # TTS problems matter also without the workflow (editor/browser button).
        if _module_enabled(cfg, "tts"):
            tts = cfg.get("tts", {})
            if not [v for v in tts.get("voices", []) if str(v).strip()]:
                issues.append(("Nie zaznaczono żadnego głosu TTS.", "TTS"))
            if not _valid_tts_tasks(tts):
                issues.append(("Brak skonfigurowanych zadań TTS.", "TTS"))
            if not _tts_key_ok(cfg):
                issues.append((
                    "TTS OpenRouter wymaga własnego klucza albo klucza z AI Generatora.",
                    "TTS",
                ))

        # Deduplicate, keep order.
        seen = set()
        unique_issues = []
        for issue in issues:
            if issue not in seen:
                seen.add(issue)
                unique_issues.append(issue)
        return unique_issues

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _add_batch_progress(self) -> None:
        """Batch API — live progress of pending batches and backfill jobs.

        Data comes from user_files/ai_batches.json (not the config), so the
        section shows only when something is actually running. The whole tab
        is rebuilt on every visit, so re-entering Start also refreshes this."""
        try:
            from ..ai_generator import batch_backfill
            jobs = batch_backfill.active_jobs()
            pending = batch_backfill.pending_batches()
        except Exception:
            return
        if not jobs and not pending:
            return

        pal = self._pal
        group = QGroupBox("Batch API — postęp")
        box = QVBoxLayout(group)
        box.setSpacing(6)

        if pending:
            per = Counter(b.get("provider", "?") for b in pending)
            detail = ", ".join(f"{p}: {c}" for p, c in sorted(per.items()))
            reqs = sum(int(b.get("count") or 0) for b in pending)
            text = (f"Batche w toku: {len(pending)} ({detail}) — "
                    f"{reqs} zapytań czeka na wyniki.")
        else:
            text = ("Brak batchy w toku — kolejny plaster zadania zostanie "
                    "wysłany przy najbliższym sprawdzeniu (co minutę).")
        line = QLabel(text)
        line.setWordWrap(True)
        box.addWidget(line)

        for job in jobs:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Zadanie z {job.get('created_at', '?')}:"))
            total = int(job.get("total") or 0)
            if total:
                sent = min(int(job.get("sent") or 0), total)
                bar = QProgressBar()
                bar.setRange(0, total)
                bar.setValue(sent)
                bar.setFormat(
                    f"{sent:,} / {total:,} zapytań wysłanych (%p%)".replace(",", " ")
                )
                row.addWidget(bar, 1)
            else:
                legacy = QLabel("w toku (starsze zadanie bez licznika)")
                legacy.setStyleSheet(f"color: {pal['muted']};")
                row.addWidget(legacy, 1)
            box.addLayout(row)

        buttons = QHBoxLayout()
        check_btn = QPushButton("Sprawdź batche teraz")
        check_btn.setToolTip("Pobierz wyniki gotowych batchy i doślij kolejny plaster.")
        check_btn.clicked.connect(self._check_batches_now)
        refresh_btn = QPushButton("Odśwież")
        refresh_btn.clicked.connect(lambda: self.refresh(self._last_cfg))
        buttons.addWidget(check_btn)
        buttons.addWidget(refresh_btn)
        buttons.addStretch()
        box.addLayout(buttons)

        self._layout.addWidget(group)

    def _check_batches_now(self) -> None:
        # ponytail: poll+apply działa w tle — klik „Odśwież” po chwili pokaże
        # nowy stan; auto-refresh po zakończeniu wymagałby callbacka przez UI.
        from ..ai_generator.browser_ui import check_pending_batches
        check_pending_batches(silent=False)

    def _add_quick_actions(self) -> None:
        """Row of shortcut buttons to the tabs people configure most often."""
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel("Szybki dostęp:")
        label.setStyleSheet(f"color: {self._pal['muted']};")
        row.addWidget(label)
        for text, target in (
            ("✨ AI Generator", "AI Generator"),
            ("🔀 Workflowy", "Workflowy"),
            ("🔊 TTS", "TTS"),
            ("📖 Słownik", "Słownik"),
        ):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, t=target: self._go_to_tab(t))
            row.addWidget(btn)
        row.addStretch()
        wrapper = QWidget()
        wrapper.setLayout(row)
        self._layout.addWidget(wrapper)

    def _add_header(self, cfg: dict, workflow: dict, steps: list[dict],
                    issues: list) -> None:
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
        title = QLabel(workflow.get("editor_label", "Generuj fiszkę"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        subtitle = QLabel(
            "Przykładowy workflow — dostępny w menu PPM (prawy klik → Anki Toolkit). "
            "Kliknij krok, aby przejść do jego ustawień."
        )
        subtitle.setStyleSheet(f"color: {pal['muted']};")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)

        if issues:
            n = len(issues)
            pill_text = f"{n} {plural_pl(n, 'rzecz do zrobienia', 'rzeczy do zrobienia', 'rzeczy do zrobienia')}"
            bg, fg = pal["warn_bg"], pal["warn_fg"]
        else:
            pill_text, bg, fg = "Gotowe", pal["ok_bg"], pal["ok_fg"]

        pill = QLabel(pill_text)
        pill.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {fg}; "
            f"background: {bg}; border-radius: 6px; padding: 8px 14px;"
        )
        row.addWidget(pill)
        self._layout.addWidget(header)

    def _add_pipeline(self, cfg: dict, steps: list[dict], statuses: list[dict]) -> None:
        if not steps:
            return  # the issue row already explains what to do

        # FlowLayout wraps the step chips to the next row instead of overflowing
        # horizontally — workflows can have many steps. Order conveys the arrows.
        wrapper = QWidget()
        flow = FlowLayout(wrapper, spacing=6)
        for status in statuses:
            flow.addWidget(self._chip(status))
        self._layout.addWidget(wrapper)

    def _chip(self, status: dict) -> QFrame:
        pal = self._pal
        level = status["level"]
        icon, icon_color = {
            "ok": ("✓", pal["ok_fg"]),
            "warn": ("⚠", pal["warn_fg"]),
            "off": ("○", pal["off_fg"]),
        }.get(level, ("⚠", pal["warn_fg"]))
        border = {
            "ok": pal["border"],
            "warn": pal["issue_border"],
            "off": pal["border"],
        }[level]

        target = status.get("target")
        on_click = (lambda t=target: self._go_to_tab(t)) if target else None
        frame = _ChipFrame(on_click)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setFixedWidth(200)  # fixed width so FlowLayout wraps predictably
        frame.setStyleSheet(
            f"QFrame {{ background: {pal['card_bg']}; border: 1px solid {border}; border-radius: 6px; }}"
            "QLabel { border: none; }"
        )
        if target:
            frame.setToolTip(f"Otwórz zakładkę: {target}")

        box = QVBoxLayout(frame)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(3)

        head = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {icon_color}; font-size: 15px; font-weight: 700;")
        title = QLabel(status["title"])
        title.setStyleSheet("font-weight: 700;")
        head.addWidget(icon_label)
        head.addWidget(title)
        head.addStretch()
        box.addLayout(head)

        detail_color = pal["off_fg"] if level == "off" else pal["detail"]
        for line in status["lines"][:2]:
            label = QLabel(line)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {detail_color}; font-size: 11px;")
            box.addWidget(label)

        return frame

    def _add_issues(self, cfg: dict, issues: list) -> None:
        pal = self._pal
        group = QGroupBox("Do zrobienia")
        box = QVBoxLayout(group)
        box.setSpacing(6)

        if not issues:
            ready = QLabel(
                "Wszystko gotowe. Uruchom workflow z menu PPM w przeglądarce "
                "(prawy klik → Anki Toolkit) — albo przyciskiem w edytorze, jeśli "
                "włączysz go w zakładce Workflowy."
            )
            ready.setWordWrap(True)
            ready.setStyleSheet(f"color: {pal['ready_fg']};")
            box.addWidget(ready)
        else:
            for text, target in issues:
                box.addWidget(self._issue_row(text, target))

        self._layout.addWidget(group)

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
            button = QPushButton("Napraw")
            button.setMaximumWidth(90)
            button.clicked.connect(lambda _checked=False, t=target: self._go_to_tab(t))
            row.addWidget(button)

        return frame

    def _add_utility_row(self, cfg: dict) -> None:
        pal = self._pal
        group = QGroupBox("Pozostałe moduły")
        row = QHBoxLayout(group)
        row.setSpacing(14)

        for key, label, target in _UTILITY_MODULES:
            enabled = _module_enabled(cfg, key)
            icon = "✓" if enabled else "○"
            color = pal["ok_fg"] if enabled else pal["off_fg"]
            item = QLabel(f"{icon} {label}")
            item.setStyleSheet(f"color: {color};")
            item.setToolTip(
                f"Moduł włączony — ustawienia w zakładce {target}." if enabled
                else "Moduł wyłączony — włączysz go w zakładce Moduły."
            )
            row.addWidget(item)

        row.addStretch()
        modules_btn = QPushButton("Moduły…")
        modules_btn.setMaximumWidth(110)
        modules_btn.clicked.connect(lambda: self._go_to_tab("Moduły"))
        row.addWidget(modules_btn)

        self._layout.addWidget(group)

    def _go_to_tab(self, title: str) -> None:
        if self._open_tab is not None:
            self._open_tab(title)
