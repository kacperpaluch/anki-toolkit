"""
Anki Toolkit — merged plugin.

Modules:
  dictionary/         — fetches pronunciation audio (MP3) and IPA from Oxford,
                        Cambridge, Diki.pl, Longman
  ai_generator/       — fills card fields using an AI provider (OpenAI / CometAPI /
                        OpenRouter / Anthropic / Google / Mistral / OpenCode Go)
  tts/                — generates MP3 audio via Kokoro TTS (local) or OpenRouter
  filtered_deck/      — creates a filtered deck with custom settings
  audio_normalizer/   — normalizes audio files using ffmpeg (EBU R128)
  nbsp_remover/       — removes &nbsp; and cleans <div> tags from card fields

Enable/disable individual modules in config.json → "modules" section.
Settings dialog: Tools → Anki Toolkit — Ustawienia
"""

from anki.hooks import addHook
from aqt import mw, gui_hooks
from aqt.qt import QTimer, QAction

from .common import ADDON_NAME, setup_logging

setup_logging()


def _enabled(name: str) -> bool:
    cfg = mw.addonManager.getConfig(ADDON_NAME) or {}
    return cfg.get("modules", {}).get(name, True)


# ---------------------------------------------------------------------------
# ai_generator
# ---------------------------------------------------------------------------
if _enabled("ai_generator"):
    from . import ai_generator
    ai_generator.migrate_workflows()  # legacy single workflow → workflows list
    gui_hooks.editor_did_init_buttons.append(ai_generator.on_editor_buttons_init)

# ---------------------------------------------------------------------------
# dictionary
# ---------------------------------------------------------------------------
if _enabled("dictionary"):
    from . import dictionary
    gui_hooks.editor_did_init_buttons.append(dictionary.on_editor_buttons_init)

# ---------------------------------------------------------------------------
# tts
# ---------------------------------------------------------------------------
if _enabled("tts"):
    from . import tts
    gui_hooks.editor_did_init_buttons.append(tts.on_editor_buttons_init)

# ---------------------------------------------------------------------------
# sibling_manager — dynamic sibling suspension (reviewer hook)
# ---------------------------------------------------------------------------
if _enabled("sibling_manager"):
    from . import sibling_manager
    gui_hooks.reviewer_did_answer_card.append(sibling_manager.on_reviewer_did_answer_card)
    gui_hooks.sync_did_finish.append(sibling_manager.on_sync_did_finish)

# ---------------------------------------------------------------------------
# deck_router — route cards to decks by tag (+ optional card template)
# ---------------------------------------------------------------------------
if _enabled("deck_router"):
    from . import deck_router
    gui_hooks.add_cards_did_add_note.append(deck_router.on_add_note)

# ---------------------------------------------------------------------------
# Browser context menu — single "Anki Toolkit" submenu
# ---------------------------------------------------------------------------
# ai_generator builds the workflows + its own (toggleable) field submenus.
# The atomic building-block sections are gated by config["context_menu"], read
# fresh on each right-click so settings changes apply without restart.
if _enabled("field_splitter"):
    from . import field_splitter

_has_context = any(
    _enabled(m) for m in ("dictionary", "ai_generator", "tts", "field_splitter")
)

if _has_context:
    def _on_browser_context_menu(browser, menu):
        cm = (mw.addonManager.getConfig(ADDON_NAME) or {}).get("context_menu", {})
        toolkit_menu = menu.addMenu("Anki Toolkit")

        if _enabled("ai_generator"):
            ai_generator.add_to_context_menu(browser, toolkit_menu)
        if _enabled("dictionary") and cm.get("dictionary", True):
            dictionary.add_to_context_menu(browser, toolkit_menu)
        if _enabled("tts") and cm.get("tts", True):
            tts.add_to_context_menu(browser, toolkit_menu)
        if _enabled("field_splitter") and cm.get("field_splitter", True):
            field_splitter.add_to_context_menu(browser, toolkit_menu)

    addHook("browser.onContextMenu", _on_browser_context_menu)

# ---------------------------------------------------------------------------
# Tools-menu modules — registered after main window is ready
# ---------------------------------------------------------------------------
_menu_modules = []
_sep = None  # sentinel for separator

if _enabled("filtered_deck"):
    from . import filtered_deck
    _menu_modules.append(filtered_deck)

_menu_modules.append(_sep)

if _enabled("audio_normalizer"):
    from . import audio_normalizer
    _menu_modules.append(audio_normalizer)

if _enabled("nbsp_remover"):
    from . import nbsp_remover
    _menu_modules.append(nbsp_remover)

if _enabled("field_splitter"):
    from . import field_splitter
    _menu_modules.append(field_splitter)

if _enabled("sibling_manager"):
    from . import sibling_manager
    _menu_modules.append(sibling_manager)

if _enabled("deck_router"):
    from . import deck_router
    _menu_modules.append(deck_router)


def _setup_menus(*_args, **_kwargs):
    from .settings import open_settings

    toolkit_menu = mw.form.menuTools.addMenu("Anki Toolkit")

    for mod in _menu_modules:
        if mod is _sep:
            toolkit_menu.addSeparator()
        else:
            mod.setup_menu(toolkit_menu)

    toolkit_menu.addSeparator()
    action = QAction("Ustawienia...", mw)
    action.triggered.connect(open_settings)
    toolkit_menu.addAction(action)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menus)
else:
    QTimer.singleShot(0, _setup_menus)
