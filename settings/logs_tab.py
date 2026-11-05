"""Logi tab — recent operation reports, debug toggle and the in-memory log buffer."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QDialog, QGroupBox,
    QPlainTextEdit, QLabel, QApplication, QTimer, QFont, QListWidget, QListWidgetItem, Qt,
)
from aqt.utils import askUser, showText

from ..common import (
    set_debug, get_log_lines, get_log_seq, clear_log, recent_reports, reports_seq, take_retry,
)
from ..common.ui import hint_label


class LogsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        reports_group = QGroupBox("Ostatnie operacje (ta sesja)")
        reports_layout = QVBoxLayout(reports_group)
        self._reports = QListWidget()
        self._reports.setMaximumHeight(130)
        self._reports.itemDoubleClicked.connect(lambda _item: self._show_report())
        self._reports.currentItemChanged.connect(lambda *_: self._update_report_buttons())
        reports_layout.addWidget(self._reports)
        report_row = QHBoxLayout()
        self._show_btn = QPushButton("Pokaż raport")
        self._show_btn.clicked.connect(self._show_report)
        self._retry_btn = QPushButton("Ponów nieudane")
        self._retry_btn.setToolTip("Uruchamia operację jeszcze raz tylko dla notatek z błędem.")
        self._retry_btn.clicked.connect(self._retry)
        report_row.addWidget(self._show_btn)
        report_row.addWidget(self._retry_btn)
        report_row.addStretch()
        reports_layout.addLayout(report_row)
        reports_layout.addWidget(hint_label(
            "Wyniki generowania AI, sekwencji, wymowy i nagrań zostają tu po zniknięciu"
            " komunikatu — do zamknięcia profilu (ostatnie 20).", small=True))
        layout.addWidget(reports_group)
        self._reports_seq = -1

        self._debug_cb = QCheckBox(
            "Tryb debugowania — rejestruj szczegółowe logi (DEBUG)"
        )
        self._debug_cb.setChecked(cfg.get("debug", {}).get("enabled", False))
        # Apply immediately so the user can watch a generation run without
        # closing the dialog first; persisted in apply() on OK.
        self._debug_cb.toggled.connect(set_debug)
        layout.addWidget(self._debug_cb)

        layout.addWidget(hint_label(
            "Logi modułów wtyczki (AI, nagrania, słowniki...). Bufor trzymany w pamięci "
            "(ostatnie 2000 wpisów), czyszczony przy restarcie Anki. Bez trybu debugowania "
            "rejestrowane są INFO/WARNING/ERROR. Widok odświeża się automatycznie co 2 s.",
            small=True,
        ))

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self._view.setFont(font)
        layout.addWidget(self._view, 1)

        row = QHBoxLayout()
        refresh_btn = QPushButton("Odśwież")
        refresh_btn.clicked.connect(lambda: self._refresh(force=True))
        copy_btn = QPushButton("Kopiuj")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(self._view.toPlainText())
        )
        clear_btn = QPushButton("Wyczyść")
        clear_btn.clicked.connect(self._clear)
        row.addWidget(refresh_btn)
        row.addWidget(copy_btn)
        row.addWidget(clear_btn)
        row.addStretch()
        layout.addLayout(row)

        self._last_seq = -1
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh(force=True)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _refresh_reports(self, force: bool = False):
        if not force and reports_seq() == self._reports_seq:
            return
        self._reports_seq = reports_seq()
        selected = self._selected_report()
        self._reports.clear()
        for report in recent_reports():
            failed = f"  ·  błędy: {report['failed']}" if report["failed"] else ""
            item = QListWidgetItem(f"{report['time']}  {report['title']}{failed}")
            item.setData(Qt.ItemDataRole.UserRole, report["id"])  # Qt would store a copy of the dict
            self._reports.addItem(item)
            if selected is not None and report["id"] == selected["id"]:
                self._reports.setCurrentItem(item)
        if self._reports.count() == 0:
            self._reports.addItem("(brak operacji w tej sesji)")
        self._update_report_buttons()

    def _selected_report(self):
        item = self._reports.currentItem()
        report_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return next((r for r in recent_reports() if r["id"] == report_id), None)

    def _update_report_buttons(self):
        report = self._selected_report()
        self._show_btn.setEnabled(report is not None)
        self._retry_btn.setEnabled(bool(report and report["retry"]))

    def _show_report(self):
        report = self._selected_report()
        if report is not None:
            showText(report["text"], parent=self, title=report["title"], type="text", copyBtn=True)

    def _retry(self):
        report = self._selected_report()
        if not report or not report["retry"]:
            return
        if not askUser(
            f"Ponowić {report['failed']} nieudanych notatek z operacji „{report['title']}”?\n\n"
            "Okno Ustawień zamknie się bez zapisywania niezapisanych zmian.", parent=self,
        ):
            return
        retry = take_retry(report["id"])
        if retry is None:
            return
        dialog = self.window()
        if isinstance(dialog, QDialog):
            dialog.reject()
        QTimer.singleShot(0, retry)  # after the modal settings loop has returned

    def _refresh(self, force: bool = False):
        self._refresh_reports(force)
        seq = get_log_seq()
        if not force and seq == self._last_seq:
            return
        self._last_seq = seq
        lines = get_log_lines()
        scrollbar = self._view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        self._view.setPlainText(
            "\n".join(lines) if lines else "(brak wpisów)"
        )
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _clear(self):
        clear_log()
        self._refresh(force=True)

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("debug", {})
        cfg["debug"]["enabled"] = self._debug_cb.isChecked()
        set_debug(self._debug_cb.isChecked())
