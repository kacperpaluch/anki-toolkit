from . import gui
from . import watcher


def setup_menu(parent_menu=None):
    gui.init_menu(parent_menu)
    watcher.init_auto_normalize()
