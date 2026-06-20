"""Shared widgets and helpers for the Settings dialog."""

from aqt import mw
from aqt.qt import (
    QWidget, QHBoxLayout, QSizePolicy, QLineEdit,
    QPushButton, QScrollArea, QFrame, Qt,
    QListWidget, QListWidgetItem, QFormLayout, QLabel,
)

from .html import clean_html_normalized


def palette() -> dict:
    """Theme-aware colors — hardcoded light values are unreadable in night mode."""
    try:
        from aqt.theme import theme_manager
        night = theme_manager.night_mode
    except Exception:
        night = False

    if night:
        return {
            "ok_bg": "#1e3327", "ok_fg": "#7fce9e",
            "warn_bg": "#3d3320", "warn_fg": "#e3b35c",
            "off_bg": "#2b2e33", "off_fg": "#9aa3ad",
            "frame_bg": "#2c2f33", "border": "#44484d",
            "muted": "#9aa3ad",
            "card_bg": "#25282c", "detail": "#b6bec7",
            "issue_bg": "#3a3322", "issue_border": "#5c5230", "issue_fg": "#e0c98a",
            "ready_fg": "#7fce9e",
            "syntax_var": "#7fb3e3", "syntax_block": "#c79be3", "syntax_bad": "#e08a8a",
        }
    return {
        "ok_bg": "#eaf5ee", "ok_fg": "#1f7a3f",
        "warn_bg": "#fff4dc", "warn_fg": "#8a5a00",
        "off_bg": "#eef0f3", "off_fg": "#5c6570",
        "frame_bg": "#f7f8fa", "border": "#d9dde3",
        "muted": "#5c6570",
        "card_bg": "white", "detail": "#4f5863",
        "issue_bg": "#fffaf0", "issue_border": "#ead8aa", "issue_fg": "#5c3d00",
        "ready_fg": "#1f7a3f",
        "syntax_var": "#1f4f7a", "syntax_block": "#7a3fa0", "syntax_bad": "#b03030",
    }


def hint_label(text: str, small: bool = False) -> QLabel:
    """Muted, word-wrapped helper text consistent across tabs and themes."""
    label = QLabel(text)
    label.setWordWrap(True)
    size = " font-size: 11px;" if small else ""
    label.setStyleSheet(f"color: {palette()['muted']};{size}")
    return label


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


def get_sample_notes(note_type_name: str, limit: int = 20) -> list[tuple[int, str]]:
    """Return up to `limit` (note_id, label) pairs for notes of the given type.

    The label is the first non-empty field, cleaned and truncated — meant for
    a "sample note" picker. Returns [] when the collection is unavailable.
    """
    if not note_type_name:
        return []
    try:
        escaped = note_type_name.replace('"', '\\"')
        nids = mw.col.find_notes(f'note:"{escaped}"')[:limit]
    except Exception:
        return []
    out: list[tuple[int, str]] = []
    for nid in nids:
        try:
            note = mw.col.get_note(nid)
        except Exception:
            continue
        label = ""
        for value in note.values():
            text = clean_html_normalized(value).strip()
            if text:
                label = text
                break
        if len(label) > 60:
            label = label[:57] + "…"
            out.append((nid, label or f"(notatka {nid})"))
    return out
