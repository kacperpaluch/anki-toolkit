"""Deck Router tab — reguły kierowania kart do talii wg tagu (+ opcjonalnie szablonu)."""

from aqt import mw
from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPushButton, QComboBox,
)

from ..common.ui import hint_label

_ALL_TEMPLATES = "(wszystkie)"


class DeckRouterTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._templates = self._collect_templates()
        self._decks = self._collect_decks()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(hint_label(
            "Kieruje karty do talii na podstawie tagu notatki — uzupełnia natywny "
            "Deck Override, który działa tylko per-szablon.\n"
            "Notatka z danym tagiem → jej karty trafiają do wskazanej talii "
            "(tworzona automatycznie, jeśli nie istnieje)."
        ))
        layout.addSpacing(8)

        dr = cfg.get("deck_router", {})
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            ["Tag", "Szablon", "Talia docelowa"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        for rule in dr.get("rules", []):
            if isinstance(rule, dict):
                self._add_row(
                    rule.get("tag", ""), rule.get("template", ""), rule.get("deck", "")
                )
        layout.addWidget(self._table)

        btns = QHBoxLayout()
        add_btn = QPushButton("＋ Dodaj regułę")
        add_btn.clicked.connect(lambda: self._add_row("", "", ""))
        del_btn = QPushButton("－ Usuń zaznaczoną")
        del_btn.clicked.connect(self._del_row)
        run_btn = QPushButton("Uporządkuj istniejące karty…")
        run_btn.setToolTip(
            "Przejdź po notatkach z tagami z powyższych reguł i przenieś ich karty "
            "do właściwych talii. Używa reguł z tabeli — także niezapisanych."
        )
        run_btn.clicked.connect(self._run_now)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addSpacing(12)
        btns.addWidget(run_btn)
        btns.addStretch()
        layout.addLayout(btns)

        layout.addWidget(hint_label(
            "Szablon „(wszystkie)” = wszystkie karty notatki; konkretny (np. „pol-ang”) "
            "= tylko ten szablon, reszta kart zostaje wg natywnego override. "
            "Talia: wybierz istniejącą z listy lub wpisz nową (zostanie utworzona; "
            "zagnieżdżanie przez ::). Pierwsza pasująca reguła wygrywa — reguły "
            "węższe (ze szablonem) umieszczaj wyżej. Notatka bez pasującego tagu nie "
            "jest ruszana.\n"
            "Działa przy dodawaniu w oknie „Dodaj”, po AI-workflow w przeglądarce oraz "
            "ręcznie: Narzędzia → Anki Toolkit → „Deck Router: uporządkuj istniejące karty…”.",
            small=True,
        ))
        layout.addStretch()

    @staticmethod
    def _collect_templates() -> list[str]:
        names: set[str] = set()
        try:
            for model in mw.col.models.all():
                for tmpl in model.get("tmpls", []):
                    name = tmpl.get("name")
                    if name:
                        names.add(name)
        except Exception:
            pass
        return sorted(names)

    @staticmethod
    def _collect_decks() -> list[str]:
        try:
            return sorted(d.name for d in mw.col.decks.all_names_and_ids())
        except Exception:
            return []

    def _add_row(self, tag: str, template: str, deck: str) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)

        self._table.setItem(r, 0, QTableWidgetItem(tag))

        tmpl_combo = QComboBox()
        tmpl_combo.addItem(_ALL_TEMPLATES)
        tmpl_combo.addItems(self._templates)
        if template:
            idx = tmpl_combo.findText(template)
            if idx < 0:  # szablon z typu notatki, którego już nie ma — zachowaj
                tmpl_combo.addItem(template)
                idx = tmpl_combo.count() - 1
            tmpl_combo.setCurrentIndex(idx)
        else:
            tmpl_combo.setCurrentIndex(0)
        self._table.setCellWidget(r, 1, tmpl_combo)

        deck_combo = QComboBox()
        deck_combo.setEditable(True)  # istniejące jako podpowiedzi, nowe można wpisać
        deck_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        deck_combo.addItems(self._decks)
        deck_combo.setCurrentText(deck)
        self._table.setCellWidget(r, 2, deck_combo)

    def _del_row(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            self._table.removeRow(r)

    def _collect_rules(self) -> list[dict]:
        rules = []
        for r in range(self._table.rowCount()):
            tag_item = self._table.item(r, 0)
            tag = tag_item.text().strip() if tag_item else ""

            tmpl_w = self._table.cellWidget(r, 1)
            template = tmpl_w.currentText() if tmpl_w else ""
            if template == _ALL_TEMPLATES:
                template = ""

            deck_w = self._table.cellWidget(r, 2)
            deck = deck_w.currentText().strip() if deck_w else ""

            if not tag or not deck:
                continue
            rule = {"tag": tag, "deck": deck}
            if template:
                rule["template"] = template
            rules.append(rule)
        return rules

    def _run_now(self) -> None:
        from ..deck_router import confirm_reorganize
        confirm_reorganize(self._collect_rules(), parent=self)

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("deck_router", {})
        cfg["deck_router"]["rules"] = self._collect_rules()
