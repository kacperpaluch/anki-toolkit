"""TTS module (Kokoro / OpenRouter) — Anki browser menu/hook integration."""

from aqt.qt import QAction, QMenu
from aqt.utils import tooltip

from .processor import process_task_async, process_tasks_async
from .config import get_tts_config, get_tasks
from .editor_ui import on_editor_buttons_init


def add_to_context_menu(browser, menu: QMenu):
    config = get_tts_config()
    tasks = get_tasks(config)

    if not tasks:
        return

    tts_menu = menu.addMenu("TTS")

    for i, task in enumerate(tasks):
        label = task.get("label", f"Zadanie {i + 1}")
        action = QAction(label, browser)
        action.triggered.connect(_make_runner(browser, task))
        tts_menu.addAction(action)

    if len(tasks) > 1:
        tts_menu.addSeparator()
        all_action = QAction("Uruchom wszystkie", browser)
        all_action.triggered.connect(_make_run_all(browser, tasks))
        tts_menu.addAction(all_action)


def _make_runner(browser, task: dict):
    def _run():
        nids = browser.selected_notes()
        if not nids:
            tooltip("Nie zaznaczono żadnych notatek.")
            return
        process_task_async(browser, nids, task)
    return _run


def _make_run_all(browser, tasks: list):
    def _run():
        nids = browser.selected_notes()
        if not nids:
            tooltip("Nie zaznaczono żadnych notatek.")
            return
        process_tasks_async(browser, nids, tasks)
    return _run
