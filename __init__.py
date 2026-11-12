"""Anki Toolkit — one add-on: card content, word queue and upkeep."""
from anki.utils import ids2str
from aqt import gui_hooks, mw
from aqt.qt import QAction, QTimer
from aqt.utils import tooltip

from . import ai_generator, dictionary, field_splitter, tts
from . import field_hider, html_cleanup, integrations
from .common import (check_config, clear_reports, get_module_config, setup_logging, unique,
                     update_module_config)

setup_logging()
gui_hooks.profile_did_open.append(check_config)  # name hand-edit mistakes up front
gui_hooks.profile_will_close.append(clear_reports)  # report note ids belong to this profile


# Toolbar text of a pinned action; its full label is the tooltip.
_SHORT = {"Uzupełnij puste pola AI": "AI", "Nagraj audio (TTS)": "TTS",
          "📚 Kolejka słówek": "📚", "Pokaż schowane pola": "👁"}


def _editor_groups(editor):
    """Actions that fit the current note, grouped: (label, callback[, checked])."""
    return (ai_generator.workflow_actions(editor),
            ai_generator.editor_actions(editor) + dictionary.editor_actions(editor)
            + tts.editor_actions(editor),
            integrations.editor_actions(editor) + field_hider.editor_actions(editor))


def _pinned() -> list:
    """Labels of the actions the user keeps on the editor toolbar."""
    return list(get_module_config("editor", {"pinned": []})["pinned"])


def _toggle_pin(label):
    pinned = _pinned()
    pinned.remove(label) if label in pinned else pinned.append(label)
    update_module_config("editor", {"pinned": pinned})
    # Anki builds the toolbar once per editor.
    tooltip("Anki Toolkit: pasek zmieni się po ponownym otwarciu okna.", period=3000)


def _run_pinned(editor, label):
    for group in _editor_groups(editor):
        for name, callback, *_ in group:
            if name == label:
                return callback()
    tooltip(f"Anki Toolkit: „{label}” nie pasuje do tej notatki.", period=3000)


def _show_editor_menu(editor):
    """The Toolkit button: actions that fit the current note and are not on the toolbar."""
    from aqt.qt import QCursor, QMenu
    from .settings_dialog import open_settings
    menu = QMenu(editor.widget)
    groups = _editor_groups(editor)
    built = getattr(editor, "_atk_pinned", ())  # buttons this editor really has
    for group in groups:
        group = [entry for entry in group if entry[0] not in built]
        if group and menu.actions():
            menu.addSeparator()
        for label, callback, *checked in group:
            action = menu.addAction(label)
            if checked:  # toggles carry their current state
                action.setCheckable(True)
                action.setChecked(checked[0])
            action.triggered.connect(lambda _checked=False, cb=callback: cb())
    from .editor_shortcuts import edit_shortcuts, get_shortcuts
    pinned = _pinned()
    # Pinned labels that do not fit this note stay listed, so they can be unpinned.
    labels = unique([entry[0] for group in groups for entry in group] + pinned + list(get_shortcuts()))
    if labels:
        if menu.actions():
            menu.addSeparator()
        pin_menu = menu.addMenu("Przypnij do paska")
        for label in labels:
            action = pin_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(label in pinned)
            action.triggered.connect(lambda _checked=False, l=label: _toggle_pin(l))
        menu.addAction("Skróty klawiszowe…").triggered.connect(
            lambda _checked=False: edit_shortcuts(editor.parentWindow, labels))
    menu.addSeparator()
    menu.addAction("Ustawienia…").triggered.connect(lambda _checked=False: open_settings())
    menu.exec(QCursor.pos())
    menu.deleteLater()


def _editor_shortcuts(cuts, editor):
    from .editor_shortcuts import get_shortcuts
    for label, keys in get_shortcuts().items():
        # The third element skips Anki's "a field has focus" check.
        cuts.append((keys, lambda ed=editor, l=label: _run_pinned(ed, l), True))


gui_hooks.editor_did_init_shortcuts.append(_editor_shortcuts)


def _editor_buttons(buttons, editor):
    from .editor_shortcuts import get_shortcuts, native
    editor._atk_pinned = _pinned()
    prefix = dictionary.ACTION_PREFIX
    shortcuts = get_shortcuts()
    for i, label in enumerate(editor._atk_pinned):
        # Dictionaries get a letter: D = Diki, O = Oxford.
        text = label[len(prefix):][:1].upper() if label.startswith(prefix) else _SHORT.get(label, label)
        buttons.append(editor.addButton(
            None, f"anki_toolkit_pin_{i}", lambda ed=editor, l=label: _run_pinned(ed, l),
            tip=f"{label} ({native(shortcuts[label])})" if label in shortcuts else label,
            label=text, disables=False))
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
