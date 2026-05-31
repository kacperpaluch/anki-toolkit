"""Prompts tab — two-panel editor for note_type→field prompts."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter,
    QPushButton, Qt, QComboBox,
)

from ..common.ui import _expanding_line_edit

_PROVIDER_NAMES = ["google", "cometapi", "openai", "openrouter", "anthropic", "mistral", "opencode_go"]


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
        self._ed_note_type = _expanding_line_edit()
        self._ed_field = _expanding_line_edit()
        self._ed_target = _expanding_line_edit()
        self._ed_provider = QComboBox()
        self._ed_provider.addItems(_PROVIDER_NAMES)
        form.addRow("Typ notatki:", self._ed_note_type)
        form.addRow("Nazwa zadania:", self._ed_field)
        form.addRow("Pole docelowe:", self._ed_target)
        form.addRow("Provider:", self._ed_provider)
        editor_form_layout.addLayout(form)

        editor_form_layout.addWidget(QLabel("Prompt:"))
        self._ed_prompt = QTextEdit()
        self._ed_prompt.setAcceptRichText(False)
        self._ed_prompt.setMinimumHeight(200)
        editor_form_layout.addWidget(self._ed_prompt)

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

    def _save_current_to_data(self, list_item=None) -> None:
        if self._current_key is None:
            return
        old_key = self._current_key
        new_nt = self._ed_note_type.text().strip()
        new_field = self._ed_field.text().strip()
        new_key = (new_nt, new_field)

        entry = {
            "target":   self._ed_target.text().strip(),
            "provider": self._ed_provider.currentText(),
            "prompt":   self._ed_prompt.toPlainText(),
        }

        if new_key != old_key:
            del self._data[old_key]
            self._data[new_key] = entry
            self._current_key = new_key
            if list_item:
                list_item.setText(f"{new_nt}\n→ {new_field}")
                list_item.setData(Qt.ItemDataRole.UserRole, new_key)
        else:
            self._data[old_key] = entry

    def _load_key_to_editor(self, key: tuple) -> None:
        self._current_key = key
        entry = self._data[key]
        self._ed_note_type.setText(key[0])
        self._ed_field.setText(key[1])
        self._ed_target.setText(entry["target"])
        idx = (
            _PROVIDER_NAMES.index(entry["provider"])
            if entry["provider"] in _PROVIDER_NAMES
            else 0
        )
        self._ed_provider.setCurrentIndex(idx)
        self._ed_prompt.setPlainText(entry["prompt"])
        self._editor_placeholder.setVisible(False)
        self._editor_widget.setVisible(True)

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
