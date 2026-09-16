"""Logi tab — debug toggle and live view of the addon's in-memory log buffer."""

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton,
    QPlainTextEdit, QLabel, QApplication, QTimer, QFont,
)

from ..common import set_debug, get_log_lines, get_log_seq, clear_log
from ..common.ui import hint_label


class LogsTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._debug_cb = QCheckBox(
            "Tryb debugowania — rejestruj szczegółowe logi (DEBUG)"
        )
        self._debug_cb.setChecked(cfg.get("debug", {}).get("enabled", False))
        # Apply immediately so the user can watch a generation run without
        # closing the dialog first; persisted in apply() on OK.
        self._debug_cb.toggled.connect(set_debug)
        layout.addWidget(self._debug_cb)

        layout.addWidget(hint_label(
            "Logi modułów wtyczki (TTS, AI Generator, słownik...). Bufor trzymany w pamięci "
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

    def _refresh(self, force: bool = False):
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
