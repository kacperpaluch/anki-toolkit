"""Field Hider tab — wybór pól chowanych w oknie „Dodaj” per typ notatki."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QLabel,
    QScrollArea, QFrame,
)

from ..common.ui import hint_label, get_note_type_names, get_fields_for_note_type


class FieldHiderTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        # Stan roboczy: {typ_notatki: [ukryte pola]} — trzymamy pełną mapę z configu,
        # aktualizujemy per typ przy przełączaniu, żeby nie gubić innych typów.
        fh = cfg.get("field_hider", {})
        self._hidden = {
            nt: list(fields)
            for nt, fields in (fh.get("hidden_fields") or {}).items()
        }
        self._current_type: str | None = None
        self._checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(hint_label(
            "Chowa zaznaczone pola w oknie „Dodaj” — przydatne dla pól pomocniczych "
            "wypełnianych później (AI, TTS). Pola pozostają widoczne w przeglądarce i "
            "przy edycji istniejących kart.\n"
            "Przycisk 👁 w pasku edytora „Dodaj” tymczasowo pokazuje schowane pola."
        ))
        layout.addSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Typ notatki:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(get_note_type_names())
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        row.addWidget(self._type_combo, 1)
        layout.addLayout(row)
        layout.addSpacing(4)

        # Kontener na checkboxy pól — przewijalny (typy notatek bywają szerokie).
        self._fields_box = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_box)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidget(self._fields_box)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll, 1)

        # Pierwszy typ z listy (jeśli jest)
        if self._type_combo.count():
            self._on_type_changed(self._type_combo.currentText())

    def _on_type_changed(self, note_type: str) -> None:
        # Zapisz stan poprzedniego typu przed przełączeniem
        self._store_current()
        self._current_type = note_type or None
        self._rebuild_checks()

    def _store_current(self) -> None:
        if self._current_type is None:
            return
        hidden = [name for name, cb in self._checks.items() if cb.isChecked()]
        if hidden:
            self._hidden[self._current_type] = hidden
        else:
            self._hidden.pop(self._current_type, None)

    def _rebuild_checks(self) -> None:
        # Wyczyść stare checkboxy
        self._checks.clear()
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._current_type:
            return

        fields = get_fields_for_note_type(self._current_type)
        hidden = set(self._hidden.get(self._current_type, []))
        if not fields:
            self._fields_layout.addWidget(hint_label(
                "Ten typ notatki nie ma pól lub jest niedostępny."
            ))
            return

        for name in fields:
            cb = QCheckBox(name)
            cb.setChecked(name in hidden)
            self._checks[name] = cb
            self._fields_layout.addWidget(cb)
        self._fields_layout.addStretch()

    def apply(self, cfg: dict) -> None:
        self._store_current()
        cfg.setdefault("field_hider", {})
        cfg["field_hider"]["hidden_fields"] = dict(self._hidden)
