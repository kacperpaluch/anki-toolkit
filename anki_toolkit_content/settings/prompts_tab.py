"""Prompts tab — two-panel editor for note_type→field prompts.

The left list follows the configuration order — that is also the generation
order (a later prompt may use the target of an earlier task), so the ▲▼
buttons reorder both the list and the saved config.
"""

import re

from aqt import mw
from aqt.utils import showWarning
from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter,
    QPushButton, Qt, QComboBox, QMenu, QPlainTextEdit,
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QDialog, QDialogButtonBox, QCheckBox, QDoubleSpinBox, QInputDialog,
)

from ..common import clean_html_normalized
from ..common.ui import (
    _expanding_line_edit, _filterable_combo, get_note_type_names,
    get_fields_for_note_type, get_sample_notes, palette, hint_label,
)
from ..ai_generator.template_engine import (
    template_structure_problems, render_template, IF_PATTERN,
)
from ..ai_generator.providers import PROVIDER_LABELS, PROVIDERS

_VAR_RE = re.compile(r'{{(.*?)}}')
_IF_RE = re.compile(r'{%\s*if\s+([^%]+)%}')
_BLOCK_RE = re.compile(r'{%.*?%}')


def _has_real_key(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and not value.startswith("YOUR_")


def _editable_combo(items: list[str]) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(items)
    combo.setCurrentText("")
    return combo


class _TemplateHighlighter(QSyntaxHighlighter):
    """Colors {{fields}} and {% blocks %}; unknown fields get a wavy underline."""

    def __init__(self, document):
        super().__init__(document)
        pal = palette()

        self._fmt_var = QTextCharFormat()
        self._fmt_var.setForeground(QColor(pal["syntax_var"]))
        self._fmt_var.setFontWeight(QFont.Weight.Bold)

        self._fmt_block = QTextCharFormat()
        self._fmt_block.setForeground(QColor(pal["syntax_block"]))
        self._fmt_block.setFontWeight(QFont.Weight.Bold)

        self._fmt_bad = QTextCharFormat()
        self._fmt_bad.setForeground(QColor(pal["syntax_bad"]))
        self._fmt_bad.setFontWeight(QFont.Weight.Bold)
        self._fmt_bad.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.WaveUnderline
        )
        self._fmt_bad.setUnderlineColor(QColor(pal["syntax_bad"]))

        self._known: set[str] | None = None

    def set_known_fields(self, known: set[str] | None) -> None:
        # rehighlight() re-emits textChanged → only run on real changes,
        # otherwise validate→highlight→validate would loop.
        if known != self._known:
            self._known = known
            self.rehighlight()

    def _is_unknown(self, name: str) -> bool:
        return bool(self._known is not None and name and name not in self._known)

    def highlightBlock(self, text: str) -> None:
        for m in _BLOCK_RE.finditer(text):
            fmt = self._fmt_block
            if_match = _IF_RE.match(m.group(0))
            if if_match and self._is_unknown(if_match.group(1).strip()):
                fmt = self._fmt_bad
            self.setFormat(m.start(), m.end() - m.start(), fmt)
        for m in _VAR_RE.finditer(text):
            name = m.group(1).strip()
            fmt = self._fmt_bad if self._is_unknown(name) else self._fmt_var
            self.setFormat(m.start(), m.end() - m.start(), fmt)


