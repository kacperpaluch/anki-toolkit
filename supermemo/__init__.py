"""SuperMemo → talia docelowa: wypełnia proste pola nowej karty gotowymi
danymi z bazy SuperMemo, zamiast tworzyć je od zera.

Przycisk **SM** w edytorze bierze słowo z pola `match_field` (np. `ang`),
znajduje wpis w `user_files/supermemo.json` i kopiuje zmapowane pola
(`field_map`). Baza to zrzut zaimportowanych talii SuperMemo — trzymana poza
kolekcją, żeby nie obciążała synchronizacji. Audio, obrazki i przykłady są
celowo pomijane (audio dogrywasz modułem TTS).

Znaczenia: gdy słowo ma w bazie wiele wpisów (homonimy / różne poziomy),
pokazuje menu wyboru — nie zgaduje. Wypełniane są tylko puste pola docelowe,
więc to co już wpisałeś/wygenerowałeś nie jest nadpisywane.
"""

import json
import os

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import QMenu, QAction, QCursor
from aqt.editor import Editor

from ..common import ADDON_NAME, clean_html_normalized
from .logic import fields_to_fill, truncate

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "user_files", "supermemo.json")
_db_cache = None


def _get_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("supermemo", {})


def _load_db() -> dict:
    """Wczytuje bazę raz i trzyma w pamięci (~5 MB JSON, ~17 tys. haseł)."""
    global _db_cache
    if _db_cache is None:
        try:
            with open(_DB_PATH, encoding="utf-8") as fh:
                _db_cache = json.load(fh)
        except (OSError, ValueError):
            _db_cache = {}
    return _db_cache


def _fill_from(editor: Editor, sm_fields: dict, cfg: dict) -> None:
    note = editor.note
    if note is None:
        return
    existing = {k: note[k] for k in note.keys()}
    updates = fields_to_fill(
        sm_fields, existing,
        cfg.get("field_map", {}), cfg.get("match_field", "ang"),
    )
    if not updates:
        tooltip("SuperMemo: brak nowych pól do uzupełnienia.", parent=mw, period=2000)
        return
    for dst, value in updates.items():
        note[dst] = value
    editor.loadNote()
    tooltip(f"SuperMemo: uzupełniono {len(updates)} pól.", parent=mw, period=2000)


def _meaning_label(entry: dict) -> str:
    pol = clean_html_normalized(entry.get("Translation", ""))
    definition = clean_html_normalized(entry.get("Definition", ""))
    parts = [p for p in (pol, truncate(definition)) if p]
    return " · ".join(parts) or "(bez tłumaczenia)"


def _on_fetch(editor: Editor) -> None:
    cfg = _get_config()
    match_field = cfg.get("match_field", "ang")

    def start():
        note = editor.note
        if note is None or match_field not in note:
            return
        word = clean_html_normalized(note[match_field])
        if not word:
            tooltip("SuperMemo: puste pole źródłowe.", parent=mw, period=2000)
            return

        entries = _load_db().get(word.strip().lower(), [])
        if not entries:
            tooltip(f"SuperMemo: brak „{word}”.", parent=mw, period=2500)
            return
        if len(entries) == 1:
            _fill_from(editor, entries[0], cfg)
            return

        # >1 znaczenie — nie zgaduj, pokaż wybór.
        menu = QMenu(editor.widget)
        for entry in entries:
            action = QAction(_meaning_label(entry), menu)
            action.triggered.connect(
                lambda _checked=False, e=entry: _fill_from(editor, e, cfg)
            )
            menu.addAction(action)
        menu.exec(QCursor.pos())

    editor.saveNow(start)


def on_editor_buttons_init(buttons: list, editor: Editor) -> None:
    btn = editor.addButton(
        None,
        "supermemo_fill",
        lambda ed=editor: _on_fetch(ed),
        tip="Uzupełnij pola z SuperMemo",
        label="SM",
    )
    buttons.append(btn)
