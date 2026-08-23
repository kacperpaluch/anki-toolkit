"""Anki Toolkit: Content — AI, dictionaries, TTS, and workflows."""
from aqt import mw,gui_hooks
from aqt.qt import QAction,QTimer
from . import ai_generator,dictionary,tts,field_splitter
ai_generator.migrate_workflows()
gui_hooks.editor_did_init_buttons.append(ai_generator.on_editor_buttons_init)
gui_hooks.editor_did_init_buttons.append(dictionary.on_editor_buttons_init)
gui_hooks.editor_did_init_buttons.append(tts.on_editor_buttons_init)
gui_hooks.profile_did_open.append(lambda:ai_generator.check_pending_batches(silent=True))
def _context(browser,menu):
 sub=menu.addMenu('Anki Toolkit: Content');ai_generator.add_to_context_menu(browser,sub);dictionary.add_to_context_menu(browser,sub);tts.add_to_context_menu(browser,sub);field_splitter.add_to_context_menu(browser,sub)
from anki.hooks import addHook
addHook('browser.onContextMenu',_context)
def _menu(*_):
 from .content_settings import open_settings
 menu=mw.form.menuTools.addMenu('Anki Toolkit: Content');a=QAction('Ustawienia…',menu);a.triggered.connect(open_settings);menu.addAction(a)
if hasattr(gui_hooks,'main_window_did_init'):gui_hooks.main_window_did_init.append(_menu)
else:QTimer.singleShot(0,_menu)
