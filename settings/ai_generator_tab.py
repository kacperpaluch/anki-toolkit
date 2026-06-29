"""AI Generator tab — providers, model discovery, and prompts editor."""

from functools import partial

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton, QTabWidget,
    QListWidget, QListWidgetItem,
    QStackedWidget, QSizePolicy,
)
from aqt.utils import showWarning

from ..common.ui import (
    _expanding_line_edit, _filterable_combo, _api_key_widget, _scrollable,
    hint_label, collapsible_section,
)
from ..ai_generator.providers import PROVIDERS, PROVIDER_LABELS
from .prompts_tab import PromptsTab

_PROVIDER_NAMES = list(PROVIDERS)
_OPENAI_REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh"]


def _has_real_key(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and not value.startswith("YOUR_")


class AIGeneratorTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        ai = cfg.get("ai_generator", {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # Build provider widgets first so the prompts tab can read unsaved keys/defaults.
        providers_page = self._build_providers_page(ai)

        # Workflows now live in their own top-level "Workflowy" tab.

        # -- Sub-tab: Prompts --
        self._prompts = PromptsTab(cfg, self._current_provider_settings)
        tabs.addTab(self._prompts, "Prompty")

        # -- Sub-tab: Providers + General --
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
        prov_layout = QHBoxLayout(prov_group)
        prov_layout.setSpacing(8)

        # List + detail instead of a third level of tabs. ✓ marks providers
        # with a real API key and follows edits live.
        self._prov_list = QListWidget()
        self._prov_list.setFixedWidth(150)
        self._prov_list.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self._prov_stack = QStackedWidget()

        self._provider_widgets: dict[str, dict] = {}
        current_provider_tab = 0
        for i, name in enumerate(_PROVIDER_NAMES):
            page = QWidget()
            prov_form = QFormLayout(page)
            prov_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            p = providers.get(name, {})
            api_key_container, api_key_field = _api_key_widget(p.get("api_key", ""))
            if _has_real_key(p.get("api_key", "")):
                current_provider_tab = i

            model_row = QWidget()
            mh = QHBoxLayout(model_row)
            mh.setContentsMargins(0, 0, 0, 0)
            mh.setSpacing(4)
            saved_model = p.get("model", "")
            cached_models = p.get("cached_models", [])
            combo_items = list(cached_models) if cached_models else (
                [saved_model] if saved_model else []
            )
            model_combo = _filterable_combo(combo_items, saved_model)
            model_combo.setMinimumWidth(200)
            model_combo.setSizePolicy(
                model_combo.sizePolicy().horizontalPolicy().Expanding,
                model_combo.sizePolicy().verticalPolicy(),
            )
            fetch_btn = QPushButton("Pobierz")
            fetch_btn.setFixedWidth(70)
            fetch_btn.clicked.connect(partial(self._fetch_models_for, name))
            mh.addWidget(model_combo)
            mh.addWidget(fetch_btn)

            temp = QDoubleSpinBox()
            temp.setRange(0.0, 2.0)
            temp.setSingleStep(0.05)
            temp.setValue(p.get("temperature", 0.2))

            fallback_model = _expanding_line_edit(p.get("fallback_model", ""))
            fallback_model.setPlaceholderText("np. gpt-4o-mini (puste = brak fallbacku)")
            fallback_model.setToolTip(
                "Model zapasowy uruchamiany gdy główny model zawiedzie "
                "(błąd API, rate limit, brak środków, brak treści).\n"
                "Używa tego samego providera i tego samego klucza API.\n"
                "Puste pole = brak fallbacku na poziomie providera.\n"
                "Prompt może nadpisać ten fallback własnym."
            )

            prov_form.addRow("Klucz API:", api_key_container)
            model_combo.setToolTip(
                "Model domyślny dla nowych i starszych promptów. Każdy prompt "
                "może wybrać własny model. Wpisywanie filtruje listę po fragmencie."
            )
            prov_form.addRow("Model domyślny:", model_row)
            prov_form.addRow("Temperatura:", temp)
            prov_form.addRow("Model zapasowy:", fallback_model)

            # --- Rate limit (per provider) -------------------------------
            # Back-compat: openrouter prefills from the old global :free knobs.
            _is_or = name == "openrouter"
            rpm = QSpinBox()
            rpm.setRange(0, 1000)
            rpm.setValue(int(p.get(
                "rpm", ai.get("free_model_rate_limit", 20) if _is_or else 0)))
            rpm.setToolTip(
                "Maks. żądań na minutę dla tego dostawcy. Żądania są rozkładane "
                "równomiernie (60/RPM s odstępu), więc batch nie burstuje.\n"
                "0 = bez limitu.\n"
                "Jeśli dostawca podaje limit jako RPS (żądania/s), pomnóż ×60:\n"
                "  Mistral free 0.83 RPS → 50 RPM (40 zostawia margines)\n"
                "  OpenRouter 20 RPM → wpisz 20."
            )
            max_conc = QSpinBox()
            max_conc.setRange(0, 16)
            max_conc.setValue(int(p.get(
                "max_concurrent",
                ai.get("free_model_max_concurrent", 1) if _is_or else 0)))
            max_conc.setToolTip(
                "Maks. równoległych żądań do tego dostawcy.\n"
                "0 = bez limitu. Darmowe API zwykle wymagają 1."
            )
            prov_form.addRow("Limit RPM:", rpm)
            prov_form.addRow("Maks. równoległych:", max_conc)

            widgets = {
                "api_key": api_key_field,
                "model": model_combo,
                "temperature": temp,
                "fallback_model": fallback_model,
                "fetch_btn": fetch_btn,
                "rpm": rpm,
                "max_concurrent": max_conc,
            }

            # ':free' is an OpenRouter-only concept (free model variants live
            # only there). Other providers' limits always cover every request.
            if _is_or:
                free_only = QCheckBox("Limit tylko dla modeli :free")
                free_only.setChecked(bool(p.get("rate_limit_free_only", True)))
                free_only.setToolTip(
                    "Zaznaczone: limit dotyczy tylko modeli z ':free' w nazwie "
                    "— płatne modele OpenRoutera nie są dławione.\n"
                    "Odznaczone: limit dotyczy wszystkich żądań OpenRoutera."
                )
                prov_form.addRow("", free_only)
                widgets["rate_limit_free_only"] = free_only
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

            item = QListWidgetItem()
            self._prov_list.addItem(item)
            self._prov_stack.addWidget(page)
            self._update_provider_item(i, name)
            api_key_field.textChanged.connect(
                partial(self._on_provider_key_changed, i, name)
            )

        self._prov_list.currentRowChanged.connect(self._prov_stack.setCurrentIndex)
        self._prov_list.setCurrentRow(current_provider_tab)
        prov_layout.addWidget(self._prov_list)
        prov_layout.addWidget(self._prov_stack, 1)
        layout.addWidget(prov_group)
        layout.addSpacing(8)

        adv_container, adv_body = collapsible_section("Zaawansowane (wydajność, limity, sieć)")
        adv_form = QFormLayout()
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
        adv_form.addRow(hint_label(
            "Limity RPM / równoległości ustawisz osobno dla każdego dostawcy "
            "wyżej (sekcja „Dostawcy AI”)."
        ))
        adv_body.addLayout(adv_form)
        layout.addWidget(adv_container)
        layout.addStretch()

        return _scrollable(inner)

    def _update_provider_item(self, row: int, name: str) -> None:
        item = self._prov_list.item(row)
        if item is None:
            return
        has_key = _has_real_key(self._provider_widgets[name]["api_key"].text())
        icon = "✓" if has_key else "○"
        item.setText(f"{icon} {PROVIDER_LABELS.get(name, name)}")

    def _on_provider_key_changed(self, row: int, name: str, _text: str = "") -> None:
        self._update_provider_item(row, name)

    def _current_provider_settings(self, name: str) -> dict:
        """Return live provider values, including unsaved edits in this dialog."""
        widgets = self._provider_widgets.get(name)
        if not widgets:
            return {}
        combo_models = [
            widgets["model"].itemText(i)
            for i in range(widgets["model"].count())
        ]
        return {
            "api_key": widgets["api_key"].text().strip(),
            "model": widgets["model"].currentText().strip(),
            "models": combo_models,
            "cached_models": combo_models,
        }

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
        ai.pop("free_model_rate_limit", None)  # migrated to per-provider rpm
        ai.pop("free_model_max_concurrent", None)
        ai.setdefault("providers", {})
        for name, w in self._provider_widgets.items():
            ai["providers"].setdefault(name, {})
            ai["providers"][name]["api_key"] = w["api_key"].text().strip()
            ai["providers"][name]["model"] = w["model"].currentText().strip()
            ai["providers"][name]["cached_models"] = [
                w["model"].itemText(i) for i in range(w["model"].count())
            ]
            ai["providers"][name]["temperature"] = round(w["temperature"].value(), 2)
            ai["providers"][name]["fallback_model"] = w["fallback_model"].text().strip()
            ai["providers"][name]["rpm"] = w["rpm"].value()
            ai["providers"][name]["max_concurrent"] = w["max_concurrent"].value()
            if "rate_limit_free_only" in w:
                ai["providers"][name]["rate_limit_free_only"] = \
                    w["rate_limit_free_only"].isChecked()
            if "reasoning_effort" in w:
                re_widget = w["reasoning_effort"]
                if hasattr(re_widget, "currentText"):
                    ai["providers"][name]["reasoning_effort"] = re_widget.currentText()
                else:
                    ai["providers"][name]["reasoning_effort"] = re_widget.text().strip()

        self._prompts.apply(cfg)
