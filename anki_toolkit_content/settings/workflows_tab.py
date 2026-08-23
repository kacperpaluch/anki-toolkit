"""Workflows tab — manage named workflows and right-click menu visibility.

Each workflow is one entry in the browser/editor right-click menu. A workflow
is an ordered list of steps; a step is {module, action, ...params}. This tab is
the only UI that writes config["workflows"] and config["context_menu"].
"""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QPushButton, QListWidget, QListWidgetItem, QCheckBox, QDialog,
    QDialogButtonBox, QComboBox, QLineEdit,
)
from aqt.utils import showWarning

from ..common.ui import _expanding_line_edit, _scrollable, hint_label
from ..ai_generator.workflow import DEFAULT_CONTEXT_MENU

_CONTEXT_LABELS = {
    "dictionary": "Pobierz wymowę (słowniki)",
    "tts": "TTS (zadania audio)",
    "ai_fields": "Generuj pola (AI)",
    "ai_blocked": "Generuj zablokowane (AI)",
    "field_splitter": "Rozdziel pole",
}

# Fallback dictionary buttons if none configured yet (mirrors config.json).
_DEFAULT_DICT_BUTTONS = [
    {"dictionaries": ["diki_uk", "diki_us"], "label": "Diki", "enabled": True},
    {"dictionaries": ["oxford_uk", "oxford_us"], "label": "Oxford", "enabled": True},
    {"dictionaries": ["cambridge_uk", "cambridge_us"], "label": "Cambridge", "enabled": False},
    {"dictionaries": ["longman_uk", "longman_us"], "label": "Longman", "enabled": False},
]


# ---------------------------------------------------------------------------
# Step label rendering
# ---------------------------------------------------------------------------

def _step_label(step: dict) -> str:
    mod = step.get("module", "?")
    if mod == "ai":
        fields = step.get("fields", "empty")
        if fields == "manual":
            return "AI: zablokowane pola"
        if isinstance(fields, list):
            return f"AI: pola: {', '.join(fields)}"
        if isinstance(fields, str) and fields not in ("", "empty"):
            return f"AI: pole: {fields}"
        return "AI: wszystkie puste pola"
    if mod == "dictionary":
        dicts = step.get("dicts", [])
        return f"Słownik: {', '.join(dicts)}" if dicts else "Słownik: (wszystkie)"
    if mod == "tts":
        return "TTS: wygeneruj audio"
    if mod == "field_splitter":
        return "Rozdziel pole źródłowe → docelowe"
    return f"{mod}/{step.get('action', '?')}"


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

def _pick_dicts(parent, dict_buttons: list[dict]) -> list[str]:
    """Checkbox dialog for available dictionaries. Returns chosen dict IDs
    (empty list if cancelled or nothing selected — caller should skip then,
    since a dictionary step with no dicts does nothing)."""
    buttons = dict_buttons or _DEFAULT_DICT_BUTTONS

    dlg = QDialog(parent)
    dlg.setWindowTitle("Wybierz słowniki")
    dlg.setMinimumWidth(300)
    layout = QVBoxLayout(dlg)
    layout.addWidget(hint_label("Zaznacz słowniki dla tego kroku."))

    checks = []
    for btn in buttons:
        cb = QCheckBox(btn.get("label", "?"))
        cb.setChecked(btn.get("enabled", False))
        cb.dict_ids = btn.get("dictionaries", [])
        checks.append(cb)
        layout.addWidget(cb)

    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    layout.addWidget(box)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return []
    dicts: list[str] = []
    for cb in checks:
        if cb.isChecked():
            dicts.extend(cb.dict_ids)
    return dicts


