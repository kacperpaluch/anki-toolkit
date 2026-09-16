"""HTML Cleanup settings panel."""

import re

from aqt.qt import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    Qt,
    QVBoxLayout,
    QWidget,
)

from .cleaning import default_rules


_COLUMNS = ["Nazwa", "Znajdź", "Zamień na", "Regex", "Powtarzaj", "Pola"]
_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked


def _check_item(checked: bool) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
    item.setCheckState(_CHECKED if checked else _UNCHECKED)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


class HtmlCleanupTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        from . import with_rules
        config = with_rules(cfg.get("html_cleanup") or {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        intro = QLabel(
            "Reguły stosowane są kolejno, od góry do dołu, przy dodawaniu notatki "
            "i podczas czyszczenia całej kolekcji."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for column in (0, 3, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        for rule in config["rules"]:
            self._add_row(rule)
        layout.addWidget(self._table, 1)

        buttons_row = QHBoxLayout()
        for text, handler in (
            ("▲", lambda: self._move(-1)),
            ("▼", lambda: self._move(1)),
            ("Dodaj", lambda: self._add_row({"on": True, "name": "Nowa reguła"})),
            ("Usuń", self._remove_row),
            ("Przywróć domyślne", self._restore_defaults),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons_row.addWidget(button)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        hint = QLabel(
            "<b>Nazwa</b> — zaznaczenie włącza regułę; nazwa pojawia się w podsumowaniu.<br>"
            "<b>Regex</b> — wzorzec wyrażenia regularnego (DOTALL, bez rozróżniania "
            "wielkości liter); w polu „Zamień na” działają odwołania <code>\\1</code>. "
            "Bez zaznaczenia „Znajdź” to zwykły tekst.<br>"
            "<b>Powtarzaj</b> — stosuj regułę wielokrotnie, aż przestanie coś zmieniać "
            "(potrzebne przy zagnieżdżonych tagach).<br>"
            "<b>Pola</b> — puste = wszystkie pola, <code>ang</code> = tylko to pole, "
            "<code>!ang</code> = wszystkie oprócz niego. Można podać kilka po przecinku."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._show_tooltip = QCheckBox("Pokazuj podsumowanie po czyszczeniu")
        self._show_tooltip.setChecked(config.get("show_tooltip", True))
        self._auto_startup = QCheckBox("Czyść całą kolekcję przy otwarciu profilu")
        self._auto_startup.setChecked(config.get("auto_run_startup", False))
        layout.addWidget(self._show_tooltip)
        layout.addWidget(self._auto_startup)

    def _add_row(self, rule: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        name = QTableWidgetItem(rule.get("name", ""))
        name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        name.setCheckState(_CHECKED if rule.get("on", True) else _UNCHECKED)
        self._table.setItem(row, 0, name)
        self._table.setItem(row, 1, QTableWidgetItem(rule.get("find", "")))
        self._table.setItem(row, 2, QTableWidgetItem(rule.get("to", "")))
        self._table.setItem(row, 3, _check_item(rule.get("regex", False)))
        self._table.setItem(row, 4, _check_item(rule.get("repeat", False)))
        self._table.setItem(row, 5, QTableWidgetItem(rule.get("fields", "")))

    def _remove_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)

    def _move(self, delta: int) -> None:
        """Order matters: <div> must become <br> before a trailing <br> is trimmed."""
        row = self._table.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self._table.rowCount()):
            return
        rules = self._collect_rules()
        rules[row], rules[target] = rules[target], rules[row]
        self._set_rules(rules)
        self._table.setCurrentCell(target, 0)

    def _restore_defaults(self) -> None:
        self._set_rules(default_rules())

    def _set_rules(self, rules: list[dict]) -> None:
        self._table.setRowCount(0)
        for rule in rules:
            self._add_row(rule)

    def _collect_rules(self) -> list[dict]:
        rules = []
        for row in range(self._table.rowCount()):
            def text(column: int) -> str:
                item = self._table.item(row, column)
                return item.text() if item else ""

            def checked(column: int) -> bool:
                item = self._table.item(row, column)
                return bool(item) and item.checkState() == _CHECKED

            rules.append({
                "on": checked(0),
                "name": text(0).strip(),
                "find": text(1),
                "to": text(2),
                "regex": checked(3),
                "repeat": checked(4),
                "fields": text(5).strip(),
            })
        return rules

    def validate(self) -> str | None:
        for row, rule in enumerate(self._collect_rules(), start=1):
            if not rule["regex"] or not rule["find"]:
                continue
            try:
                re.compile(rule["find"]).sub(rule["to"], "")
            except (re.error, IndexError) as error:  # IndexError: unknown group in the replacement
                return (f"HTML Cleanup: wiersz {row} („{rule['name'] or rule['find']}”) "
                        f"ma niepoprawne wyrażenie regularne:\n\n{error}")
        return None

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("html_cleanup", {}).update({
            "rules": self._collect_rules(),
            "show_tooltip": self._show_tooltip.isChecked(),
            "auto_run_startup": self._auto_startup.isChecked(),
        })
