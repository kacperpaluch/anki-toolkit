"""TTS tab — provider selection, Kokoro/OpenRouter settings, voices, tasks, performance."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QStackedWidget, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QDialog, QDialogButtonBox,
    Qt, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QToolButton,
)
from aqt.utils import showWarning, tooltip
from aqt import mw
from aqt.sound import av_player

from ..common.ui import (
    _expanding_line_edit, _api_key_widget, _scrollable, hint_label,
    collapsible_section, _filterable_combo, get_all_field_names,
)

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

        fields = get_all_field_names()
        self._label = QLineEdit(task.get("label", "") if task else "")
        self._source = _filterable_combo(fields, task.get("source_field", "") if task else "")
        self._target = _filterable_combo(fields, task.get("target_field", "") if task else "")
        self._mode = QComboBox()
        self._mode.addItem("Pojedyncze audio", "single")
        self._mode.addItem("Dzielone (split)", "split")
        self._mode.addItem("Dzielone — tylko audio", "split_audio")
        if task:
            idx = self._mode.findData(task.get("mode", "single"))
            if idx >= 0:
                self._mode.setCurrentIndex(idx)
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
        self._separator.setEnabled(
            self._mode.currentData() in ("split", "split_audio")
        )

    def get_task(self) -> dict:
        task = {
            "label": self._label.text().strip(),
            "source_field": self._source.currentText().strip(),
            "target_field": self._target.currentText().strip(),
            "mode": self._mode.currentData(),
        }
        if task["mode"] in ("split", "split_audio"):
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
        kf.addRow(hint_label(
            "Przykładowe głosy Kokoro:\n"
            "  EN (F): af_bella, af_heart, af_nova, af_sky, af_sarah\n"
            "  EN (M): am_adam, am_echo, am_michael, bm_lewis, bm_george\n"
            "Pełna lista głosów w tts/README.md"
        ))
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

        self._or_provider = QComboBox()
        self._or_provider.addItem("Automatycznie (najtańszy sprawny)", "")
        saved_or_provider = t.get("openrouter_provider", "")
        if saved_or_provider:
            self._or_provider.addItem(saved_or_provider, saved_or_provider)
            self._or_provider.setCurrentIndex(1)
        self._or_provider.setEnabled(False)
        orf.addRow("Dostawca modelu:", self._or_provider)

        self._or_provider_hint = hint_label(
            'Wybierz model po kliknięciu „Pobierz”, aby zobaczyć dostawców i ich ceny.'
        )
        orf.addRow(self._or_provider_hint)

        self._or_voice_hint = hint_label(
            'Kliknij "Pobierz" aby załadować listę modeli i głosów.'
        )
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

        self._or_voice_list = QTableWidget(0, 2)
        self._or_voice_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._or_voice_list.verticalHeader().setVisible(False)
        self._or_voice_list.horizontalHeader().setVisible(False)
        self._or_voice_list.setMaximumHeight(200)
        self._or_voice_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._or_voice_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        # connect raz — _update_voice_checklist przebudowuje wiersze wielokrotnie,
        # a ponowny connect przy każdej przebudowie akumulowałby połączenia.
        self._or_voice_list.itemChanged.connect(self._on_voice_checklist_changed)
        orf.addRow(self._or_voice_list)

        orl.addLayout(orf)
        orl.addStretch()
        self._stack.addWidget(or_page)

        provider_group = QGroupBox("Ustawienia dostawcy")
        pg_layout = QVBoxLayout(provider_group)
        pg_layout.addWidget(self._stack)
        layout.addWidget(provider_group)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        self._on_provider_changed()

        # -- Shared voices field (hidden for OpenRouter once the checklist
        #    has entries — then the checklist is the editor) --
        voices_form = QFormLayout()
        voices_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._voices = _expanding_line_edit(
            ", ".join(t.get("voices", ["af_bella"]))
        )
        self._voices.textChanged.connect(self._on_voices_text_changed)
        self._voices_label = QLabel("Głosy (oddzielone przecinkiem):")
        voices_form.addRow(self._voices_label, self._voices)
        layout.addLayout(voices_form)
        self._update_voices_row_visibility()

        # -- Speed --
        speed_form = QFormLayout()
        speed_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.1, 3.0)
        self._speed.setSingleStep(0.05)
        self._speed.setValue(t.get("speed", 0.9))
        speed_form.addRow("Szybkość (speed):", self._speed)
        layout.addLayout(speed_form)

        # -- Word replacements (applied only to text sent to the engine) --
        repl_group = QGroupBox("Zamiana wyrazów (przed syntezą)")
        rg = QVBoxLayout(repl_group)
        self._repl_table = QTableWidget(0, 2)
        self._repl_table.setHorizontalHeaderLabels(["Skrót", "Zamiennik"])
        self._repl_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._repl_table.verticalHeader().setVisible(False)
        self._repl_table.setMaximumHeight(140)
        for k, v in (t.get("replacements") or {}).items():
            self._add_repl_row(k, v)
        rg.addWidget(self._repl_table)

        repl_btns = QWidget()
        rbh = QHBoxLayout(repl_btns)
        rbh.setContentsMargins(0, 0, 0, 0)
        rbh.setSpacing(4)
        repl_add = QPushButton("Dodaj")
        repl_add.clicked.connect(lambda: self._add_repl_row("", ""))
        repl_del = QPushButton("Usuń")
        repl_del.clicked.connect(self._remove_repl_row)
        rbh.addWidget(repl_add)
        rbh.addWidget(repl_del)
        rbh.addStretch()
        rg.addWidget(repl_btns)

        rg.addWidget(hint_label(
            "Skrót zamieniany na pełne słowo tylko w tekście wysyłanym do TTS"
            " (np. sb → somebody). Zamieniane są całe słowa, bez rozróżniania"
            " wielkości liter; treść karty pozostaje bez zmian."
        ))
        layout.addWidget(repl_group)

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

        tasks_layout.addWidget(hint_label(
            "Zadania definiują pozycje w menu TTS. Każde zadanie ma etykietę,"
            " pole źródłowe, docelowe i tryb (single/split).\n"
            "Menu jest budowane dynamicznie — możesz dodawać własne zadania."
        ))

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

        perf_container, perf_body = collapsible_section("Wydajność i sieć (zaawansowane)")
        perf_form = QFormLayout()
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
        perf_body.addLayout(perf_form)
        layout.addWidget(perf_container)
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
        # Called once during __init__ before the voices row exists.
        if hasattr(self, "_voices_label"):
            self._update_voices_row_visibility()

    def _update_voices_row_visibility(self):
        """Text field is the editor for Kokoro / manual OpenRouter models;
        once the OpenRouter checklist has voices, the checklist takes over."""
        manual = (
            self._provider.currentData() != "openrouter"
            or self._or_voice_list.rowCount() == 0
        )
        self._voices_label.setVisible(manual)
        self._voices.setVisible(manual)

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
                self._fetch_model_providers()
            except RuntimeError:
                pass  # dialog was closed while fetching

        mw.taskman.run_in_background(task, on_done)

    def _on_or_model_changed(self, _text: str):
        self._update_voice_checklist()
        self._fetch_model_providers()

    def _current_or_model_id(self) -> str:
        idx = self._or_model.currentIndex()
        if (
            idx >= 0
            and self._or_model.itemData(idx)
            and self._or_model.itemText(idx) == self._or_model.currentText()
        ):
            return self._or_model.itemData(idx)
        return self._or_model.currentText().split("  (")[0].strip()

    def _fetch_model_providers(self):
        """Load per-provider prices after choosing an OpenRouter TTS model."""
        model_id = self._current_or_model_id()
        if not model_id or "/" not in model_id:
            return
        try:
            from ..tts.api import fetch_openrouter_tts_providers
            from ..tts.config import resolve_openrouter_key
        except ImportError:
            from tts.api import fetch_openrouter_tts_providers
            from tts.config import resolve_openrouter_key

        api_key = resolve_openrouter_key(self._build_preview_config())
        if not api_key:
            self._or_provider.setEnabled(False)
            self._or_provider_hint.setText("Podaj klucz API OpenRouter, aby pobrać dostawców i ceny.")
            return

        self._or_provider.setEnabled(False)
        self._or_provider_hint.setText("Pobieranie dostawców i cen…")

        def task():
            return fetch_openrouter_tts_providers(model_id, api_key)

        def on_done(fut):
            try:
                providers = fut.result()
            except Exception:
                providers = []
            try:
                # Ignore a delayed result for a model that is no longer selected.
                if model_id != self._current_or_model_id():
                    return
                saved = self._or_provider.currentData() or ""
                self._or_provider.blockSignals(True)
                self._or_provider.clear()
                self._or_provider.addItem("Automatycznie (najtańszy sprawny)", "")
                for provider in providers:
                    self._or_provider.addItem(
                        f"{provider['name']}  ({provider['pricing']})",
                        provider["id"],
                    )
                index = self._or_provider.findData(saved)
                self._or_provider.setCurrentIndex(index if index >= 0 else 0)
                self._or_provider.blockSignals(False)
                self._or_provider.setEnabled(bool(providers))
                self._or_provider_hint.setText(
                    "Wybierz dostawcę, aby wymusić go bez fallbacku."
                    if providers else
                    "Nie udało się pobrać dostawców dla tego modelu."
                )
            except RuntimeError:
                pass

        mw.taskman.run_in_background(task, on_done)

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
        self._or_voice_list.setRowCount(0)

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
                row = self._or_voice_list.rowCount()
                self._or_voice_list.insertRow(row)

                item = QTableWidgetItem(voice)
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
                self._or_voice_list.setItem(row, 0, item)

                play_btn = QToolButton()
                play_btn.setText("▶")
                play_btn.setFixedWidth(30)
                play_btn.setToolTip(f'Podgląd głosu: {voice}')
                play_btn.clicked.connect(
                    lambda _checked=False, v=voice: self._play_voice_sample(v)
                )
                self._or_voice_list.setCellWidget(row, 1, play_btn)
        else:
            self._or_voice_hint.setText(
                'Kliknij "Pobierz" aby załadować listę modelów i głosów.\n'
                'Możesz też wpisać model ręcznie i podać głosy poniżej.'
            )

        self._or_voice_list.blockSignals(False)
        self._on_voice_checklist_changed(None)
        self._update_voices_row_visibility()

    def _on_voice_checklist_changed(self, _item):
        checked = []
        for row in range(self._or_voice_list.rowCount()):
            item = self._or_voice_list.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
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
        for row in range(self._or_voice_list.rowCount()):
            item = self._or_voice_list.item(row, 0)
            if item:
                item.setCheckState(
                    Qt.CheckState.Checked
                    if item.text() in selected
                    else Qt.CheckState.Unchecked
                )
        self._or_voice_list.blockSignals(False)

    def _select_all(self):
        self._or_voice_list.blockSignals(True)
        for row in range(self._or_voice_list.rowCount()):
            item = self._or_voice_list.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self._or_voice_list.blockSignals(False)
        self._on_voice_checklist_changed(None)

    def _deselect_all(self):
        self._or_voice_list.blockSignals(True)
        for row in range(self._or_voice_list.rowCount()):
            item = self._or_voice_list.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._or_voice_list.blockSignals(False)
        self._on_voice_checklist_changed(None)

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def _refresh_task_list(self):
        self._task_list.clear()
        for t in self._tasks_data:
            mode_str = t.get("mode", "single")
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
    # Word replacements
    # ------------------------------------------------------------------

    def _add_repl_row(self, key: str, value: str):
        r = self._repl_table.rowCount()
        self._repl_table.insertRow(r)
        self._repl_table.setItem(r, 0, QTableWidgetItem(key))
        self._repl_table.setItem(r, 1, QTableWidgetItem(value))

    def _remove_repl_row(self):
        r = self._repl_table.currentRow()
        if r >= 0:
            self._repl_table.removeRow(r)

    def _collect_replacements(self) -> dict:
        out = {}
        for r in range(self._repl_table.rowCount()):
            k_item = self._repl_table.item(r, 0)
            v_item = self._repl_table.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k and v:
                out[k] = v
        return out

    # ------------------------------------------------------------------
    # Voice preview
    # ------------------------------------------------------------------

    _PREVIEW_TEXT = "Hello, this is a voice sample for text-to-speech preview."

    def _current_voices(self) -> list[str]:
        text = self._voices.text().strip()
        if not text:
            return []
        return [v.strip() for v in text.split(",") if v.strip()]

    def _build_preview_config(self) -> dict:
        """Build a TTS config dict from current (unsaved) UI state."""
        config = {
            "tts_provider": self._provider.currentData(),
            "api_url": self._api_url.text().strip(),
            "model": self._model.text().strip(),
            "openrouter_api_key": self._or_key.text().strip(),
            "use_ai_openrouter_key": self._or_use_ai_key.isChecked(),
            "openrouter_provider": self._or_provider.currentData() or "",
            "speed": self._speed.value(),
            "max_retries": 2,
            "timeout": 30,
        }
        idx = self._or_model.currentIndex()
        if (
            idx >= 0
            and self._or_model.itemData(idx)
            and self._or_model.itemText(idx) == self._or_model.currentText()
        ):
            config["openrouter_model"] = self._or_model.itemData(idx)
        else:
            config["openrouter_model"] = self._or_model.currentText().split("  (")[0].strip()
        return config

    def _play_voice_sample(self, voice: str):
        from ..tts.api import generate_audio

        config = self._build_preview_config()

        # Find the ▶ button for this voice to show in-progress state
        btn = None
        for row in range(self._or_voice_list.rowCount()):
            item = self._or_voice_list.item(row, 0)
            if item and item.text() == voice:
                btn = self._or_voice_list.cellWidget(row, 1)
                break

        if btn:
            btn.setEnabled(False)
            btn.setText("…")

        def task():
            return generate_audio(self._PREVIEW_TEXT, config, voice)

        def on_done(fut):
            if btn:
                btn.setEnabled(True)
                btn.setText("▶")
            try:
                audio_bytes = fut.result()
            except Exception as e:
                tooltip(f"Podgląd głosu ({voice}): błąd — {e}", period=8000)
                return

            # ponytail: one reusable media file, overwritten each preview
            fname = mw.col.media.write_data("_tts_preview.mp3", audio_bytes)
            av_player.play_file(fname)
            tooltip(f"Odtwarzanie: {voice}", period=3000)

        mw.taskman.run_in_background(task, on_done)

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
        t["openrouter_provider"] = self._or_provider.currentData() or ""
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
        t["replacements"] = self._collect_replacements()
        t["speed"] = round(self._speed.value(), 2)
        t["tasks"] = self._tasks_data
        t["max_workers"] = self._tts_max_workers.value()
        t["max_retries"] = self._tts_max_retries.value()
        t["timeout"] = self._tts_timeout.value()
