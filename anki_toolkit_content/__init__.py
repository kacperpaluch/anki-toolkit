"""Anki Toolkit: Content — AI, dictionaries, TTS, and workflows."""
from aqt import mw,gui_hooks
from aqt.qt import QAction,QTimer
from . import ai_generator,dictionary,tts,field_splitter
from .common import setup_logging
setup_logging()
ai_generator.migrate_workflows()
gui_hooks.editor_did_init_buttons.append(ai_generator.on_editor_buttons_init)
gui_hooks.editor_did_init_buttons.append(dictionary.on_editor_buttons_init)
gui_hooks.editor_did_init_buttons.append(tts.on_editor_buttons_init)
gui_hooks.profile_did_open.append(lambda:ai_generator.check_pending_batches(silent=True))
# Batche kończą się w ciągu godzin, a zadanie wygasa po 24h — bez cyklicznego
# sprawdzania wyniki czekałyby do następnego startu Anki, a reszta zadania
# nigdy by nie poszła. check_pending_batches() samo pilnuje, by dwa przebiegi
# się nie nałożyły i by nie ruszać zamkniętego profilu.
_batch_timer=QTimer(mw);_batch_timer.setInterval(60000)
_batch_timer.timeout.connect(lambda:ai_generator.check_pending_batches(silent=True))
_batch_timer.start()
def _context(browser,menu):
 sub=menu.addMenu('Anki Toolkit: Content');ai_generator.add_to_context_menu(browser,sub);dictionary.add_to_context_menu(browser,sub);tts.add_to_context_menu(browser,sub);field_splitter.add_to_context_menu(browser,sub)
from anki.hooks import addHook
addHook('browser.onContextMenu',_context)
def _menu(*_):
 from .content_settings import open_settings
 a=QAction('Anki Toolkit: Content…',mw);a.triggered.connect(open_settings);mw.form.menuTools.addAction(a)
 mw.addonManager.setConfigAction(__name__,open_settings)
if hasattr(gui_hooks,'main_window_did_init'):gui_hooks.main_window_did_init.append(_menu)
else:QTimer.singleShot(0,_menu)