class PromptPreviewDialog(QDialog):
    """Renders the prompt on a real note from the collection — fields
    substituted, HTML cleaned and {% if %} branches resolved."""

    def __init__(self, parent, note_type: str, prompt: str):
        super().__init__(parent)
        self.setWindowTitle(f"Podgląd promptu — {note_type or '(brak typu notatki)'}")
        self.resize(640, 520)
        self._prompt = prompt

        layout = QVBoxLayout(self)

        note_row = QHBoxLayout()
        note_row.addWidget(QLabel("Notatka:"))
        self._note_combo = QComboBox()
        self._note_combo.setSizePolicy(
            self._note_combo.sizePolicy().horizontalPolicy().Expanding,
            self._note_combo.sizePolicy().verticalPolicy(),
        )
        note_row.addWidget(self._note_combo, 1)
        layout.addLayout(note_row)

        self._conditions = hint_label("")
        self._conditions.setVisible(False)
        layout.addWidget(self._conditions)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        layout.addWidget(self._text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for nid, label in get_sample_notes(note_type, limit=20):
            self._note_combo.addItem(label, nid)
        self._note_combo.currentIndexChanged.connect(lambda _i: self._render())
        self._render()

    def _render(self) -> None:
        nid = self._note_combo.currentData()
        if nid is None:
            self._conditions.setVisible(False)
            self._text.setPlainText("(brak notatek tego typu w kolekcji)")
            return

        try:
            from aqt import mw
            note = mw.col.get_note(nid)
            fields_map = {f: clean_html_normalized(note[f]) for f in note.keys()}
        except Exception:
            self._conditions.setVisible(False)
            self._text.setPlainText("(nie udało się wczytać notatki)")
            return

        # Which {% if %} branch fires for this note — the part that makes
        # conditionals understandable at a glance.
        cond_lines = []
        for m in IF_PATTERN.finditer(self._prompt):
            field = m.group(1).strip()
            filled = bool(fields_map.get(field, "").strip())
            branch = "IF (pole wypełnione)" if filled else "ELSE (pole puste)"
            cond_lines.append(f"{{% if {field} %}} → gałąź {branch}")
        self._conditions.setText("\n".join(cond_lines))
        self._conditions.setVisible(bool(cond_lines))

        self._text.setPlainText(render_template(self._prompt, fields_map))


class PromptsTab(QWidget):
    """Two-panel editor: list of note_type→field on left, prompt editor on right."""

    def __init__(self, cfg: dict, provider_settings=None):
        super().__init__()
        self._data: dict = {}
        self._current_key: tuple | None = None

        ai = cfg.get("ai_generator", {})
        self._providers_cfg = ai.get("providers", {})
        self._provider_settings = provider_settings or (
            lambda name: self._providers_cfg.get(name, {})
        )
        self._model_options: dict[str, list[str]] = {}
        note_types = ai.get("note_types", {})
        for nt_name, fields in note_types.items():
            for field_name, field_cfg in fields.items():
                key = (nt_name, field_name)
                provider = field_cfg.get("provider", "openai")
                self._data[key] = {
                    "target":      field_cfg.get("target", field_name),
                    "provider":    provider,
                    "model":       field_cfg.get("model", ""),
                    "prompt":      field_cfg.get("prompt", ""),
                    "manual_only": bool(field_cfg.get("manual_only", False)),
                    "fallback_provider": field_cfg.get("fallback_provider", ""),
                    "fallback_model":    field_cfg.get("fallback_model", ""),
                    "temperature":       field_cfg.get("temperature"),
                }

        # Default provider for a new prompt: first usable one. "Usable" is a
        # real API key, or — for local providers like Codex CLI — a model,
        # since those authenticate outside the add-on.
        self._default_provider = "openai"
        for name, p in ai.get("providers", {}).items():
            if not isinstance(p, dict):
                continue
            cls = PROVIDERS.get(name)
            if getattr(cls, "REQUIRES_API_KEY", True):
                usable = _has_real_key(p.get("api_key", ""))
            else:
                usable = bool(p.get("model", "").strip())
            if usable:
                self._default_provider = name
                break

        pal = palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 4, 8)

        left_layout.addWidget(QLabel("Typ notatki → zadanie:"))

        # Filtr po typie notatki — przy wielu typach płaska lista robi się
        # nieczytelna; filtr pokazuje tylko wybrany typ.
        self._filter_combo = QComboBox()
        self._filter_combo.setToolTip("Pokaż zadania tylko wybranego typu notatki.")
        self._populate_filter()
        left_layout.addWidget(self._filter_combo)

        self._list = QListWidget()
        self._list.setMinimumWidth(160)
        self._list.setMaximumWidth(240)
        left_layout.addWidget(self._list)
        # Lista renderowana z self._data przez _rebuild_list() (na końcu __init__,
        # gdy istnieją już widgety edytora): pogrupowana po typie notatki,
        # w kolejności configu = kolejności generowania.

        order_row = QHBoxLayout()
        self._btn_up = QPushButton("▲")
        self._btn_up.setToolTip(
            "Przesuń zadanie wyżej. Kolejność na liście = kolejność generowania —\n"
            "późniejszy prompt może użyć pola wygenerowanego przez wcześniejsze zadanie."
        )
        self._btn_down = QPushButton("▼")
        self._btn_down.setToolTip(self._btn_up.toolTip())
        order_row.addWidget(self._btn_up)
        order_row.addWidget(self._btn_down)
        left_layout.addLayout(order_row)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("+ Dodaj…")
        self._btn_add.setToolTip(
            "Dodaje puste zadanie AI dla wybranego typu notatki i pola."
        )
        self._btn_del = QPushButton("Usuń")
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_del)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 8, 8, 8)

        self._editor_placeholder = QLabel(
            "Wybierz zadanie z listy po lewej\nalbo kliknij „+ Dodaj…”,\n"
            "żeby dodać nowe zadanie AI."
        )
        self._editor_placeholder.setStyleSheet(f"color: {pal['muted']};")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._editor_widget = QWidget()
        editor_form_layout = QVBoxLayout(self._editor_widget)
        editor_form_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._note_type_names = get_note_type_names()
        self._ed_note_type = _editable_combo(self._note_type_names)
        self._ed_field = _expanding_line_edit()
        self._ed_field.setToolTip(
            "Identyfikator zadania w konfiguracji — zwykle taki sam jak pole docelowe."
        )
        self._ed_target = _editable_combo([])
        self._ed_provider = QComboBox()
        for name, label in PROVIDER_LABELS.items():
            self._ed_provider.addItem(label, name)
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(4)
        self._ed_model = _filterable_combo()
        self._ed_model.setMinimumWidth(200)
        self._ed_model.setToolTip(
            "Model używany tylko przez ten prompt. Wpisywanie filtruje listę "
            "po dowolnym fragmencie, np. 5.5."
        )
        self._btn_fetch_models = QPushButton("Pobierz")
        self._btn_fetch_models.setFixedWidth(70)
        model_layout.addWidget(self._ed_model)
        model_layout.addWidget(self._btn_fetch_models)
        self._ed_temperature = QDoubleSpinBox()
        # Minimum (-0.05) is the special "inherit" value — real temperatures
        # start at 0.0, so anything negative means "use the provider default".
        self._ed_temperature.setRange(-0.05, 2.0)
        self._ed_temperature.setSingleStep(0.05)
        self._ed_temperature.setDecimals(2)
        self._ed_temperature.setSpecialValueText("— domyślna dostawcy")
        self._ed_temperature.setValue(self._ed_temperature.minimum())
        self._ed_temperature.setMaximumWidth(180)
        self._ed_temperature.setToolTip(
            "Temperatura tylko dla tego promptu — niska (0.0–0.3) dla definicji\n"
            "i faktów, wyższa (0.7–1.0) dla przykładowych zdań i zadań kreatywnych.\n"
            "„— domyślna dostawcy” = użyj temperatury z karty dostawcy.\n"
            "Fallback tego promptu również używa tej temperatury."
        )
        self._ed_manual_only = QCheckBox("Tylko na żądanie (pomijaj w batchu i workflow)")
        self._ed_manual_only.setToolTip(
            "Zaznacz, jeśli to pole ma być generowane TYLKO przez jawne\n"
            "wskazanie: PPM na polu w edytorze albo submenu „Generuj zablokowane”\n"
            "w przeglądarce. Pominięte przy „Wszystkie puste”, workflow\n"
            "oraz głównym przycisku AI w edytorze."
        )
        # Fallback (per-prompt override). Empty = inherit provider-level fallback_model.
        self._ed_fallback_provider = QComboBox()
        self._ed_fallback_provider.addItem("— (ten sam dostawca)", "")
        for name, label in PROVIDER_LABELS.items():
            self._ed_fallback_provider.addItem(label, name)
        self._ed_fallback_provider.setToolTip(
            "Dostawca zapasowy uruchamiany gdy główny model zawiedzie.\n"
            "„—” = użyj tego samego dostawcy co główny model."
        )
        fb_model_row = QWidget()
        fb_layout = QHBoxLayout(fb_model_row)
        fb_layout.setContentsMargins(0, 0, 0, 0)
        fb_layout.setSpacing(4)
        self._ed_fallback_model = _filterable_combo()
        self._ed_fallback_model.setMinimumWidth(200)
        self._ed_fallback_model.setToolTip(
            "Model zapasowy uruchamiany gdy główny model zawiedzie (błąd API,\n"
            "rate limit, brak środków, brak treści). Puste = brak fallbacku\n"
            "per-prompt; wtedy używany jest fallback z konfiguracji dostawcy."
        )
        self._btn_fetch_fb_models = QPushButton("Pobierz")
        self._btn_fetch_fb_models.setFixedWidth(70)
        self._btn_fetch_fb_models.setToolTip(
            "Pobiera listę modeli z API dla dostawcy zapasowego."
        )
        fb_layout.addWidget(self._ed_fallback_model)
        fb_layout.addWidget(self._btn_fetch_fb_models)
        form.addRow("Typ notatki:", self._ed_note_type)
        form.addRow("Nazwa zadania:", self._ed_field)
        form.addRow("Pole docelowe:", self._ed_target)
        form.addRow("Dostawca AI:", self._ed_provider)
        form.addRow("Model AI:", model_row)
        form.addRow("Temperatura:", self._ed_temperature)
        form.addRow(self._ed_manual_only)
        form.addRow("Dostawca zapasowy:", self._ed_fallback_provider)
        form.addRow("Model zapasowy:", fb_model_row)
        editor_form_layout.addLayout(form)

        prompt_header = QHBoxLayout()
        prompt_header.addWidget(QLabel("Prompt:"))
        prompt_header.addStretch()
        self._btn_insert_field = QPushButton("Wstaw pole ▾")
        prompt_header.addWidget(self._btn_insert_field)
        self._btn_insert_cond = QPushButton("Wstaw warunek ▾")
        self._btn_insert_cond.setToolTip(
            "Wstawia {% if pole %}…{% else %}…{% endif %}.\n"
            "Zaznaczony tekst zostanie owinięty warunkiem (trafi do gałęzi „if”)."
        )
        prompt_header.addWidget(self._btn_insert_cond)
        self._btn_preview = QPushButton("Podgląd…")
        self._btn_preview.setToolTip(
            "Otwiera okno z finalnym promptem wyrenderowanym na wybranej\n"
            "notatce z kolekcji — z rozstrzygniętymi warunkami {% if %}."
        )
        prompt_header.addWidget(self._btn_preview)
        editor_form_layout.addLayout(prompt_header)

        self._ed_prompt = QTextEdit()
        self._ed_prompt.setAcceptRichText(False)
        self._ed_prompt.setMinimumHeight(200)
        self._highlighter = _TemplateHighlighter(self._ed_prompt.document())
        editor_form_layout.addWidget(self._ed_prompt)

        self._lbl_validation = QLabel("")
        self._lbl_validation.setWordWrap(True)
        self._lbl_validation.setStyleSheet(f"color: {pal['warn_fg']};")
        self._lbl_validation.setVisible(False)
        editor_form_layout.addWidget(self._lbl_validation)

        self._editor_widget.setVisible(False)

        right_layout.addWidget(self._editor_placeholder)
        right_layout.addWidget(self._editor_widget)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        self._list.currentItemChanged.connect(self._on_item_changed)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._btn_add.clicked.connect(self._on_add)
        self._btn_del.clicked.connect(self._on_delete)
        self._btn_up.clicked.connect(lambda: self._on_move(-1))
        self._btn_down.clicked.connect(lambda: self._on_move(1))
        self._ed_note_type.currentTextChanged.connect(self._on_note_type_changed)
        self._ed_provider.currentIndexChanged.connect(self._on_provider_changed)
        self._ed_fallback_provider.currentIndexChanged.connect(self._on_fallback_provider_changed)
        self._ed_model.currentTextChanged.connect(self._validate_prompt)
        self._ed_target.currentTextChanged.connect(self._validate_prompt)
        self._ed_prompt.textChanged.connect(self._validate_prompt)
        self._btn_fetch_models.clicked.connect(self._fetch_models)
        self._btn_fetch_fb_models.clicked.connect(self._fetch_fallback_models)
        self._btn_insert_field.clicked.connect(self._on_insert_field)
        self._btn_insert_cond.clicked.connect(self._on_insert_condition)
        self._btn_preview.clicked.connect(self._on_preview)

        self._rebuild_list()

    # ------------------------------------------------------------------
    # List items & ordering
    # ------------------------------------------------------------------

    def _populate_filter(self) -> None:
        """(Re)fill the note-type filter from the current data, keeping the
        selection if that type still exists."""
        current = self._filter_combo.currentData() if self._filter_combo.count() else None
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem("— wszystkie typy —", None)
        seen: list[str] = []
        for nt, _field in self._data:
            if nt not in seen:
                seen.append(nt)
        for nt in seen:
            self._filter_combo.addItem(nt, nt)
        idx = self._filter_combo.findData(current)
        self._filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._filter_combo.blockSignals(False)

    def _rebuild_list(self, select_key: tuple | None = None) -> None:
        """Render the list from self._data: one non-selectable header per note
        type, then its tasks. Optionally reselect select_key."""
        filter_nt = self._filter_combo.currentData()
        self._list.blockSignals(True)
        self._list.clear()
        last_nt = None
        target_item = None
        for key, entry in self._data.items():
            nt = key[0]
            if filter_nt is not None and nt != filter_nt:
                continue
            if nt != last_nt:
                header = QListWidgetItem(f"──  {nt}  ──")
                # Enabled but not selectable → visible, not clickable, skipped by ▲▼.
                header.setFlags(Qt.ItemFlag.ItemIsEnabled)
                header.setData(Qt.ItemDataRole.UserRole, None)
                f = header.font()
                f.setBold(True)
                header.setFont(f)
                header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._list.addItem(header)
                last_nt = nt
            item = QListWidgetItem(self._item_text(key, entry["prompt"]))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)
            if key == select_key:
                target_item = item
        self._list.blockSignals(False)
        if target_item is not None:
            self._list.setCurrentItem(target_item)
        else:
            self._current_key = None
            self._editor_widget.setVisible(False)
            self._editor_placeholder.setVisible(True)

    def _on_filter_changed(self, _index: int = -1) -> None:
        self._save_current_to_data(self._list.currentItem())
        self._rebuild_list(select_key=self._current_key)

    def _deps_for(self, key: tuple, prompt: str) -> list[str]:
        """Targets of *other* tasks of the same note type used in this prompt."""
        nt = key[0]
        other_targets = {
            entry["target"]
            for other_key, entry in self._data.items()
            if other_key != key and other_key[0] == nt and entry["target"]
        }
        used = {m.strip() for m in _VAR_RE.findall(prompt)}
        used |= {m.strip() for m in _IF_RE.findall(prompt)}
        return sorted(used & other_targets)

    def _item_text(self, key: tuple, prompt: str) -> str:
        text = f"{key[0]}\n→ {key[1]}"
        deps = self._deps_for(key, prompt)
        if deps:
            text += f"   (zależy od: {', '.join(deps)})"
        return text

    def _on_move(self, delta: int) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key is None:  # nagłówek grupy
            return
        self._save_current_to_data(item)
        keys = list(self._data.keys())
        i = keys.index(key)
        # Reorder within the same note type only — generation order matters
        # per note type (dependent fields), and groups stay contiguous.
        j = i + delta
        while 0 <= j < len(keys) and keys[j][0] != key[0]:
            j += delta
        if not (0 <= j < len(keys)) or keys[j][0] != key[0]:
            return
        keys[i], keys[j] = keys[j], keys[i]
        # Rebuild dict in the new order — apply() and dependency resolution
        # both follow this order.
        self._data = {k: self._data[k] for k in keys}
        self._rebuild_list(select_key=key)

    # ------------------------------------------------------------------
    # Editor state
    # ------------------------------------------------------------------

    def _save_current_to_data(self, list_item=None) -> None:
        if self._current_key is None:
            return
        old_key = self._current_key
        new_nt = self._ed_note_type.currentText().strip()
        new_field = self._ed_field.text().strip()
        new_key = (new_nt, new_field)

        entry = {
            "target":      self._ed_target.currentText().strip(),
            "provider":    self._ed_provider.currentData() or "openai",
            "model":       self._ed_model.currentText().strip(),
            "prompt":      self._ed_prompt.toPlainText(),
            "manual_only": self._ed_manual_only.isChecked(),
            "fallback_provider": self._ed_fallback_provider.currentData() or "",
            "fallback_model":    self._ed_fallback_model.currentText().strip(),
            # Negative = the special "inherit provider default" spinbox value.
            "temperature": (
                round(self._ed_temperature.value(), 2)
                if self._ed_temperature.value() >= 0 else None
            ),
        }

        if new_key != old_key:
            # Rebuild in place so renaming keeps the entry's position —
            # generation order follows note_types key order (dependent fields).
            self._data = {
                (new_key if k == old_key else k): (entry if k == old_key else v)
                for k, v in self._data.items()
            }
            self._current_key = new_key
            if list_item:
                list_item.setText(self._item_text(new_key, entry["prompt"]))
                list_item.setData(Qt.ItemDataRole.UserRole, new_key)
        else:
            self._data[old_key] = entry
            if list_item:
                list_item.setText(self._item_text(old_key, entry["prompt"]))

    def _load_key_to_editor(self, key: tuple) -> None:
        self._current_key = key
        entry = self._data[key]
        self._ed_note_type.setCurrentText(key[0])
        self._ed_field.setText(key[1])
        self._ed_target.setCurrentText(entry["target"])
        self._ed_provider.blockSignals(True)
        idx = self._ed_provider.findData(entry["provider"])
        self._ed_provider.setCurrentIndex(idx if idx >= 0 else 0)
        self._ed_provider.blockSignals(False)
        self._set_model_choices(entry["provider"], self._ed_model, entry.get("model", ""))
        self._ed_fallback_provider.blockSignals(True)
        fb_idx = self._ed_fallback_provider.findData(entry.get("fallback_provider", ""))
        self._ed_fallback_provider.setCurrentIndex(fb_idx if fb_idx >= 0 else 0)
        self._ed_fallback_provider.blockSignals(False)
        self._set_model_choices(
            entry.get("fallback_provider", "") or entry["provider"],
            self._ed_fallback_model,
            entry.get("fallback_model", ""),
        )
        temp = entry.get("temperature")
        self._ed_temperature.setValue(
            temp if isinstance(temp, (int, float))
            else self._ed_temperature.minimum()
        )
        self._ed_manual_only.setChecked(entry.get("manual_only", False))
        self._ed_prompt.setPlainText(entry["prompt"])
        self._editor_placeholder.setVisible(False)
        self._editor_widget.setVisible(True)
        self._validate_prompt()

    # --- pomoc kontekstowa: pola, wstawianie, walidacja ---

    def _on_note_type_changed(self, _text: str = "") -> None:
        fields = get_fields_for_note_type(self._ed_note_type.currentText().strip())
        current_target = self._ed_target.currentText()
        self._ed_target.blockSignals(True)
        self._ed_target.clear()
        self._ed_target.addItems(fields)
        self._ed_target.setCurrentText(current_target)
        self._ed_target.blockSignals(False)
        self._validate_prompt()

    def _provider_values(self, provider: str) -> dict:
        values = self._provider_settings(provider)
        return values if isinstance(values, dict) else {}

    def _set_model_choices(self, provider: str, combo: QComboBox,
                           current: str = "") -> None:
        provider_values = self._provider_values(provider)
        default = str(provider_values.get("model") or "").strip()
        selected = str(current or "").strip() or default
        choices = list(
            self._model_options.get(provider)
            or provider_values.get("models")
            or provider_values.get("cached_models")
            or []
        )
        for model in (default, selected):
            if model and model not in choices:
                choices.insert(0, model)
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(choices)
        combo.setCurrentText(selected)
        combo.blockSignals(False)
        if combo is self._ed_model:
            self._validate_prompt()

    def _on_provider_changed(self, _index: int = -1) -> None:
        self._set_model_choices(
            self._ed_provider.currentData() or "openai", self._ed_model
        )

    def _on_fallback_provider_changed(self, _index: int = -1) -> None:
        fb_provider = self._ed_fallback_provider.currentData() or ""
        main_provider = self._ed_provider.currentData() or "openai"
        self._set_model_choices(
            fb_provider or main_provider, self._ed_fallback_model
        )

    def _fetch_models(self) -> None:
        provider = self._ed_provider.currentData() or "openai"
        self._fetch_models_for_combo(provider, self._ed_model, self._btn_fetch_models)

    def _fetch_fallback_models(self) -> None:
        fb_provider = self._ed_fallback_provider.currentData() or ""
        provider = fb_provider or self._ed_provider.currentData() or "openai"
        self._fetch_models_for_combo(
            provider, self._ed_fallback_model, self._btn_fetch_fb_models
        )

    def _fetch_models_for_combo(self, provider: str, combo: QComboBox,
                                btn: QPushButton) -> None:
        api_key = str(self._provider_values(provider).get("api_key", "")).strip()
        current = combo.currentText()
        btn.setEnabled(False)
        btn.setText("...")

        def task():
            from ..ai_generator.providers.model_discovery import fetch_models
            return fetch_models(provider, api_key, force=True)

        def on_done(fut):
            try:
                models = fut.result()
            except Exception:
                models = []
            try:
                btn.setEnabled(True)
                btn.setText("Pobierz")
                if not models:
                    showWarning(
                        f"Nie udało się pobrać modeli dla {provider}.\n"
                        "Sprawdź klucz API i połączenie z internetem."
                    )
                    return
                self._model_options[provider] = models
                # Refresh whichever combo matches this provider
                if (self._ed_provider.currentData() or "openai") == provider:
                    self._set_model_choices(provider, self._ed_model, self._ed_model.currentText())
                fb_provider_data = self._ed_fallback_provider.currentData() or ""
                fb_name = fb_provider_data or self._ed_provider.currentData() or "openai"
                if fb_name == provider:
                    self._set_model_choices(provider, self._ed_fallback_model, self._ed_fallback_model.currentText())
            except RuntimeError:
                pass  # dialog was closed while fetching

        mw.taskman.run_in_background(task, on_done)

    def _known_prompt_fields(self) -> set[str]:
        """Fields usable in the prompt: note type fields + targets of earlier tasks."""
        nt = self._ed_note_type.currentText().strip()
        known = set(get_fields_for_note_type(nt))
        for key, entry in self._data.items():
            if key == self._current_key:
                break
            if key[0] == nt and entry["target"]:
                known.add(entry["target"])
        return known

    def _later_task_targets(self) -> set[str]:
        """Targets generated by tasks *after* the current one (same note type)."""
        nt = self._ed_note_type.currentText().strip()
        seen_current = False
        later: set[str] = set()
        for key, entry in self._data.items():
            if key == self._current_key:
                seen_current = True
                continue
            if seen_current and key[0] == nt and entry["target"]:
                later.add(entry["target"])
        return later

    def _exec_field_menu(self, button: QPushButton, callback) -> None:
        names = sorted(self._known_prompt_fields())
        menu = QMenu(self)
        if not names:
            menu.addAction("(brak pól — sprawdź typ notatki)").setEnabled(False)
        for name in names:
            action = menu.addAction(name)
            action.triggered.connect(lambda _=False, n=name: callback(n))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _on_insert_field(self) -> None:
        self._exec_field_menu(self._btn_insert_field, self._insert_placeholder)

    def _on_insert_condition(self) -> None:
        self._exec_field_menu(self._btn_insert_cond, self._insert_condition)

    def _insert_placeholder(self, name: str) -> None:
        self._ed_prompt.textCursor().insertText("{{" + name + "}}")
        self._ed_prompt.setFocus()

    def _insert_condition(self, name: str) -> None:
        cursor = self._ed_prompt.textCursor()
        # QTextCursor.selectedText() uses U+2029 as the line separator
        selected = cursor.selectedText().replace("\u2029", "\n")
        prefix = "{% if " + name + " %}"
        start = cursor.selectionStart()

        cursor.insertText(prefix + selected + "{% else %}{% endif %}")
        if selected:
            # kursor w pustej gałęzi else
            cursor.setPosition(start + len(prefix + selected + "{% else %}"))
        else:
            # kursor w pustej gałęzi if
            cursor.setPosition(start + len(prefix))
        self._ed_prompt.setTextCursor(cursor)
        self._ed_prompt.setFocus()

    def _validate_prompt(self, *_args) -> None:
        prompt = self._ed_prompt.toPlainText()
        problems: list[str] = template_structure_problems(prompt)
        if not self._ed_model.currentText().strip():
            problems.append("Wybierz model AI dla tego promptu.")

        # sprawdzanie istnienia pól wymaga dostępu do kolekcji
        if self._note_type_names:
            nt = self._ed_note_type.currentText().strip()

            if nt and nt not in self._note_type_names:
                problems.append(f"Typ notatki „{nt}” nie istnieje w kolekcji.")
                self._highlighter.set_known_fields(None)
            else:
                nt_fields = set(get_fields_for_note_type(nt))
                target = self._ed_target.currentText().strip()
                if target and target not in nt_fields:
                    problems.append(f"Pole docelowe „{target}” nie istnieje w typie notatki.")

                known = self._known_prompt_fields()
                self._highlighter.set_known_fields(known)
                used = [m.strip() for m in _VAR_RE.findall(prompt)]
                used += [m.strip() for m in _IF_RE.findall(prompt)]
                unknown = sorted({u for u in used if u and u not in known})
                if unknown:
                    problems.append(
                        "Nieznane pola w prompcie: "
                        + ", ".join("{{" + u + "}}" for u in unknown)
                    )

                too_late = sorted(set(used) & self._later_task_targets())
                if too_late:
                    problems.append(
                        "Pole "
                        + ", ".join(f"„{t}”" for t in too_late)
                        + " jest generowane przez późniejsze zadanie — przesuń je "
                        "wyżej (▲), jeśli prompt ma użyć świeżo wygenerowanej wartości."
                    )
        else:
            self._highlighter.set_known_fields(None)

        self._lbl_validation.setText("\n".join("⚠ " + p for p in problems))
        self._lbl_validation.setVisible(bool(problems))

        # keep dependency hint on the list item in sync
        item = self._list.currentItem()
        if item is not None and self._current_key is not None:
            item.setText(self._item_text(self._current_key, prompt))

    # ------------------------------------------------------------------
    # Preview on a sample note
    # ------------------------------------------------------------------

    def _on_preview(self) -> None:
        dlg = PromptPreviewDialog(
            self,
            note_type=self._ed_note_type.currentText().strip(),
            prompt=self._ed_prompt.toPlainText(),
        )
        dlg.exec()

    # ------------------------------------------------------------------
    # List events, add/delete
    # ------------------------------------------------------------------

    def _on_item_changed(self, current, previous) -> None:
        if previous is not None:
            self._save_current_to_data(previous)
        if current is None:
            self._editor_widget.setVisible(False)
            self._editor_placeholder.setVisible(True)
            self._current_key = None
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key is None:
            return  # header — visible but not a real entry
        self._load_key_to_editor(key)

    def _on_add(self) -> None:
        default_note_type = (
            self._current_key[0] if self._current_key
            else self._filter_combo.currentData()
            or (self._note_type_names[0] if self._note_type_names else "")
        )
        if not self._note_type_names:
            showWarning("Brak typów notatek w kolekcji.")
            return
        if len(self._note_type_names) == 1:
            note_type = self._note_type_names[0]
        else:
            note_type, ok = QInputDialog.getItem(
                self,
                "Nowy prompt",
                "Typ notatki:",
                self._note_type_names,
                (
                    self._note_type_names.index(default_note_type)
                    if default_note_type in self._note_type_names else 0
                ),
                False,
            )
            if not ok:
                return
        base_name = "nowy_prompt"
        key = (note_type, base_name)
        i = 1
        while key in self._data:
            key = (note_type, f"{base_name}_{i}")
            i += 1

        # Wstaw zaraz za ostatnim zadaniem tego samego typu, żeby lista
        # pozostała pogrupowana (a nie doklejona na sam koniec).
        keys = list(self._data.keys())
        insert_at = len(keys)
        for idx, k in enumerate(keys):
            if k[0] == key[0]:
                insert_at = idx + 1
        keys.insert(insert_at, key)
        provider = self._default_provider
        provider_cfg = self._provider_settings(provider) or {}
        self._data[key] = {
            "target": "",
            "provider": provider,
            "model": provider_cfg.get("model", ""),
            "prompt": "",
            "manual_only": False,
        }
        self._data = {k: self._data[k] for k in keys}
        self._populate_filter()
        # Pokaż grupę nowego wpisu, żeby nie zniknął pod aktywnym filtrem.
        self._filter_combo.blockSignals(True)
        self._filter_combo.setCurrentIndex(self._filter_combo.findData(key[0]))
        self._filter_combo.blockSignals(False)
        self._rebuild_list(select_key=key)

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key is None:  # nagłówek grupy — nic do usunięcia
            return
        self._current_key = None
        keys = list(self._data.keys())
        i = keys.index(key)
        del self._data[key]
        self._populate_filter()
        # Zaznacz sąsiedni wpis (jak wcześniej); _rebuild_list pokaże placeholder
        # gdy nic nie zostało / sąsiad jest poza filtrem.
        remaining = list(self._data.keys())
        neighbor = remaining[min(i, len(remaining) - 1)] if remaining else None
        self._rebuild_list(select_key=neighbor)

    def apply(self, cfg: dict) -> None:
        self._save_current_to_data(self._list.currentItem())

        cfg.setdefault("ai_generator", {})
        cfg["ai_generator"].setdefault("note_types", {})

        note_types: dict = {}
        for (nt_name, field_name), entry in self._data.items():
            note_types.setdefault(nt_name, {})
            field_cfg: dict = {
                "target":   entry["target"],
                "provider": entry["provider"],
                "model":    entry["model"],
                "prompt":   entry["prompt"],
            }
            if entry.get("manual_only"):
                field_cfg["manual_only"] = True
            fb_provider = entry.get("fallback_provider", "")
            fb_model = entry.get("fallback_model", "")
            if fb_provider:
                field_cfg["fallback_provider"] = fb_provider
            if fb_model:
                field_cfg["fallback_model"] = fb_model
            if entry.get("temperature") is not None:
                field_cfg["temperature"] = entry["temperature"]
            note_types[nt_name][field_name] = field_cfg
        cfg["ai_generator"]["note_types"] = note_types
