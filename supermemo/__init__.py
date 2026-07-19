"""SuperMemo → talia docelowa: wypełnia proste pola nowej karty gotowymi
danymi z zaimportowanych baz SuperMemo, zamiast tworzyć je od zera.

Przycisk **SM** w edytorze bierze słowo z pola `match_field` (np. `ang`),
znajduje notatkę SuperMemo w tej samej kolekcji i kopiuje zmapowane pola
(`field_map`). Audio (`Sound`) reużywa plików już obecnych w mediach — zero
zapytań do sieci. Przykłady i IPA są celowo pomijane (generujesz je osobno).

Znaczenia: gdy słowo ma w SM wiele wpisów (homonimy / różne poziomy),
pokazuje menu wyboru — nie zgaduje. Wypełniane są tylko puste pola docelowe,
więc to co już wpisałeś/wygenerowałeś nie jest nadpisywane.
"""

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import QMenu, QAction, QCursor
from aqt.editor import Editor

from ..common import ADDON_NAME, clean_html_normalized
from .logic import build_query, fields_to_fill, truncate


def _get_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("supermemo", {})


def _fill_from(editor: Editor, sm_note, cfg: dict) -> None:
    note = editor.note
    if note is None:
        return
    existing = {k: note[k] for k in note.keys()}
    sm_fields = {k: sm_note[k] for k in sm_note.keys()}
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


def _meaning_label(sm_note) -> str:
    pol = clean_html_normalized(sm_note["Translation"]) if "Translation" in sm_note else ""
    definition = clean_html_normalized(sm_note["Definition"]) if "Definition" in sm_note else ""
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

        query = build_query(
            cfg.get("source_note_type", "SuperMemo Extreme"),
            cfg.get("source_match_field", "English"),
            word,
        )
        nids = list(mw.col.find_notes(query))
        if not nids:
            tooltip(f"SuperMemo: brak „{word}”.", parent=mw, period=2500)
            return
        if len(nids) == 1:
            _fill_from(editor, mw.col.get_note(nids[0]), cfg)
            return

        # >1 znaczenie — nie zgaduj, pokaż wybór.
        menu = QMenu(editor.widget)
        for nid in nids:
            sm_note = mw.col.get_note(nid)
            action = QAction(_meaning_label(sm_note), menu)
            action.triggered.connect(
                lambda _checked=False, n=sm_note: _fill_from(editor, n, cfg)
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
