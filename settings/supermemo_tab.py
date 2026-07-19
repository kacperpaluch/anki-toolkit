"""SuperMemo — konfiguracja mapowania pól bazy SM na talię docelową."""

from aqt.qt import (
    QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget, Qt,
)

from ..common.ui import (
    get_note_type_names, get_fields_for_note_type, get_all_field_names,
    hint_label,
)

_SKIP = "— pomiń —"


class SuperMemoTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        sm = cfg.get("supermemo", {})
        self._field_map = dict(sm.get("field_map", {}))
        self._dst_names = get_all_field_names()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(hint_label(
            "Przycisk „SM” w edytorze bierze słowo z pola dopasowania, znajduje wpis "
            "w bazie SuperMemo i kopiuje zmapowane pola (tylko puste — nie nadpisuje).\n"
            "Ustaw, które pole SM trafia do którego pola Twojej talii. „— pomiń —” "
            "wyłącza dane pole (np. przykłady generujesz osobno)."
        ))
        layout.addSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._source_type = QComboBox()
        self._source_type.addItems(get_note_type_names())
        _select(self._source_type, sm.get("source_note_type", "SuperMemo Extreme"))
        self._source_type.currentTextChanged.connect(self._on_type_changed)
        form.addRow("Typ notatki SuperMemo", self._source_type)

        self._source_match = QComboBox()  # pole SM z angielskim słowem
        form.addRow("Pole SM z hasłem", self._source_match)
        self._saved_source_match = sm.get("source_match_field", "English")

        self._match_field = QComboBox()
        self._match_field.addItems(self._dst_names)
        _select(self._match_field, sm.get("match_field", "ang"))
        self._match_field.setToolTip("Pole Twojej talii, z którego czytane jest słowo do wyszukania")
        form.addRow("Pole talii z hasłem", self._match_field)

        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addWidget(QLabel("Mapowanie pól SuperMemo → Twoja talia:"))

        self._map_form = QFormLayout()
        self._map_form.setSpacing(6)
        self._map_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.addLayout(self._map_form)
        layout.addStretch()

        self._map_combos: dict[str, QComboBox] = {}
        self._rebuild()

    def _on_type_changed(self, _text: str) -> None:
        # ponytail: przełączenie typu gubi niezapisane mapowanie poprzedniego typu.
        # Realnie jest jeden typ SM, więc nie warto trzymać mapy per typ.
        self._rebuild()

    def _rebuild(self) -> None:
        source_type = self._source_type.currentText()
        fields = get_fields_for_note_type(source_type)

        # Pole SM z hasłem — pola bieżącego typu
        self._source_match.clear()
        self._source_match.addItems(fields)
        _select(self._source_match, self._saved_source_match)

        # Wiersze mapowania — jeden na pole SM
        self._map_combos.clear()
        while self._map_form.count():
            item = self._map_form.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not fields:
            self._map_form.addRow(hint_label("Ten typ notatki nie ma pól."))
            return

        for sm_field in fields:
            combo = QComboBox()
            combo.addItem(_SKIP, "")
            combo.addItems(self._dst_names)
            _select(combo, self._field_map.get(sm_field, ""))
            self._map_combos[sm_field] = combo
            self._map_form.addRow(sm_field + " →", combo)

    def apply(self, cfg: dict) -> None:
        sm = cfg.setdefault("supermemo", {})
        sm["source_note_type"] = self._source_type.currentText().strip()
        sm["source_match_field"] = self._source_match.currentText().strip()
        sm["match_field"] = self._match_field.currentText().strip()
        field_map = {
            sm_field: combo.currentText().strip()
            for sm_field, combo in self._map_combos.items()
            if combo.currentText().strip() and combo.currentText() != _SKIP
        }
        # Zachowaj mapowania pól spoza bieżącego typu (gdyby ktoś zmienił typ),
        # żeby apply nie skasowało reszty mapy bez powodu.
        for k, v in self._field_map.items():
            if k not in self._map_combos:
                field_map.setdefault(k, v)
        sm["field_map"] = field_map


def _select(combo: QComboBox, value: str) -> None:
    idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)
