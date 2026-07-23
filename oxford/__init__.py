"""Oxford 5000 → talia docelowa: wypełnia pola nowej karty gotowymi danymi
z eksportu talii Oxford5000 (te same nazwy pól co typ `angielski`).

Przycisk **OX** w edytorze bierze słowo z pola `match_field` (domyślnie `ang`),
znajduje wpisy w `user_files/oxford.json` i kopiuje wszystkie pasujące pola,
które w notatce są puste. Baza leży poza kolekcją, żeby nie obciążała sync.

Znaczenia: jedno słowo ma zwykle kilka (a `open` 31) wpisów — moduł nie zgaduje,
pokazuje menu `poziom · tłumaczenie · początek definicji`. Audio jest pomijane
(referencje [sound:...] wycięte przy budowie bazy) — dogrywasz je modułem TTS
albo Słownikiem.
"""

import json
import os

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import QMenu, QAction, QCursor
from aqt.editor import Editor

from ..common import ADDON_NAME, clean_html_normalized
from .logic import fields_to_fill, truncate

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "user_files", "oxford.json")
_db_cache = None


def _get_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("oxford", {})


def _load_db() -> dict:
    """Wczytuje bazę raz i trzyma w pamięci (~10 MB JSON, ~5 tys. haseł)."""
    global _db_cache
    if _db_cache is None:
        try:
            with open(_DB_PATH, encoding="utf-8") as fh:
                _db_cache = json.load(fh)
        except (OSError, ValueError):
            _db_cache = {}
    return _db_cache


def _fill_from(editor: Editor, entry: dict, match_field: str) -> None:
    note = editor.note
    if note is None:
        return
    existing = {k: note[k] for k in note.keys()}
    updates = fields_to_fill(entry, existing, match_field)
    if not updates:
        tooltip("Oxford: brak nowych pól do uzupełnienia.", parent=mw, period=2000)
        return
    for dst, value in updates.items():
        note[dst] = value
    editor.loadNote()
    tooltip(f"Oxford: uzupełniono {len(updates)} pól.", parent=mw, period=2000)


def _meaning_label(entry: dict) -> str:
    parts = [
        entry.get("_level", ""),
        clean_html_normalized(entry.get("pol", "")),
        truncate(clean_html_normalized(entry.get("def", ""))),
    ]
    return " · ".join(p for p in parts if p) or "(bez tłumaczenia)"


def _on_fetch(editor: Editor) -> None:
    match_field = _get_config().get("match_field", "ang")

    def start():
        note = editor.note
        if note is None or match_field not in note:
            return
        word = clean_html_normalized(note[match_field])
        if not word:
            tooltip("Oxford: puste pole źródłowe.", parent=mw, period=2000)
            return

        entries = _load_db().get(word.strip().lower(), [])
        if not entries:
            tooltip(f"Oxford: brak „{word}”.", parent=mw, period=2500)
            return
        if len(entries) == 1:
            _fill_from(editor, entries[0], match_field)
            return

        # >1 znaczenie — nie zgaduj, pokaż wybór.
        menu = QMenu(editor.widget)
        for entry in entries:
            action = QAction(_meaning_label(entry), menu)
            action.triggered.connect(
                lambda _checked=False, e=entry: _fill_from(editor, e, match_field)
            )
            menu.addAction(action)
        menu.exec(QCursor.pos())

    editor.saveNow(start)


def on_editor_buttons_init(buttons: list, editor: Editor) -> None:
    btn = editor.addButton(
        None,
        "oxford_fill",
        lambda ed=editor: _on_fetch(ed),
        tip="Uzupełnij pola z Oxford 5000",
        label="OX",
    )
    buttons.append(btn)
