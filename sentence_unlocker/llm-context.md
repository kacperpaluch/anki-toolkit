# LLM Context — sentence_unlocker

## Rola

Progresywne odblokowywanie kart-ćwiczeń „Uzupełnij" (gap-fill) przez wpisywanie znacznika do pól `pX-tak`. Szablony modelu `angielski` (`p1-nauka`/`p2-nauka`/`p3-nauka`) generują kartę tylko przy `{{#pX-tak}}{{#pX-nauka}}`. Moduł ustawia `pX-tak` **stopniowo** wg dojrzałości kart. Jednokierunkowo — znacznik nigdy nie jest usuwany (usunięcie skasowałoby wygenerowaną kartę i jej historię).

Koncepcyjne przeciwieństwo `sibling_manager` (tam: zawieszanie NEW siblingów; tu: tworzenie nowych kart po dojrzeniu).

## Pliki

| Plik | Rola |
|---|---|
| `logic.py` | Czysta logika — `process_note()`, `_tmpl_cards()`, `_finish()`. Bez importów aqt → testowalne |
| `__init__.py` | Hooki (reviewer + sync), batch scan przez `CollectionOp`, akcja menu, defaulty, `setup_menu()` |
| `README.md` | Dokumentacja użytkowa |
| `llm-context.md` | Ten plik |

## Logika (`process_note`)

Sygnatura: `process_note(col, note_id, threshold, main_templates, chain, marker, ignore_tag=None, done_tag=None) -> int` (0/1 — ile pól `-tak` nowo ustawiono; staggered ⇒ max 1 na wywołanie).

```
1. ignore_tag na notatce → return 0
2. _tmpl_cards(): mapa nazwa_szablonu -> Card dla ISTNIEJĄCYCH kart notatki
   (karta zdania istnieje dopiero po ustawieniu jej -tak → obecność = "odblokowane",
    a ivl tej karty bramkuje kolejne zdanie)
3. slots = pozycje chain, gdzie nauka_field niepuste ORAZ nauka_field/tak_field są w polach
4. brak slotów → _finish (tag done, bez zmian pól) → return 0
5. gate = wszystkie main_templates dojrzałe (ivl >= threshold)
6. iteruj sloty:
     - tak_field już ustawione → gate = dojrzałość karty tego slotu (nauka_field jako nazwa szablonu); dalej
     - pierwszy nieustawiony slot → jeśli gate: wpisz marker (unlocked=1); BREAK
       (następny slot nie ma jeszcze karty, więc nie da się go ocenić)
7. _finish: done = wszystkie sloty mają -tak; jeśli done → dodaj done_tag; update_note gdy coś zmieniono
```

Dojrzałość: `card.ivl >= threshold`. Nowe karty mają `ivl=0`, więc naturalnie nie przechodzą.

## Przepływ (hooki i batch)

```
reviewer_did_answer_card(reviewer, card, ease)
  → note = col.get_note(card.nid)
  → jeśli model(note) != cfg.model → return  (filtr modelu)
  → process_note(...) → log gdy odblokowano

sync_did_finish → QTimer 500 ms → _run_scan
  → CollectionOp op(col):
       query = '"note:{model}" -tag:{done_tag} -tag:{ignore_tag}'
       dla każdej notatki: process_note(...) (staggered — jeden krok/skan)
       zwróć _changes_for_ui() gdy coś odblokowano, inaczej pusty OpChanges()
  → on_success: log + tooltip (gated show_tooltip)

Menu: "Sentence Unlocker: przeskanuj kolekcję..." → QMessageBox → _run_scan
```

## Konfiguracja (`sentence_unlocker` w config.json)

```json
"sentence_unlocker": {
    "model": "angielski",
    "threshold": 21,
    "marker": "tak",
    "main_templates": ["ang-pol", "pol-ang"],
    "chain": [
        {"nauka_field": "p1-nauka", "tak_field": "p1-tak"},
        {"nauka_field": "p2-nauka", "tak_field": "p2-tak"},
        {"nauka_field": "p3-nauka", "tak_field": "p3-tak"}
    ],
    "ignore_tag": "tk-unlock-ignored",
    "done_tag": "tk-unlock-done",
    "show_tooltip": true
}
```

Edycja z UI: **Ustawienia → Narzędzia → Sentence Unlocker** (`settings/narzedzia_tab.py`). `main_templates` jako CSV, `chain` jako pary `nauka:tak` przez przecinki (`_csv`, `_text_to_chain`, `_chain_to_text`). Założenie: `nauka_field` == nazwa szablonu karty zdania (w modelu `angielski` się pokrywają).

## Anki API używane

- `col.get_note(nid)`, `col.card_ids_of_note(nid)`, `col.get_card(cid)`
- `col.models.get(note.mid)` — `["tmpls"][card.ord]["name"]` (mapowanie karta→szablon), `["name"]` (filtr modelu)
- `col.update_note(note)` — zapis pól + tagów; triggeruje regenerację kart
- `col.find_notes(query)` — batch
- `note.keys()` / `note[field]` / `note.has_tag` / `note.add_tag`
- `card.ivl`, `card.ord`
- `aqt.operations.CollectionOp` — batch z jednym krokiem undo
- `gui_hooks.reviewer_did_answer_card`, `gui_hooks.sync_did_finish`

## Zależności

- `common.get_module_config`
- Brak zależności od innych modułów wtyczki, brak pip packages

## Testy

`tests/test_sentence_unlocker.py` — 9 testów logiki na lekkich fake'ach (col/note/card): dojrzałość mainów, staggered odblokowywanie, bramka poprzedniej karty, pomijanie pustych zdań, done-tag, ignore-tag.

## Rejestracja w root `__init__.py`

```python
if _enabled("sentence_unlocker"):
    from . import sentence_unlocker
    gui_hooks.reviewer_did_answer_card.append(sentence_unlocker.on_reviewer_did_answer_card)
    gui_hooks.sync_did_finish.append(sentence_unlocker.on_sync_did_finish)
# ...
if _enabled("sentence_unlocker"):
    from . import sentence_unlocker
    _menu_modules.append(sentence_unlocker)
```
