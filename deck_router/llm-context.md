# LLM Context — Deck Router

Moduł kierowania kart do talii wg tagu notatki (+ opcjonalnie szablonu karty) w Anki Toolkit.

## Rola

Uzupełnia natywny Deck Override (który działa tylko per-szablon) o kierowanie **per-tag**. Notatka z tagiem z reguły → jej pasujące karty są przenoszone do talii z reguły. Notatka bez pasującej reguły nie jest ruszana (natywny override / bieżąca talia zostają). Pusta lista reguł = no-op.

## Pliki

```
deck_router/
├── __init__.py    # glue Anki: config, _apply(), hook add-cards, route_after_edit(), menu retro
├── logic.py       # match_deck() — czysta logika dopasowania reguły (bez importów Anki)
├── README.md      # dokumentacja użytkowa
└── llm-context.md # ten plik
```

Zakładka UI: `settings/deck_router_tab.py` (`DeckRouterTab`). Test: `tests/test_pure_logic.py` (`DeckRouterMatchTest`).

## Stack

Python 3.9+. Brak zewnętrznych zależności. Używa `col.get_note`, `note.cards()`, `card.template()`, `col.decks.id(name, create=True)`, `col.set_deck(card_ids, did)`, `col.find_notes`, `aqt.operations.CollectionOp`, `gui_hooks.add_cards_did_add_note`.

## Model danych

Reguła (dict):

```json
{"tag": "abc123", "template": "pol-ang", "deck": "Angielski::Osobne"}
```

- `tag` — wymagany; tag musi być na notatce.
- `deck` — wymagany; nazwa talii docelowej (tworzona przez `col.decks.id(..., create=True)`).
- `template` — opcjonalny; nazwa szablonu karty. Pominięty/pusty/`"*"` = wszystkie karty notatki.

Config: `config.json` → `"deck_router": {"rules": [...]}`. Toggle: `modules.deck_router`.

## Logika

### `logic.match_deck(tags, template_name, rules)` (czysta)

- Iteruje reguły po kolei — **pierwsza pasująca wygrywa**.
- Reguła pasuje, gdy `rule["tag"] in tags` **oraz** (`template` to `None`/`""`/`"*"` **lub** `template == template_name`).
- Zwraca `rule["deck"]` pierwszej pasującej reguły (o ile niepusty), inaczej `None`.
- `tags` normalizowane do `set` (akceptuje listę lub set).

### `__init__._apply(col, note_ids, rules) -> int` (mutacja kolekcji)

1. Dla każdej notatki: `tags = set(note.tags)`.
2. Dla każdej karty: `name = card.template()["name"]` (obsługuje cloze — jeden szablon, `ord` = numer cloze; indeksowanie `tmpls[card.ord]` rzucałoby `IndexError`), `deck = match_deck(tags, name, rules)`.
3. Jeśli `deck` niepusty: resolve `did` przez `col.decks.id(deck, create=True)` (cache `deck_ids` w obrębie wywołania); jeśli `card.did != did` → dodaj do `to_move[did]`.
4. `col.set_deck(cids, did)` dla każdej talii. Zwraca liczbę przeniesionych kart.
5. Karta już we właściwej talii jest pomijana (brak churnu). Karta bez dopasowania nie jest ruszana.

### `__init__._rules()`

Zwraca reguły z configu przefiltrowane do tych z niepustym `tag` i `deck` (odporność na niekompletne wiersze).

## Wejścia (entry points)

### `on_add_note(note)` — hook okna Dodaj

- `add_cards_did_add_note`. Jeśli brak reguł → return. Woła `_apply(mw.col, [note.id], rules)` **synchronicznie** w hooku (jak `nbsp_remover.on_add` woła `col.update_note`). Loguje liczbę przeniesionych. Wyjątki łapane i logowane.

### `route_after_edit(parent, note_ids)` — po AI-batchu/workflow w przeglądarce

- Wołane z `ai_generator/browser_ui.py` w `_save_changed_notes._saved` (jedyny punkt zapisu notatek po batchu/workflow), dla `[n.id for n in changed_notes]`.
- **Guard w środku**: `_module_enabled()` (bo caller importuje bezwarunkowo) + niepuste reguły + niepuste `note_ids`. Uruchamia `CollectionOp` z `_apply`; tooltip z liczbą przeniesionych, gdy `> 0`.

### `_reorganize()` / `setup_menu` — retroaktywne menu

- Query `col.find_notes(" OR ".join(f"tag:{t}" for t in tags))` po tagach z reguł → `_apply`. `CollectionOp` w tle, tooltip z liczbą przeniesionych. `_confirm_reorganize` pyta przez `QMessageBox`.

## OpChanges

`_ui_changes()` zwraca `OpChanges` z `card=True`, `study_queues=True` — po `set_deck` UI (liczniki talii, kolejki) odświeża się od razu. Gdy nic nie przeniesiono, `CollectionOp` op zwraca pusty `OpChanges()`.

## Rejestracja w root `__init__.py`

```python
if _enabled("deck_router"):
    from . import deck_router
    gui_hooks.add_cards_did_add_note.append(deck_router.on_add_note)
# ...
if _enabled("deck_router"):
    _menu_modules.append(deck_router)
```

## Integracja z ai_generator

`ai_generator/browser_ui.py` → `_save_changed_notes._saved`:

```python
try:
    from ..deck_router import route_after_edit
    route_after_edit(browser, [n.id for n in changed_notes])
except Exception:
    logger.exception("deck_router: routing po edycji nie powiódł się")
```

Soft-import + `_module_enabled()` guard: brak twardej zależności, działa też gdy moduł wyłączony (no-op).

## UI — `DeckRouterTab` (`settings/deck_router_tab.py`)

- `QTableWidget` 3 kolumny: Tag (`QTableWidgetItem` tekst), Szablon (`QComboBox` `(wszystkie)` + `_collect_templates()`), Talia (`QComboBox` edytowalny, `_collect_decks()`, `NoInsert`).
- `_collect_templates()` — union nazw szablonów ze wszystkich `mw.col.models.all()`. `_collect_decks()` — `mw.col.decks.all_names_and_ids()`.
- `apply(cfg)` — buduje `rules`; wiersze z pustym tagiem lub talią pomijane; `template == "(wszystkie)"` → nie zapisywane (pole `template` pominięte). Zarejestrowana w `settings/__init__.py` (grupa „System", ikona 🎯).

## Zależności

- `common.config.get_module_config`, `common.ADDON_NAME`.
- Brak zależności od innych modułów wtyczki (ai_generator zależy od deck_router, nie odwrotnie — przez soft-import).

## Anki API używane

- `col.get_note(nid)`, `note.tags`, `note.cards()`, `card.template()`, `card.did`, `card.id`
- `col.decks.id(name, create=True)`, `col.set_deck(card_ids, deck_id)`, `col.decks.all_names_and_ids()`
- `col.models.all()`, `col.find_notes(query)`
- `aqt.operations.CollectionOp`, `gui_hooks.add_cards_did_add_note`
