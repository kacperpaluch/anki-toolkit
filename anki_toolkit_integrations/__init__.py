"""Anki Toolkit: Integrations — n8n Word Queue and local Web Bridge."""
from aqt import gui_hooks,mw
from aqt.qt import QAction,QTimer
from . import word_queue,bridge
gui_hooks.add_cards_did_add_note.append(word_queue.on_add_note)
gui_hooks.editor_did_init_buttons.append(word_queue.on_editor_buttons_init)
gui_hooks.profile_did_open.append(bridge.start_server)

def _menu(*_):
 from .settings import open_settings
 menu=mw.form.menuTools.addMenu('Anki Toolkit: Integrations')
 a=QAction('Ustawienia…',menu);a.triggered.connect(open_settings);menu.addAction(a)
 a=QAction('Kolejka słówek (n8n)…',menu);a.triggered.connect(word_queue.open_queue);menu.addAction(a)
if hasattr(gui_hooks,'main_window_did_init'):gui_hooks.main_window_did_init.append(_menu)
else:QTimer.singleShot(0,_menu)
