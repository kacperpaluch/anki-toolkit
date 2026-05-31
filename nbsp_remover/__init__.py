from aqt import mw
from aqt.qt import QAction, QMessageBox

from .addcards import init_addcards
from .collection import clean_collection
from .utils import _get_config


def _confirm_purge():
    result = QMessageBox.question(
        mw,
        "Purge collection",
        "Ta operacja usunie &nbsp; i wyczyści <div> we wszystkich kartach.\n"
        "Zmiany są nieodwracalne.\n\n"
        "Kontynuować?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        clean_collection()


def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools

    action = QAction("Purge collection from &nbsp;", mw)
    action.triggered.connect(_confirm_purge)
    menu.addAction(action)

    init_addcards()

    if _get_config().get("auto_run_startup", False):
        clean_collection()
