from aqt import gui_hooks, mw
from aqt.qt import QAction, QMessageBox

from .addcards import init_addcards
from .collection import clean_collection
from .utils import _get_config


def _confirm_purge():
    result = QMessageBox.question(
        mw,
        "Wyczyść HTML w kolekcji",
        "Ta operacja usunie &nbsp; i wyczyści <div> we wszystkich kartach.\n"
        "Zmiany są nieodwracalne.\n\n"
        "Kontynuować?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        clean_collection()


def _maybe_auto_clean():
    if _get_config().get("auto_run_startup", False):
        clean_collection()


def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools

    action = QAction("Wyczyść HTML w kolekcji...", mw)
    action.triggered.connect(_confirm_purge)
    menu.addAction(action)

    init_addcards()

    # Auto-clean must wait for the collection — at main_window_did_init the
    # profile may not be open yet. If it already is, run directly (the hook
    # would only fire again on a profile switch).
    if mw.col is not None:
        _maybe_auto_clean()
    else:
        gui_hooks.profile_did_open.append(_maybe_auto_clean)
