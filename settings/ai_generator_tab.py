"""AI Generator tab — providers, model discovery, and prompts editor."""

from functools import partial

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QPushButton, QTabWidget,
    QListWidget, QListWidgetItem, QCheckBox, QDialog, QDialogButtonBox,
)
from aqt.utils import showWarning

from ..common.ui import _expanding_line_edit, _api_key_widget, _scrollable
from .prompts_tab import PromptsTab

_PROVIDER_NAMES = ["google", "cometapi", "openai", "openrouter", "anthropic", "mistral", "opencode_go"]
_OPENAI_REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh"]


class AIGeneratorTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        ai = cfg.get("ai_generator", {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # -- Sub-tab: Workflow --
        wf_page = self._build_workflow_page(cfg.get("workflow", {}))
        tabs.addTab(wf_page, "Workflow")

        # -- Sub-tab: Prompts --
        self._prompts = PromptsTab(cfg)
        tabs.addTab(self._prompts, "Prompty")

        # -- Sub-tab: Providers + General --
        providers_page = self._build_providers_page(ai)
        tabs.addTab(providers_page, "Dostawcy")

        layout.addWidget(tabs)

    # ------------------------------------------------------------------
    # Providers page
    # ------------------------------------------------------------------

    def _build_providers_page(self, ai: dict) -> QWidget:
        providers = ai.get("providers", {})

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)

        gen_group = QGroupBox("Podstawowe")
        gen_form = QFormLayout(gen_group)
        gen_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._label = _expanding_line_edit(ai.get("button_label", "AI"))
        _skip_tags_raw = ai.get("skip_tags", ai.get("skip_tag", ["skip-ai"]))
        if isinstance(_skip_tags_raw, list):
            _skip_tags_str = ", ".join(_skip_tags_raw)
        else:
            _skip_tags_str = str(_skip_tags_raw)
        self._skip_tag = _expanding_line_edit(_skip_tags_str)
        self._skip_tag.setToolTip(
            "Tagi wykluczające — oddziel przecinkami (np. skip-ai, pomin). "
            "Zostaw puste żeby wyłączyć."
        )
        gen_form.addRow("Etykieta przycisku AI:", self._label)
        gen_form.addRow("Tagi wykluczające:", self._skip_tag)
        layout.addWidget(gen_group)
        layout.addSpacing(8)

        prov_group = QGroupBox("Dostawcy AI")
        prov_layout = QVBoxLayout(prov_group)
        provider_tabs = QTabWidget()

        self._provider_widgets: dict[str, dict] = {}
        current_provider_tab = 0
        for i, name in enumerate(_PROVIDER_NAMES):
            page = QWidget()
            prov_form = QFormLayout(page)
            prov_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            p = providers.get(name, {})
            api_key_container, api_key_field = _api_key_widget(p.get("api_key", ""))
            if p.get("api_key", "").strip() and not p.get("api_key", "").startswith("YOUR_"):
                current_provider_tab = i

            model_row = QWidget()
            mh = QHBoxLayout(model_row)
            mh.setContentsMargins(0, 0, 0, 0)
            mh.setSpacing(4)
            model_combo = QComboBox()
            model_combo.setEditable(True)
            model_combo.setMinimumWidth(200)
            model_combo.setSizePolicy(
                model_combo.sizePolicy().horizontalPolicy().Expanding,
                model_combo.sizePolicy().verticalPolicy(),
            )
            saved_model = p.get("model", "")
            if saved_model:
                model_combo.addItem(saved_model)
                model_combo.setCurrentText(saved_model)
            fetch_btn = QPushButton("Pobierz")
            fetch_btn.setFixedWidth(70)
            fetch_btn.clicked.connect(partial(self._fetch_models_for, name))
            mh.addWidget(model_combo)
            mh.addWidget(fetch_btn)

            temp = QDoubleSpinBox()
            temp.setRange(0.0, 2.0)
            temp.setSingleStep(0.05)
            temp.setValue(p.get("temperature", 0.2))

            prov_form.addRow("Klucz API:", api_key_container)
            prov_form.addRow("Model:", model_row)
            prov_form.addRow("Temperatura:", temp)
            widgets = {
                "api_key": api_key_field,
                "model": model_combo,
                "temperature": temp,
                "fetch_btn": fetch_btn,
            }
            if name in ("openai", "cometapi", "openrouter"):
                reasoning_effort = QComboBox()
                reasoning_effort.addItems(_OPENAI_REASONING_EFFORTS)
                current_effort = p.get("reasoning_effort", "medium")
                if isinstance(current_effort, str):
                    current_effort = current_effort.strip().lower()
                if current_effort not in _OPENAI_REASONING_EFFORTS:
                    current_effort = "medium"
                reasoning_effort.setCurrentText(current_effort)
                reasoning_effort.setToolTip(
                    "OpenAI reasoning_effort. Wysyłane tylko dla modeli OpenAI, "
                    "które obsługują reasoning."
                )
                prov_form.addRow("Poziom reasoning:", reasoning_effort)
                widgets["reasoning_effort"] = reasoning_effort
            elif name == "opencode_go":
                reasoning_line = _expanding_line_edit(p.get("reasoning_effort", ""))
                reasoning_line.setPlaceholderText("np. max (DeepSeek V4), high, medium — puste = wyłączone")
                reasoning_line.setToolTip(
                    "Wartość reasoning_effort wysyłana do API. Każdy model może używać innych wartości:\n"
                    "DeepSeek V4: max\n"
                    "Pozostałe modele: sprawdź dokumentację modelu.\n"
                    "Puste pole = reasoning_effort nie jest wysyłane."
                )
                prov_form.addRow("Poziom reasoning:", reasoning_line)
                widgets["reasoning_effort"] = reasoning_line
            self._provider_widgets[name] = widgets
            provider_tabs.addTab(page, name)

        provider_tabs.setCurrentIndex(current_provider_tab)
        prov_layout.addWidget(provider_tabs)
        layout.addWidget(prov_group)
        layout.addSpacing(8)

        adv_group = QGroupBox("Zaawansowane")
        adv_form = QFormLayout(adv_group)
        adv_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._batch_limit = QSpinBox()
        self._batch_limit.setRange(1, 9999)
        self._batch_limit.setValue(ai.get("batch_limit", 3))
        self._batch_sleep = QDoubleSpinBox()
        self._batch_sleep.setRange(0.0, 30.0)
        self._batch_sleep.setSingleStep(0.1)
        self._batch_sleep.setValue(ai.get("batch_sleep", 1.0))
        self._parallel_requests = QSpinBox()
        self._parallel_requests.setRange(1, 16)
        self._parallel_requests.setValue(int(ai.get("parallel_requests", 3)))
        self._parallel_requests.setToolTip(
            "Liczba notatek przetwarzanych równolegle w batchu przeglądarki.\n"
            "Wyższe wartości = szybciej, ale łatwiej o limity API (429)."
        )
        self._ai_max_retries = QSpinBox()
        self._ai_max_retries.setRange(1, 10)
        self._ai_max_retries.setValue(ai.get("max_retries", 3))
        self._ai_max_retries.setToolTip("Liczba prób przy błędach API (429, 5xx)")
        self._request_timeout = QSpinBox()
        self._request_timeout.setRange(5, 300)
        self._request_timeout.setSuffix(" s")
        self._request_timeout.setValue(ai.get("request_timeout", 30))
        self._request_timeout.setToolTip("Timeout pojedynczego żądania do API (sekundy)")
        adv_form.addRow("Limit paczki:", self._batch_limit)
        adv_form.addRow("Przerwa między paczkami:", self._batch_sleep)
        adv_form.addRow("Równoległe żądania:", self._parallel_requests)
        adv_form.addRow("Maks. prób:", self._ai_max_retries)
        adv_form.addRow("Timeout żądania:", self._request_timeout)
        layout.addWidget(adv_group)
        layout.addStretch()

        return _scrollable(inner)

    # ------------------------------------------------------------------
    # Model fetching
    # ------------------------------------------------------------------

    def _fetch_models_for(self, provider_name: str):
        w = self._provider_widgets.get(provider_name)
        if not w:
            return
        api_key = w["api_key"].text().strip()

        try:
            from ..ai_generator.providers.model_discovery import fetch_models
        except ImportError:
            from ai_generator.providers.model_discovery import fetch_models

        from aqt import mw

        btn = w.get("fetch_btn")
        if btn:
            btn.setEnabled(False)
            btn.setText("...")

        def task():
            return fetch_models(provider_name, api_key, force=True)

        def on_done(fut):
            try:
                models = fut.result()
            except Exception:
                models = []
            try:
                if btn:
                    btn.setEnabled(True)
                    btn.setText("Pobierz")
                if not models:
                    showWarning(
                        f"Nie udało się pobrać modeli dla {provider_name}.\n"
                        "Sprawdź klucz API i połączenie z internetem."
                    )
                    return

                combo = w["model"]
                current = combo.currentText()

                combo.blockSignals(True)
                combo.clear()
                for mid in models:
                    combo.addItem(mid)
                idx = combo.findText(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)
            except RuntimeError:
                pass  # dialog was closed while fetching

        mw.taskman.run_in_background(task, on_done)

    # ------------------------------------------------------------------
    # Workflow page
    # ------------------------------------------------------------------

    def _build_workflow_page(self, wf: dict) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)

        # Label
        lbl_form = QFormLayout()
        lbl_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._wf_enabled = QCheckBox("Włącz przycisk workflow w edytorze")
        self._wf_enabled.setChecked(wf.get("enabled", True))
        lbl_form.addRow(self._wf_enabled)
        self._wf_label = _expanding_line_edit(wf.get("editor_label", "Generuj fiszkę"))
        lbl_form.addRow("Etykieta przycisku:", self._wf_label)
        layout.addLayout(lbl_form)
        layout.addSpacing(8)

        # Steps list
        layout.addWidget(QLabel("Kroki workflow (kolejność = kolejność wykonania):"))
        self._wf_list = QListWidget()
        self._wf_list.setMaximumHeight(120)
        layout.addWidget(self._wf_list)

        # Buttons
        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(4)
        add_ai = QPushButton("+ AI")
        add_ai.clicked.connect(lambda: self._wf_add("ai", "generate"))
        add_dict = QPushButton("+ Słownik")
        add_dict.clicked.connect(lambda: self._wf_add("dictionary", "fetch"))
        add_tts = QPushButton("+ TTS")
        add_tts.clicked.connect(lambda: self._wf_add("tts", "generate"))
        up_btn = QPushButton("▲")
        up_btn.clicked.connect(self._wf_move_up)
        down_btn = QPushButton("▼")
        down_btn.clicked.connect(self._wf_move_down)
        remove_btn = QPushButton("Usuń")
        remove_btn.clicked.connect(self._wf_remove)
        bh.addWidget(add_ai)
        bh.addWidget(add_dict)
        bh.addWidget(add_tts)
        bh.addSpacing(8)
        bh.addWidget(up_btn)
        bh.addWidget(down_btn)
        bh.addWidget(remove_btn)
        bh.addStretch()
        layout.addWidget(btn_row)

        hint = QLabel(
            "Workflow odpala się przyciskiem w edytorze.\n"
            "AI — generuje pola, Słownik — pobiera wymowę, TTS — generuje audio."
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Load current steps
        self._wf_data = []
        for step in wf.get("steps", []):
            if isinstance(step, dict):
                self._wf_data.append(dict(step))
        self._wf_refresh()

        return page

    def _wf_refresh(self):
        self._wf_list.clear()
        for s in self._wf_data:
            mod = s.get("module", "?")
            act = s.get("action", "?")
            label = f"{mod}/{act}"
            if mod == "dictionary":
                dicts = s.get("dicts", [])
                extra = f" ({', '.join(dicts)})" if dicts else " (wszystkie)"
                label = f"Słownik: pobierz wymowę{extra}"
            elif mod == "ai":
                label = "AI: uzupełnij pola"
            elif mod == "tts":
                label = "TTS: wygeneruj audio"
            self._wf_list.addItem(QListWidgetItem(label))

    def _wf_add(self, module: str, action: str):
        step = {"module": module, "action": action}
        if module == "dictionary":
            step["dicts"] = self._wf_pick_dicts()
            if not step["dicts"]:
                return  # user cancelled
        self._wf_data.append(step)
        self._wf_refresh()

    def _wf_pick_dicts(self) -> list[str]:
        """Show dialog with checkboxes for available dictionaries. Returns list of dict IDs."""
        from ..common import get_full_config
        full = get_full_config()
        dict_cfg = full.get("dictionary", {})
        buttons = dict_cfg.get("buttons", [])
        if not buttons:
            # Fallback: read from config.json defaults
            buttons = [
                {"dictionaries": ["diki_uk", "diki_us"], "label": "Diki", "enabled": True},
                {"dictionaries": ["oxford_uk", "oxford_us"], "label": "Oxford", "enabled": True},
                {"dictionaries": ["cambridge_uk", "cambridge_us"], "label": "Cambridge", "enabled": False},
                {"dictionaries": ["longman_uk", "longman_us"], "label": "Longman", "enabled": False},
            ]

        dlg = QDialog(self)
        dlg.setWindowTitle("Wybierz słowniki")
        dlg.setMinimumWidth(300)
        layout = QVBoxLayout(dlg)

        checks = []
        for btn in buttons:
            cb = QCheckBox(btn.get("label", "?"))
            cb.setChecked(btn.get("enabled", False))
            cb.dict_ids = btn.get("dictionaries", [])
            checks.append(cb)
            layout.addWidget(cb)

        buttons_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons_box.accepted.connect(dlg.accept)
        buttons_box.rejected.connect(dlg.reject)
        layout.addWidget(buttons_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return []

        dicts = []
        for cb in checks:
            if cb.isChecked():
                dicts.extend(cb.dict_ids)
        return dicts

    def _wf_move_up(self):
        idx = self._wf_list.currentRow()
        if idx > 0:
            self._wf_data[idx], self._wf_data[idx - 1] = self._wf_data[idx - 1], self._wf_data[idx]
            self._wf_refresh()
            self._wf_list.setCurrentRow(idx - 1)

    def _wf_move_down(self):
        idx = self._wf_list.currentRow()
        if 0 <= idx < len(self._wf_data) - 1:
            self._wf_data[idx], self._wf_data[idx + 1] = self._wf_data[idx + 1], self._wf_data[idx]
            self._wf_refresh()
            self._wf_list.setCurrentRow(idx + 1)

    def _wf_remove(self):
        idx = self._wf_list.currentRow()
        if idx >= 0:
            del self._wf_data[idx]
            self._wf_refresh()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("ai_generator", {})
        ai = cfg["ai_generator"]
        ai["button_label"] = self._label.text().strip()
        ai["skip_tags"] = [t.strip() for t in self._skip_tag.text().split(",") if t.strip()]
        ai["batch_limit"] = self._batch_limit.value()
        ai["batch_sleep"] = round(self._batch_sleep.value(), 2)
        ai["parallel_requests"] = self._parallel_requests.value()
        ai["max_retries"] = self._ai_max_retries.value()
        ai["request_timeout"] = self._request_timeout.value()
        ai.setdefault("providers", {})
        for name, w in self._provider_widgets.items():
            ai["providers"].setdefault(name, {})
            ai["providers"][name]["api_key"] = w["api_key"].text().strip()
            ai["providers"][name]["model"] = w["model"].currentText().strip()
            ai["providers"][name]["temperature"] = round(w["temperature"].value(), 2)
            if "reasoning_effort" in w:
                re_widget = w["reasoning_effort"]
                if hasattr(re_widget, "currentText"):
                    ai["providers"][name]["reasoning_effort"] = re_widget.currentText()
                else:
                    ai["providers"][name]["reasoning_effort"] = re_widget.text().strip()

        self._prompts.apply(cfg)

        cfg.setdefault("workflow", {})
        cfg["workflow"]["enabled"] = self._wf_enabled.isChecked()
        cfg["workflow"]["editor_label"] = self._wf_label.text().strip()
        cfg["workflow"]["steps"] = self._wf_data
