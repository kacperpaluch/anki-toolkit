"""Editor keyboard shortcuts the user assigns to Toolkit actions (`editor.shortcuts`)."""
from aqt import mw
from aqt.qt import (
    QAbstractButton, QAction, QDialog, QDialogButtonBox, QFormLayout, QKeySequence,
    QKeySequenceEdit, QLabel, QShortcut, QVBoxLayout,
)
from aqt.utils import showWarning, tooltip

from .common import get_module_config, shortcut_typing_problem, update_module_config

_PORTABLE = QKeySequence.SequenceFormat.PortableText
_NATIVE = QKeySequence.SequenceFormat.NativeText
_EDITING = ("Copy", "Cut", "Paste", "Undo", "Redo", "SelectAll", "Bold", "Italic", "Underline")


def get_shortcuts() -> dict:
    """Action label → portable key combination."""
    return dict(get_module_config("editor", {"shortcuts": {}})["shortcuts"])


def native(keys: str) -> str:
    return QKeySequence(keys).toString(_NATIVE)


def _taken(window, own: dict) -> dict:
    """Portable keys → who holds them: text editing, Anki and other add-ons in this window."""
    taken = {}
    for name in _EDITING:
        for sequence in QKeySequence.keyBindings(getattr(QKeySequence.StandardKey, name)):
            taken[sequence.toString(_PORTABLE)] = "edycja tekstu"
    # shortcut: the editor's own formatting keys live in its JavaScript and are not
    # visible to Qt — only the standard editing keys above are known; list more if they bite.
    for root in filter(None, (mw, window)):
        for action in root.findChildren(QAction):
            for sequence in action.shortcuts():
                taken[sequence.toString(_PORTABLE)] = action.text().replace("&", "") or "Anki"
        for button in root.findChildren(QAbstractButton):
            taken[button.shortcut().toString(_PORTABLE)] = button.text().replace("&", "") or "Anki"
        for shortcut in root.findChildren(QShortcut):
            taken.setdefault(shortcut.key().toString(_PORTABLE), "Anki albo inny dodatek")
    taken.pop("", None)
    for keys in own.values():  # ours are live QShortcuts of this window too
        taken.pop(QKeySequence(keys).toString(_PORTABLE), None)
    return taken


class ShortcutsDialog(QDialog):
    def __init__(self, window, labels: list):
        super().__init__(window)
        self.setWindowTitle("Anki Toolkit — skróty klawiszowe")
        current = get_shortcuts()
        self._taken = _taken(window, current)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Kliknij pole i naciśnij kombinację klawiszy. Krzyżyk usuwa skrót."))
        form = QFormLayout()
        self._edits = {}
        for label in labels:
            edit = QKeySequenceEdit(QKeySequence(current.get(label, "")))
            edit.setMaximumSequenceLength(1)
            edit.setClearButtonEnabled(True)
            form.addRow(label, edit)
            self._edits[label] = edit
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Zapisz")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        """Validate here, so a refused combination keeps the dialog and the other rows."""
        chosen = {}
        for label, edit in self._edits.items():
            keys = edit.keySequence().toString(_PORTABLE)
            if not keys:
                continue
            holder = next((f"„{other}”" for other, used in chosen.items() if used == keys),
                          self._taken.get(keys))
            problem = shortcut_typing_problem(keys) or (holder and f"jest już zajęty ({holder})")
            if problem:
                showWarning(f"Skrót {native(keys)} dla „{label}”: {problem}.", parent=self)
                edit.setFocus()
                return
            chosen[label] = keys
        update_module_config("editor", {"shortcuts": chosen})
        super().accept()
        # Anki registers editor shortcuts once per editor.
        tooltip("Anki Toolkit: skróty zadziałają po ponownym otwarciu okna.", period=3000)


def edit_shortcuts(window, labels: list) -> None:
    ShortcutsDialog(window, labels).exec()
