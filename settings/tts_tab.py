"""TTS tab — provider selection, Kokoro/OpenRouter settings, voices, tasks, performance."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QStackedWidget, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QDialog, QDialogButtonBox,
    Qt, QLineEdit, QCheckBox,
)
from aqt.utils import showWarning

from ..common.ui import _expanding_line_edit, _api_key_widget, _scrollable

_PROVIDERS = {"kokoro": "Kokoro (lokalny Docker)", "openrouter": "OpenRouter (API)"}


# ---------------------------------------------------------------------------
# Task editor dialog
# ---------------------------------------------------------------------------

class TaskEditDialog(QDialog):
    def __init__(self, parent=None, task: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edytuj zadanie" if task else "Dodaj zadanie")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._label = QLineEdit(task.get("label", "") if task else "")
        self._source = QLineEdit(task.get("source_field", "") if task else "")
        self._target = QLineEdit(task.get("target_field", "") if task else "")
        self._mode = QComboBox()
        self._mode.addItem("Pojedyncze audio", "single")
        self._mode.addItem("Dzielone (split)", "split")
        if task and task.get("mode") == "split":
            self._mode.setCurrentIndex(1)
        self._separator = QLineEdit(
            task.get("split_separator", "<br><br>") if task else "<br><br>"
        )
        self._mode.currentIndexChanged.connect(self._on_mode_changed)

        form.addRow("Etykieta w menu:", self._label)
        form.addRow("Pole źródłowe:", self._source)
        form.addRow("Pole docelowe:", self._target)
        form.addRow("Tryb:", self._mode)
        form.addRow("Separator (split):", self._separator)
        layout.addLayout(form)

        self._on_mode_changed()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_mode_changed(self):
        self._separator.setEnabled(self._mode.currentData() == "split")

    def get_task(self) -> dict:
        task = {
            "label": self._label.text().strip(),
            "source_field": self._source.text().strip(),
            "target_field": self._target.text().strip(),
            "mode": self._mode.currentData(),
        }
        if task["mode"] == "split":
            task["split_separator"] = self._separator.text().strip() or "<br><br>"
        return task


# ---------------------------------------------------------------------------
# Main tab
# ---------------------------------------------------------------------------

class TTSTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        t = cfg.get("tts", {})
        self._or_models = []

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)

        # -- Provider selector --
        provider_form = QFormLayout()
        provider_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._provider = QComboBox()
        for key, label in _PROVIDERS.items():
            self._provider.addItem(label, key)
        current_provider = t.get("tts_provider", "kokoro")
        idx = self._provider.findData(current_provider)
        if idx >= 0:
            self._provider.setCurrentIndex(idx)
        provider_form.addRow("Dostawca TTS:", self._provider)
        layout.addLayout(provider_form)
        layout.addSpacing(8)

        # -- Stacked widget: Kokoro vs OpenRouter --
        self._stack = QStackedWidget()

        # Page 0: Kokoro
        kokoro_page = QWidget()
        kf = QFormLayout(kokoro_page)
        kf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._api_url = _expanding_line_edit(
            t.get("api_url", "http://localhost:8880/v1/audio/speech")
        )
        self._model = _expanding_line_edit(t.get("model", "kokoro"))
        kf.addRow("URL API:", self._api_url)
        kf.addRow("Model:", self._model)
        self._stack.addWidget(kokoro_page)

        # Page 1: OpenRouter
        or_page = QWidget()
        orl = QVBoxLayout(or_page)
        orl.setContentsMargins(0, 0, 0, 0)
        orf = QFormLayout()
        orf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._or_key_container, self._or_key = _api_key_widget(
            t.get("openrouter_api_key", "")
        )
        orf.addRow("Klucz API:", self._or_key_container)

        self._or_use_ai_key = QCheckBox("Użyj klucza OpenRouter z AI Generatora")
        self._or_use_ai_key.setChecked(t.get("use_ai_openrouter_key", False))
        self._or_use_ai_key.toggled.connect(self._on_use_ai_key_toggled)
        orf.addRow(self._or_use_ai_key)

        self._on_use_ai_key_toggled()

        model_row = QWidget()
        mh = QHBoxLayout(model_row)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(4)
        self._or_model = QComboBox()
        self._or_model.setEditable(True)
        self._or_model.setMinimumWidth(200)
        self._or_model.setSizePolicy(
            self._or_model.sizePolicy().horizontalPolicy().Expanding,
            self._or_model.sizePolicy().verticalPolicy(),
        )
        saved_model = t.get("openrouter_model", "openai/gpt-4o-mini-tts-2025-12-15")
        self._or_model.addItem(saved_model)
        self._or_model.setCurrentText(saved_model)
        self._or_model.currentTextChanged.connect(self._on_or_model_changed)
        self._or_fetch_btn = QPushButton("Pobierz")
        self._or_fetch_btn.setFixedWidth(70)
        self._or_fetch_btn.clicked.connect(self._fetch_models)
        mh.addWidget(self._or_model)
        mh.addWidget(self._or_fetch_btn)
        orf.addRow("Model:", model_row)

        self._or_voice_hint = QLabel(
            'Kliknij "Pobierz" aby załadować listę modeli i głosów.'
        )
        self._or_voice_hint.setWordWrap(True)
        self._or_voice_hint.setStyleSheet("color: gray;")
        orf.addRow(self._or_voice_hint)

        sel_row = QWidget()
        sh = QHBoxLayout(sel_row)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(4)
        self._select_all_btn = QPushButton("Zaznacz wszystkie")
        self._select_all_btn.clicked.connect(self._select_all)
        self._deselect_all_btn = QPushButton("Odznacz wszystkie")
        self._deselect_all_btn.clicked.connect(self._deselect_all)
        sh.addWidget(self._select_all_btn)
        sh.addWidget(self._deselect_all_btn)
        sh.addStretch()
        orf.addRow(sel_row)

        self._or_voice_list = QListWidget()
        self._or_voice_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._or_voice_list.setMaximumHeight(130)
        self._or_voice_list.itemChanged.connect(self._on_voice_checklist_changed)
        orf.addRow(self._or_voice_list)

        orl.addLayout(orf)
        orl.addStretch()
        self._stack.addWidget(or_page)

        layout.addWidget(self._stack)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        self._on_provider_changed()

        # -- Shared voices field --
        voices_form = QFormLayout()
        voices_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._voices = _expanding_line_edit(
            ", ".join(t.get("voices", ["af_bella"]))
        )
        self._voices.textChanged.connect(self._on_voices_text_changed)
        voices_form.addRow("Głosy (oddzielone przecinkiem):", self._voices)
        layout.addLayout(voices_form)

        # -- Speed --
        speed_form = QFormLayout()
        speed_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.1, 3.0)
        self._speed.setSingleStep(0.05)
        self._speed.setValue(t.get("speed", 0.9))
        speed_form.addRow("Szybkość (speed):", self._speed)
        layout.addLayout(speed_form)

        # -- Legacy fields (hidden, kept for backward compat) --
        self._ang_source = _expanding_line_edit(t.get("ang_source_field", "ang"))
        self._ang_target = _expanding_line_edit(t.get("ang_target_field", "audio"))
        self._przyklad_target = _expanding_line_edit(
            t.get("przyklad_target_field", "przyklad")
        )

        # -- Tasks --
        tasks_group = QGroupBox("Zadania TTS")
        tasks_layout = QVBoxLayout(tasks_group)

        self._task_list = QListWidget()
        self._task_list.setMaximumHeight(110)
        tasks_layout.addWidget(self._task_list)

        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(4)
        add_btn = QPushButton("Dodaj")
        add_btn.clicked.connect(self._add_task)
        edit_btn = QPushButton("Edytuj")
        edit_btn.clicked.connect(self._edit_task)
        remove_btn = QPushButton("Usuń")
        remove_btn.clicked.connect(self._remove_task)
        bh.addWidget(add_btn)
        bh.addWidget(edit_btn)
        bh.addWidget(remove_btn)
        bh.addStretch()
        tasks_layout.addWidget(btn_row)

        tasks_hint = QLabel(
            "Zadania definiują pozycje w menu TTS. Każde zadanie ma etykietę,"
            " pole źródłowe, docelowe i tryb (single/split).\n"
            "Menu jest budowane dynamicznie — możesz dodawać własne zadania."
        )
        tasks_hint.setStyleSheet("color: gray;")
        tasks_hint.setWordWrap(True)
        tasks_layout.addWidget(tasks_hint)

        layout.addWidget(tasks_group)

        # Load current tasks
        self._tasks_data: list[dict] = []
        raw_tasks = t.get("tasks")
        if raw_tasks and isinstance(raw_tasks, list):
            self._tasks_data = [
                dict(tk) for tk in raw_tasks if isinstance(tk, dict) and tk.get("label")
            ]
        self._refresh_task_list()

        layout.addSpacing(8)

        kokoro_hint = QLabel(
            "Przykładowe głosy Kokoro:\n"
            "  EN (F): af_bella, af_heart, af_nova, af_sky, af_sarah\n"
            "  EN (M): am_adam, am_echo, am_michael, bm_lewis, bm_george\n"
            "Pełna lista głosów w tts/README.md"
        )
        kokoro_hint.setStyleSheet("color: gray;")
        layout.addWidget(kokoro_hint)
        layout.addSpacing(8)

        perf_group = QGroupBox("Wydajność i sieć")
        perf_form = QFormLayout(perf_group)
        perf_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._tts_max_workers = QSpinBox()
        self._tts_max_workers.setRange(1, 64)
        self._tts_max_workers.setValue(t.get("max_workers", 12))
        self._tts_max_workers.setToolTip("Liczba równoległych wątków generowania audio")
        self._tts_max_retries = QSpinBox()
        self._tts_max_retries.setRange(1, 10)
        self._tts_max_retries.setValue(t.get("max_retries", 3))
        self._tts_max_retries.setToolTip("Liczba prób przy błędach API (429, 5xx)")
        self._tts_timeout = QSpinBox()
        self._tts_timeout.setRange(5, 600)
        self._tts_timeout.setSuffix(" s")
        self._tts_timeout.setValue(t.get("timeout", 60))
        self._tts_timeout.setToolTip("Timeout pojedynczego żądania TTS (sekundy)")
        perf_form.addRow("Maks. wątków:", self._tts_max_workers)
        perf_form.addRow("Maks. prób (retry):", self._tts_max_retries)
        perf_form.addRow("Timeout żądania:", self._tts_timeout)
        layout.addWidget(perf_group)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scrollable(inner))

    # ------------------------------------------------------------------
    # Provider switching
    # ------------------------------------------------------------------

    def _on_provider_changed(self):
        provider = self._provider.currentData()
        if provider == "openrouter":
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(0)

    def _on_use_ai_key_toggled(self):
        use_shared = self._or_use_ai_key.isChecked()
        self._or_key.setEnabled(not use_shared)
        # Also disable the show/hide button in the container
        container = self._or_key_container
        if container and hasattr(container, "layout"):
            for i in range(container.layout().count()):
                w = container.layout().itemAt(i).widget()
                if w and w is not self._or_key:
                    w.setEnabled(not use_shared)

    # ------------------------------------------------------------------
    # OpenRouter: fetch models, model selection, voice checklist
    # ------------------------------------------------------------------

    def _fetch_models(self):
        try:
            from ..tts.api import fetch_openrouter_tts_models
        except ImportError:
            from tts.api import fetch_openrouter_tts_models

        from aqt import mw

        self._or_fetch_btn.setEnabled(False)
        self._or_fetch_btn.setText("...")

        def task():
            return fetch_openrouter_tts_models(force=True)

        def on_done(fut):
            try:
                models = fut.result()
            except Exception:
                models = []
            try:
                self._or_fetch_btn.setEnabled(True)
                self._or_fetch_btn.setText("Pobierz")
                if not models:
                    showWarning(
                        "Nie udało się pobrać listy modeli TTS.\n"
                        "Sprawdź połączenie z internetem."
                    )
                    return

                self._or_models = models
                current = self._or_model.currentText()

                self._or_model.blockSignals(True)
                self._or_model.clear()
                for m in models:
                    label = f"{m['name']}  ({m['pricing']})"
                    self._or_model.addItem(label, m["id"])
                idx = self._or_model.findText(current)
                if idx >= 0:
                    self._or_model.setCurrentIndex(idx)
                else:
                    for i, m in enumerate(models):
                        if m["id"] == current:
                            self._or_model.setCurrentIndex(i)
                            break
                self._or_model.blockSignals(False)

                self._update_voice_checklist()
            except RuntimeError:
                pass  # dialog was closed while fetching

        mw.taskman.run_in_background(task, on_done)

    def _on_or_model_changed(self, _text: str):
        self._update_voice_checklist()

    def _update_voice_checklist(self):
        model_id = self._or_model.currentData()
        if not model_id:
            model_id = self._or_model.currentText()

        model_info = None
        for m in self._or_models:
            if m["id"] == model_id:
                model_info = m
                break

        self._or_voice_list.blockSignals(True)
        self._or_voice_list.clear()

        if model_info and model_info.get("voices"):
            voices = model_info["voices"]
            self._or_voice_hint.setText(
                f"{len(voices)} dostępnych głosów — zaznacz które chcesz używać:"
            )
            selected = set(
                v.strip() for v in self._voices.text().split(",") if v.strip()
            )
            has_any_match = any(v in selected for v in voices)
            for voice in voices:
                item = QListWidgetItem(voice)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                check = Qt.CheckState.Unchecked
                if has_any_match:
                    check = (
                        Qt.CheckState.Checked
                        if voice in selected
                        else Qt.CheckState.Unchecked
                    )
                else:
                    check = Qt.CheckState.Checked
                item.setCheckState(check)
                self._or_voice_list.addItem(item)
        else:
            self._or_voice_hint.setText(
                'Kliknij "Pobierz" aby załadować listę modeli i głosów.\n'
                'Możesz też wpisać model ręcznie i podać głosy poniżej.'
            )

        self._or_voice_list.blockSignals(False)
        self._on_voice_checklist_changed(None)

    def _on_voice_checklist_changed(self, _item):
        checked = []
        for i in range(self._or_voice_list.count()):
            item = self._or_voice_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked.append(item.text())
        self._voices.blockSignals(True)
        self._voices.setText(", ".join(checked))
        self._voices.blockSignals(False)

    def _on_voices_text_changed(self, _text: str):
        if self._provider.currentData() != "openrouter":
            return
        selected = set(
            v.strip() for v in self._voices.text().split(",") if v.strip()
        )
        self._or_voice_list.blockSignals(True)
        for i in range(self._or_voice_list.count()):
            item = self._or_voice_list.item(i)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.text() in selected
                else Qt.CheckState.Unchecked
            )
        self._or_voice_list.blockSignals(False)

    def _select_all(self):
        self._or_voice_list.blockSignals(True)
        for i in range(self._or_voice_list.count()):
            self._or_voice_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._or_voice_list.blockSignals(False)
        self._on_voice_checklist_changed(None)

    def _deselect_all(self):
        self._or_voice_list.blockSignals(True)
        for i in range(self._or_voice_list.count()):
            self._or_voice_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._or_voice_list.blockSignals(False)
        self._on_voice_checklist_changed(None)

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def _refresh_task_list(self):
        self._task_list.clear()
        for t in self._tasks_data:
            mode_str = "split" if t.get("mode") == "split" else "single"
            src = t.get("source_field", "?")
            dst = t.get("target_field", "?")
            item = QListWidgetItem(
                f"{t['label']}  [{mode_str}]  {src} → {dst}"
            )
            self._task_list.addItem(item)

    def _add_task(self):
        dlg = TaskEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            task = dlg.get_task()
            if task["label"] and task["source_field"] and task["target_field"]:
                self._tasks_data.append(task)
                self._refresh_task_list()

    def _edit_task(self):
        idx = self._task_list.currentRow()
        if idx < 0:
            showWarning("Zaznacz zadanie do edycji.")
            return
        dlg = TaskEditDialog(self, self._tasks_data[idx])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            task = dlg.get_task()
            if task["label"] and task["source_field"] and task["target_field"]:
                self._tasks_data[idx] = task
                self._refresh_task_list()

    def _remove_task(self):
        idx = self._task_list.currentRow()
        if idx < 0:
            showWarning("Zaznacz zadanie do usunięcia.")
            return
        del self._tasks_data[idx]
        self._refresh_task_list()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("tts", {})
        t = cfg["tts"]
        t["tts_provider"] = self._provider.currentData()
        t["api_url"] = self._api_url.text().strip()
        t["model"] = self._model.text().strip()
        t["openrouter_api_key"] = self._or_key.text().strip()
        t["use_ai_openrouter_key"] = self._or_use_ai_key.isChecked()
        # currentData() is only trustworthy when the visible text still matches
        # the selected item — the combo is editable, so the user may have typed
        # a custom model after fetching the list.
        idx = self._or_model.currentIndex()
        if (
            idx >= 0
            and self._or_model.itemData(idx)
            and self._or_model.itemText(idx) == self._or_model.currentText()
        ):
            t["openrouter_model"] = self._or_model.itemData(idx)
        else:
            t["openrouter_model"] = self._or_model.currentText().split("  (")[0].strip()
        t["voices"] = [v.strip() for v in self._voices.text().split(",") if v.strip()]
        t["speed"] = round(self._speed.value(), 2)
        t["ang_source_field"] = self._ang_source.text().strip()
        t["ang_target_field"] = self._ang_target.text().strip()
        t["przyklad_target_field"] = self._przyklad_target.text().strip()
        t["tasks"] = self._tasks_data
        t["max_workers"] = self._tts_max_workers.value()
        t["max_retries"] = self._tts_max_retries.value()
        t["timeout"] = self._tts_timeout.value()
