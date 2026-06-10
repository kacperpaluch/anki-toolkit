"""Prompts tab — two-panel editor for note_type→field prompts."""

import re

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter,
    QPushButton, Qt, QComboBox, QMenu,
)

from ..common.ui import _expanding_line_edit, get_note_type_names, get_fields_for_note_type
from ..ai_generator.template_engine import template_structure_problems

_PROVIDER_NAMES = ["google", "cometapi", "openai", "openrouter", "anthropic", "mistral", "opencode_go"]

_VAR_RE = re.compile(r'{{(.*?)}}')
_IF_RE = re.compile(r'{%\s*if\s+([^%]+)%}')


def _editable_combo(items: list[str]) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(items)
    combo.setCurrentText("")
    return combo


class PromptsTab(QWidget):
    """Two-panel editor: list of note_type→field on left, prompt editor on right."""

    def __init__(self, cfg: dict):
        super().__init__()
        self._data: dict = {}
        self._current_key: tuple | None = None

        note_types = cfg.get("ai_generator", {}).get("note_types", {})
        for nt_name, fields in note_types.items():
            for field_name, field_cfg in fields.items():
                key = (nt_name, field_name)
                self._data[key] = {
                    "target":   field_cfg.get("target", field_name),
                    "provider": field_cfg.get("provider", "openai"),
                    "prompt":   field_cfg.get("prompt", ""),
                }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 4, 8)

        left_layout.addWidget(QLabel("Typ notatki → zadanie:"))
        self._list = QListWidget()
        self._list.setMinimumWidth(160)
        self._list.setMaximumWidth(240)

        for nt_name, field_name in sorted(self._data.keys()):
            item = QListWidgetItem(f"{nt_name}\n→ {field_name}")
            item.setData(Qt.ItemDataRole.UserRole, (nt_name, field_name))
            self._list.addItem(item)

        left_layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("+ Dodaj")
        self._btn_del = QPushButton("Usuń")
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_del)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 8, 8, 8)

        self._editor_placeholder = QLabel("Wybierz pole z listy po lewej.")
        self._editor_placeholder.setStyleSheet("color: gray;")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._editor_widget = QWidget()
        editor_form_layout = QVBoxLayout(self._editor_widget)
        editor_form_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._note_type_names = get_note_type_names()
        self._ed_note_type = _editable_combo(self._note_type_names)
        self._ed_field = _expanding_line_edit()
        self._ed_target = _editable_combo([])
        self._ed_provider = QComboBox()
        self._ed_provider.addItems(_PROVIDER_NAMES)
        form.addRow("Typ notatki:", self._ed_note_type)
        form.addRow("Nazwa zadania:", self._ed_field)
        form.addRow("Pole docelowe:", self._ed_target)
        form.addRow("Provider:", self._ed_provider)
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
        editor_form_layout.addLayout(prompt_header)

        self._ed_prompt = QTextEdit()
        self._ed_prompt.setAcceptRichText(False)
        self._ed_prompt.setMinimumHeight(200)
        editor_form_layout.addWidget(self._ed_prompt)

        self._lbl_validation = QLabel("")
        self._lbl_validation.setWordWrap(True)
        self._lbl_validation.setStyleSheet("color: #cc7700;")
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
        self._btn_add.clicked.connect(self._on_add)
        self._btn_del.clicked.connect(self._on_delete)
        self._ed_note_type.currentTextChanged.connect(self._on_note_type_changed)
        self._ed_target.currentTextChanged.connect(self._validate_prompt)
        self._ed_prompt.textChanged.connect(self._validate_prompt)
        self._btn_insert_field.clicked.connect(self._on_insert_field)
        self._btn_insert_cond.clicked.connect(self._on_insert_condition)

    def _save_current_to_data(self, list_item=None) -> None:
        if self._current_key is None:
            return
        old_key = self._current_key
        new_nt = self._ed_note_type.currentText().strip()
        new_field = self._ed_field.text().strip()
        new_key = (new_nt, new_field)

        entry = {
            "target":   self._ed_target.currentText().strip(),
            "provider": self._ed_provider.currentText(),
            "prompt":   self._ed_prompt.toPlainText(),
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
                list_item.setText(f"{new_nt}\n→ {new_field}")
                list_item.setData(Qt.ItemDataRole.UserRole, new_key)
        else:
            self._data[old_key] = entry

    def _load_key_to_editor(self, key: tuple) -> None:
        self._current_key = key
        entry = self._data[key]
        self._ed_note_type.setCurrentText(key[0])
        self._ed_field.setText(key[1])
        self._ed_target.setCurrentText(entry["target"])
        idx = (
            _PROVIDER_NAMES.index(entry["provider"])
            if entry["provider"] in _PROVIDER_NAMES
            else 0
        )
        self._ed_provider.setCurrentIndex(idx)
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

        # sprawdzanie istnienia pól wymaga dostępu do kolekcji
        if self._note_type_names:
            nt = self._ed_note_type.currentText().strip()

            if nt and nt not in self._note_type_names:
                problems.append(f"Typ notatki „{nt}” nie istnieje w kolekcji.")
            else:
                nt_fields = set(get_fields_for_note_type(nt))
                target = self._ed_target.currentText().strip()
                if target and target not in nt_fields:
                    problems.append(f"Pole docelowe „{target}” nie istnieje w typie notatki.")

                known = self._known_prompt_fields()
                used = [m.strip() for m in _VAR_RE.findall(prompt)]
                used += [m.strip() for m in _IF_RE.findall(prompt)]
                unknown = sorted({u for u in used if u and u not in known})
                if unknown:
                    problems.append(
                        "Nieznane pola w prompcie: "
                        + ", ".join("{{" + u + "}}" for u in unknown)
                    )

        self._lbl_validation.setText("\n".join("⚠ " + p for p in problems))
        self._lbl_validation.setVisible(bool(problems))

    def _on_item_changed(self, current, previous) -> None:
        if previous is not None:
            self._save_current_to_data(previous)
        if current is None:
            self._editor_widget.setVisible(False)
            self._editor_placeholder.setVisible(True)
            self._current_key = None
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        self._load_key_to_editor(key)

    def _on_add(self) -> None:
        base_nt = "angielski"
        base_field = "nowe_pole"
        key = (base_nt, base_field)
        i = 1
        while key in self._data:
            key = (base_nt, f"{base_field}_{i}")
            i += 1

        self._data[key] = {"target": key[1], "provider": "openai", "prompt": ""}
        item = QListWidgetItem(f"{key[0]}\n→ {key[1]}")
        item.setData(Qt.ItemDataRole.UserRole, key)
        self._list.addItem(item)
        self._list.setCurrentItem(item)

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self._current_key = None
        del self._data[key]
        self._list.takeItem(self._list.row(item))
        self._editor_widget.setVisible(False)
        self._editor_placeholder.setVisible(True)

    def apply(self, cfg: dict) -> None:
        self._save_current_to_data(self._list.currentItem())

        cfg.setdefault("ai_generator", {})
        cfg["ai_generator"].setdefault("note_types", {})

        note_types: dict = {}
        for (nt_name, field_name), entry in self._data.items():
            note_types.setdefault(nt_name, {})
            note_types[nt_name][field_name] = {
                "target":   entry["target"],
                "provider": entry["provider"],
                "prompt":   entry["prompt"],
            }
        cfg["ai_generator"]["note_types"] = note_types
