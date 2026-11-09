"""Anki Toolkit — one add-on: card content, word queue and upkeep."""
from anki.utils import ids2str
from aqt import gui_hooks, mw
from aqt.qt import QAction, QTimer

from . import ai_generator, dictionary, field_splitter, tts
from . import field_hider, html_cleanup, integrations
from .common import check_config, clear_reports, setup_logging

setup_logging()
gui_hooks.profile_did_open.append(check_config)  # name hand-edit mistakes up front
gui_hooks.profile_will_close.append(clear_reports)  # report note ids belong to this profile


def _show_editor_menu(editor):
    """One editor button: actions that fit the current note, grouped."""
    from aqt.qt import QCursor, QMenu
    from .settings_dialog import open_settings
    menu = QMenu(editor.widget)
    groups = (ai_generator.workflow_actions(editor),
              ai_generator.editor_actions(editor) + dictionary.editor_actions(editor)
              + tts.editor_actions(editor),
              integrations.editor_actions(editor) + field_hider.editor_actions(editor),
              [("Ustawienia…", open_settings)])
    for group in filter(None, groups):
        if menu.actions():
            menu.addSeparator()
        for label, callback in group:
            menu.addAction(label).triggered.connect(lambda _checked=False, cb=callback: cb())
    menu.exec(QCursor.pos())
    menu.deleteLater()


def _editor_buttons(buttons, editor):
    ai_generator.on_editor_buttons_init(buttons, editor)  # workflows with their own button
    buttons.append(editor.addButton(
        None, "anki_toolkit_menu", _show_editor_menu, tip="Anki Toolkit",
        label="Toolkit ▾", disables=False))  # usable before any field has focus


gui_hooks.editor_did_init_buttons.append(_editor_buttons)


def _context(browser, menu):
    from .ai_generator.workflow import get_context_menu
    nids = browser.selected_notes()
    if not nids or mw.col is None:
        return
    # The menus depend only on note type and tags, so one note per combination
    # stands for the selection — reading 30k selected notes froze the right click.
    notes = [mw.col.get_note(nid) for nid in mw.col.db.list(
        f"select min(id) from notes where id in {ids2str(nids)} group by mid, tags")]
    sub = menu.addMenu("Anki Toolkit")
    cm = get_context_menu()
    ai_generator.add_to_context_menu(browser, sub, notes=notes)
    for key, module in (("dictionary", dictionary), ("tts", tts),
                        ("field_splitter", field_splitter)):
        if cm.get(key, True):
            module.add_to_context_menu(browser, sub, notes=notes)
    if sub.isEmpty():
        menu.removeAction(sub.menuAction())


gui_hooks.browser_will_show_context_menu.append(_context)


def _setup_menu(*_):
    from .settings_dialog import open_settings

    menu = mw.form.menuTools.addMenu("Anki Toolkit")
    def add_actions(target, entries):
        for title, callback in entries:
            action = QAction(title, target)
            # QAction passes checked(bool), never a settings page name.
            action.triggered.connect(lambda _checked=False, callback=callback: callback())
            target.addAction(action)

    add_actions(menu, (
        ("Kolejka słówek (n8n)…", integrations.open_queue),
        ("Ustawienia…", open_settings),
    ))
    operations = menu.addMenu("Operacje na kolekcji")
    add_actions(operations, (
        ("Rozdziel pola w kolekcji…", field_splitter.run_on_collection),
        ("Wyczyść HTML w kolekcji…", html_cleanup.confirm_collection_cleanup),
    ))
    # Anki otwiera edytor JSON, gdy akcja zwróci False — stąd zawsze `None`
    # (`open_settings() and None` dawało False po „Anuluj”).
    def config_action():
        open_settings()
    mw.addonManager.setConfigAction(__name__, config_action)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup_menu)
else:
    QTimer.singleShot(0, _setup_menu)
