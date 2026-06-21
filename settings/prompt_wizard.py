"""Single-page "Nowe zadanie AI" dialog for the Prompts tab.

Collects the mechanical part of a new prompt entry — note type, target
field, provider — in one compact form. Starter templates are optional:
the "Szablon startowy" combo defaults to an empty prompt; picking a
template reveals field-mapping rows (and the {% if %} checkbox for the
examples template), so template syntax is never written by hand.
"""

from aqt.qt import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QComboBox,
    QDialogButtonBox, QCheckBox, QWidget,
)

from ..common.ui import hint_label, palette, get_fields_for_note_type
from ..ai_generator.providers import PROVIDER_LABELS
from .prompt_templates import TEMPLATES, guess_field, build_prompt


def _editable_combo(items: list[str], current: str = "") -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(items)
    combo.setCurrentText(current)
    return combo


class NewPromptDialog(QDialog):
    """Collects (note_type, task_name, target, provider, prompt) in one form."""

    def __init__(self, parent, note_type_names: list[str],
                 default_note_type: str = "", default_provider: str = "openai"):
        super().__init__(parent)
        self.setWindowTitle("Nowe zadanie AI")
        self.setMinimumWidth(460)
        self._note_type_names = note_type_names
        self._param_combos: dict[str, QComboBox] = {}
        self._cond_check: QCheckBox | None = None
        self._cond_combo: QComboBox | None = None

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        current_nt = default_note_type or (
            note_type_names[0] if note_type_names else ""
        )
        self._note_type = _editable_combo(note_type_names, current_nt)
        form.addRow("Typ notatki:", self._note_type)

        self._target = _editable_combo(get_fields_for_note_type(current_nt))
        self._target.setCurrentText("")
        self._target.setToolTip("Pole, do którego AI wpisze wynik.")
        form.addRow("Pole docelowe (wynik AI):", self._target)

        self._provider = QComboBox()
        for key, label in PROVIDER_LABELS.items():
            self._provider.addItem(label, key)
        idx = self._provider.findData(default_provider)
        if idx >= 0:
            self._provider.setCurrentIndex(idx)
        form.addRow("Dostawca AI:", self._provider)

        # "Pusty prompt" first — the default path adds a clean entry and the
        # actual prompt is written in the editor. Templates are an offer for
        # users who don't yet know what a good flashcard prompt looks like.
        self._template = QComboBox()
        self._template.addItem("Pusty prompt — napiszę własny", "custom")
        for tpl in TEMPLATES:
            if tpl["id"] != "custom":
                self._template.addItem(f"Szablon: {tpl['name']}", tpl["id"])
        form.addRow("Szablon startowy:", self._template)

        self._manual_only = QCheckBox("Tylko na żądanie (pomijaj w batchu i workflow)")
        self._manual_only.setToolTip(
            "Zaznacz, jeśli to pole ma być generowane TYLKO przez jawne\n"
            "wskazanie: PPM na polu w edytorze albo submenu „Generuj zablokowane”\n"
            "w przeglądarce. Pominięte przy „Wszystkie puste”, workflow\n"
            "oraz głównym przycisku AI w edytorze."
        )
        form.addRow(self._manual_only)

        layout.addLayout(form)

        self._tpl_desc = hint_label("")
        self._tpl_desc.setVisible(False)
        layout.addWidget(self._tpl_desc)

        self._mapping_host = QWidget()
        self._mapping_form = QFormLayout(self._mapping_host)
        self._mapping_form.setContentsMargins(0, 0, 0, 0)
        self._mapping_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        layout.addWidget(self._mapping_host)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {palette()['warn_fg']};")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Dodaj")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._note_type.currentTextChanged.connect(self._on_note_type_changed)
        self._template.currentIndexChanged.connect(
            lambda _i: self._rebuild_mapping()
        )
        self._rebuild_mapping()

    # ------------------------------------------------------------------
    # Dynamic parts
    # ------------------------------------------------------------------

    def _fields(self) -> list[str]:
        return get_fields_for_note_type(self._note_type.currentText().strip())

    def _selected_template(self) -> dict:
        tpl_id = self._template.currentData() or "custom"
        return next(t for t in TEMPLATES if t["id"] == tpl_id)

    def _on_note_type_changed(self, _text: str = "") -> None:
        fields = self._fields()
        current_target = self._target.currentText()
        self._target.blockSignals(True)
        self._target.clear()
        self._target.addItems(fields)
        self._target.setCurrentText(current_target)
        self._target.blockSignals(False)
        self._rebuild_mapping()

    def _rebuild_mapping(self) -> None:
        while self._mapping_form.rowCount():
            self._mapping_form.removeRow(0)
        self._param_combos = {}
        self._cond_check = None
        self._cond_combo = None
        self._error.setVisible(False)

        tpl = self._selected_template()
        if tpl["id"] == "custom":
            self._tpl_desc.setVisible(False)
            self._mapping_host.setVisible(False)
            return

        self._tpl_desc.setText(
            tpl["desc"] + " Wskaż, z których pól notatki szablon ma korzystać:"
        )
        self._tpl_desc.setVisible(True)
        self._mapping_host.setVisible(True)

        fields = self._fields()

        # Suggest a target matching the template when the user hasn't picked one.
        if not self._target.currentText().strip():
            self._target.setCurrentText(guess_field(tpl["target_hints"], fields))

        for key, label, hints in tpl["params"]:
            combo = _editable_combo(fields, guess_field(hints, fields))
            self._param_combos[key] = combo
            self._mapping_form.addRow(label + ":", combo)

        cond = tpl.get("conditional")
        if cond:
            self._cond_check = QCheckBox(cond["label"])
            self._cond_check.setChecked(True)
            self._cond_check.setToolTip(
                "Dialog sam wygeneruje blok {% if %}…{% else %}…{% endif %} — "
                "gdy pole jest wypełnione, AI dostanie pełniejszy kontekst."
            )
            self._mapping_form.addRow(self._cond_check)
            ckey, clabel, chints = cond["param"]
            self._cond_combo = _editable_combo(fields, guess_field(chints, fields))
            self._mapping_form.addRow(clabel + ":", self._cond_combo)
            self._cond_check.toggled.connect(self._cond_combo.setEnabled)

    # ------------------------------------------------------------------
    # Accept & result
    # ------------------------------------------------------------------

    def _show_error(self, text: str) -> None:
        self._error.setText("⚠ " + text)
        self._error.setVisible(True)

    def _on_accept(self) -> None:
        tpl = self._selected_template()
        if not self._note_type.currentText().strip():
            self._show_error("Podaj typ notatki.")
            return
        if not self._target.currentText().strip():
            self._show_error("Wybierz pole docelowe.")
            return
        for key, label, _hints in tpl["params"]:
            if not self._param_combos[key].currentText().strip():
                self._show_error(f"Wskaż pole dla „{label}”.")
                return
        use_cond = bool(self._cond_check and self._cond_check.isChecked())
        if use_cond and not self._cond_combo.currentText().strip():
            self._show_error("Wskaż pole z definicją albo odznacz warunek.")
            return
        self.accept()

    def entry(self) -> dict:
        """Return the configured prompt entry (valid after accept())."""
        tpl = self._selected_template()
        mapping = {
            key: combo.currentText().strip()
            for key, combo in self._param_combos.items()
        }
        use_cond = bool(self._cond_check and self._cond_check.isChecked())
        if tpl.get("conditional") and self._cond_combo is not None:
            mapping[tpl["conditional"]["param"][0]] = (
                self._cond_combo.currentText().strip()
            )
        target = self._target.currentText().strip()
        return {
            "note_type": self._note_type.currentText().strip(),
            "task_name": target,
            "target": target,
            "provider": self._provider.currentData() or "openai",
            "prompt": build_prompt(tpl, mapping, use_cond),
            "manual_only": self._manual_only.isChecked(),
        }
