"""Shared widgets and helpers for the Settings dialog."""

from aqt import mw
from aqt.qt import (
    QWidget, QHBoxLayout, QSizePolicy, QLineEdit,
    QPushButton, QScrollArea, QFrame, Qt,
    QListWidget, QListWidgetItem, QFormLayout,
)


def _expanding_line_edit(text: str = "") -> QLineEdit:
    w = QLineEdit(text)
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return w


def _api_key_widget(text: str = "") -> tuple:
    """Return (container_widget, QLineEdit) — password field with show/hide toggle."""
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)

    field = QLineEdit(text)
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    btn = QPushButton("Pokaż")
    btn.setFixedWidth(60)
    btn.setCheckable(True)

    def _toggle(checked: bool) -> None:
        if checked:
            field.setEchoMode(QLineEdit.EchoMode.Normal)
            btn.setText("Ukryj")
        else:
            field.setEchoMode(QLineEdit.EchoMode.Password)
            btn.setText("Pokaż")

    btn.toggled.connect(_toggle)
    row.addWidget(field)
    row.addWidget(btn)
    return container, field


def _scrollable(inner: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidget(inner)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    return scroll


def get_field_names() -> list[str]:
    """Return sorted list of all field names in the collection."""
    field_names = set()
    for model in mw.col.models.all():
        for fld in model["flds"]:
            field_names.add(fld["name"])
    return sorted(field_names)


def get_note_type_names() -> list[str]:
    """Return sorted list of note type names, or [] if collection unavailable."""
    try:
        return sorted(m["name"] for m in mw.col.models.all())
    except Exception:
        return []


def get_fields_for_note_type(note_type_name: str) -> list[str]:
    """Return field names of a note type, or [] if not found / collection unavailable."""
    try:
        model = mw.col.models.by_name(note_type_name)
    except Exception:
        return []
    if not model:
        return []
    return [fld["name"] for fld in model["flds"]]


def get_templates_for_field(field_name: str) -> list[tuple[int, str]]:
    """Return list of (ord, template_name) for note types containing field_name."""
    seen: dict[int, str] = {}
    for model in mw.col.models.all():
        if not any(fld["name"] == field_name for fld in model["flds"]):
            continue
        for tmpl in model["tmpls"]:
            ord_val = tmpl["ord"]
            if ord_val not in seen:
                seen[ord_val] = tmpl["name"]
    return sorted(seen.items())
