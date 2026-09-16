"""Integrations — n8n Word Queue, four-dictionary panel and local Web Bridge."""
from aqt import gui_hooks

from . import bridge, word_queue
from .word_queue import open_queue

gui_hooks.add_cards_did_add_note.append(word_queue.on_add_note)
gui_hooks.editor_did_init_buttons.append(word_queue.on_editor_buttons_init)
gui_hooks.profile_did_open.append(bridge.start_server)
gui_hooks.editor_did_load_note.append(bridge.track_editor)
gui_hooks.profile_will_close.append(bridge.forget_editor)