def _pick_ai_fields(parent, step: dict | None) -> dict | None:
    """Dialog to choose which fields an AI step targets. Returns the AI step
    dict, or None if cancelled."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Krok AI — które pola")
    dlg.setMinimumWidth(360)
    layout = QVBoxLayout(dlg)
    form = QFormLayout()

    mode = QComboBox()
    mode.addItem("Wszystkie puste pola", "empty")
    mode.addItem("Zablokowane pola (manual_only)", "manual")
    mode.addItem("Konkretne pola…", "specific")
    fields_edit = _expanding_line_edit("")
    fields_edit.setPlaceholderText("np. p1-nauka, p2-nauka, p3-nauka")

    cur = step.get("fields", "empty") if step else "empty"
    if cur == "manual":
        mode.setCurrentIndex(1)
    elif isinstance(cur, (list, str)) and cur not in ("", "empty"):
        mode.setCurrentIndex(2)
        fields_edit.setText(", ".join(cur) if isinstance(cur, list) else cur)

    def _sync():
        fields_edit.setEnabled(mode.currentData() == "specific")
    mode.currentIndexChanged.connect(_sync)
    _sync()

    form.addRow("Pola:", mode)
    form.addRow("Lista pól:", fields_edit)
    layout.addLayout(form)

    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    layout.addWidget(box)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    choice = mode.currentData()
    out = {"module": "ai", "action": "generate"}
    if choice == "manual":
        out["fields"] = "manual"
    elif choice == "specific":
        names = [f.strip() for f in fields_edit.text().split(",") if f.strip()]
        out["fields"] = names or "empty"
    else:
        out["fields"] = "empty"
    return out


class WorkflowEditDialog(QDialog):
    """Edit one workflow: name, editor-button flag, and ordered steps."""

    def __init__(self, parent, workflow: dict | None, dict_buttons: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Edytuj workflow" if workflow else "Nowy workflow")
        self.setMinimumWidth(440)
        self._dict_buttons = dict_buttons

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._name = _expanding_line_edit(workflow.get("name", "") if workflow else "")
        form.addRow("Nazwa (w menu):", self._name)
        self._editor_btn = QCheckBox("Pokaż jako przycisk w edytorze")
        self._editor_btn.setChecked(bool(workflow.get("editor_button")) if workflow else False)
        form.addRow(self._editor_btn)
        layout.addLayout(form)

        layout.addWidget(QLabel("Kroki (kolejność = kolejność wykonania):"))
        self._steps_list = QListWidget()
        self._steps_list.setMaximumHeight(160)
        layout.addWidget(self._steps_list)

        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(4)
        for label, mod, act in (
            ("+ AI", "ai", "generate"),
            ("+ Słownik", "dictionary", "fetch"),
            ("+ TTS", "tts", "generate"),
            ("+ Rozdziel", "field_splitter", "split"),
        ):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, m=mod, a=act: self._add_step(m, a))
            bh.addWidget(b)
        bh.addSpacing(8)
        up = QPushButton("▲")
        up.clicked.connect(self._move_up)
        down = QPushButton("▼")
        down.clicked.connect(self._move_down)
        rm = QPushButton("Usuń")
        rm.clicked.connect(self._remove_step)
        bh.addWidget(up)
        bh.addWidget(down)
        bh.addWidget(rm)
        bh.addStretch()
        layout.addWidget(btn_row)

        layout.addWidget(hint_label(
            "Dwuklik na kroku AI lub Słownik pozwala zmienić jego parametry."
        ))

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._steps: list[dict] = [
            dict(s) for s in (workflow.get("steps", []) if workflow else [])
            if isinstance(s, dict)
        ]
        self._steps_list.itemDoubleClicked.connect(self._edit_step)
        self._refresh()

    def _refresh(self):
        self._steps_list.clear()
        for s in self._steps:
            self._steps_list.addItem(QListWidgetItem(_step_label(s)))

    def _add_step(self, module: str, action: str):
        if module == "ai":
            step = _pick_ai_fields(self, None)
            if step is None:
                return
        elif module == "dictionary":
            dicts = _pick_dicts(self, self._dict_buttons)
            if not dicts:
                return  # cancelled or nothing selected — skip the no-op step
            step = {"module": "dictionary", "action": "fetch", "dicts": dicts}
        else:
            step = {"module": module, "action": action}
        self._steps.append(step)
        self._refresh()

    def _edit_step(self, _item=None):
        idx = self._steps_list.currentRow()
        if idx < 0:
            return
        step = self._steps[idx]
        if step.get("module") == "ai":
            new = _pick_ai_fields(self, step)
            if new is not None:
                self._steps[idx] = new
                self._refresh()
        elif step.get("module") == "dictionary":
            dicts = _pick_dicts(self, self._dict_buttons)
            if dicts:
                step["dicts"] = dicts
                self._refresh()

    def _move_up(self):
        i = self._steps_list.currentRow()
        if i > 0:
            self._steps[i - 1], self._steps[i] = self._steps[i], self._steps[i - 1]
            self._refresh()
            self._steps_list.setCurrentRow(i - 1)

    def _move_down(self):
        i = self._steps_list.currentRow()
        if 0 <= i < len(self._steps) - 1:
            self._steps[i + 1], self._steps[i] = self._steps[i], self._steps[i + 1]
            self._refresh()
            self._steps_list.setCurrentRow(i + 1)

    def _remove_step(self):
        i = self._steps_list.currentRow()
        if i >= 0:
            del self._steps[i]
            self._refresh()

    def get_workflow(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "editor_button": self._editor_btn.isChecked(),
            "steps": self._steps,
        }


# ---------------------------------------------------------------------------
# Main tab
# ---------------------------------------------------------------------------

class WorkflowsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._dict_buttons = cfg.get("dictionary", {}).get("buttons", [])

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(QLabel("Workflowy (każdy to pozycja w menu PPM, kolejność = kolejność w menu):"))
        self._list = QListWidget()
        self._list.setMaximumHeight(180)
        self._list.itemDoubleClicked.connect(self._edit)
        layout.addWidget(self._list)

        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(4)
        add = QPushButton("Dodaj")
        add.clicked.connect(self._add)
        edit = QPushButton("Edytuj")
        edit.clicked.connect(self._edit)
        rm = QPushButton("Usuń")
        rm.clicked.connect(self._remove)
        up = QPushButton("▲")
        up.clicked.connect(self._move_up)
        down = QPushButton("▼")
        down.clicked.connect(self._move_down)
        bh.addWidget(add)
        bh.addWidget(edit)
        bh.addWidget(rm)
        bh.addSpacing(8)
        bh.addWidget(up)
        bh.addWidget(down)
        bh.addStretch()
        layout.addWidget(btn_row)

        layout.addSpacing(8)

        vis_group = QGroupBox("Widoczność wbudowanych sekcji w menu PPM")
        vis_layout = QVBoxLayout(vis_group)
        cm = cfg.get("context_menu", {})
        self._vis_checks: dict[str, QCheckBox] = {}
        for key, label in _CONTEXT_LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(cm.get(key, DEFAULT_CONTEXT_MENU.get(key, True)))
            self._vis_checks[key] = cb
            vis_layout.addWidget(cb)
        vis_layout.addWidget(hint_label(
            "Te sekcje generują się automatycznie (z pól AI, zadań TTS, słowników).\n"
            "Odznacz, by ukryć je w menu — workflowy powyżej zawsze są widoczne."
        ))
        layout.addWidget(vis_group)
        layout.addStretch()

        self._workflows: list[dict] = [
            dict(w) for w in cfg.get("workflows", []) if isinstance(w, dict)
        ]
        self._refresh()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scrollable(inner))

    def _refresh(self):
        self._list.clear()
        for w in self._workflows:
            n_steps = len([s for s in w.get("steps", []) if isinstance(s, dict)])
            flag = "  ⌨" if w.get("editor_button") else ""
            name = w.get("name", "(bez nazwy)")
            self._list.addItem(QListWidgetItem(f"{name}  [{n_steps} kroków]{flag}"))

    def _add(self):
        dlg = WorkflowEditDialog(self, None, self._dict_buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            wf = dlg.get_workflow()
            if not wf["name"]:
                showWarning("Workflow musi mieć nazwę.")
                return
            if not wf["steps"]:
                showWarning("Workflow musi mieć przynajmniej jeden krok.")
                return
            self._workflows.append(wf)
            self._refresh()

    def _edit(self, _item=None):
        idx = self._list.currentRow()
        if idx < 0:
            showWarning("Zaznacz workflow do edycji.")
            return
        dlg = WorkflowEditDialog(self, self._workflows[idx], self._dict_buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            wf = dlg.get_workflow()
            if not wf["name"] or not wf["steps"]:
                showWarning("Workflow musi mieć nazwę i przynajmniej jeden krok.")
                return
            self._workflows[idx] = wf
            self._refresh()

    def _remove(self):
        idx = self._list.currentRow()
        if idx < 0:
            showWarning("Zaznacz workflow do usunięcia.")
            return
        del self._workflows[idx]
        self._refresh()

    def _move_up(self):
        i = self._list.currentRow()
        if i > 0:
            self._workflows[i - 1], self._workflows[i] = self._workflows[i], self._workflows[i - 1]
            self._refresh()
            self._list.setCurrentRow(i - 1)

    def _move_down(self):
        i = self._list.currentRow()
        if 0 <= i < len(self._workflows) - 1:
            self._workflows[i + 1], self._workflows[i] = self._workflows[i], self._workflows[i + 1]
            self._refresh()
            self._list.setCurrentRow(i + 1)

    def apply(self, cfg: dict) -> None:
        cfg["workflows"] = self._workflows
        cfg["context_menu"] = {
            key: cb.isChecked() for key, cb in self._vis_checks.items()
        }
