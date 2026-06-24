# LLM Context — Sibling Manager

Moduł dynamicznego zawieszania kart-siblingów w Anki Toolkit.

Inspiracja: [SibPush — Delay New Sibs](https://github.com/DerDemystifier/SibPush_Delay-New-Sibs)

## Rola

Reaktywne zarządzanie siblingami — po odpowiedzi na kartę zawiesza pozostałe NEW siblingi dopóki aktywna karta nie dojrzeje. Alternatywa dla SibPush: zamiast pre-suspendować wg kolejności szablonów, suspenduje reaktywnie — większa losowość, Anki decyduje co pokazać następnym.

Sync catch-up: po synchronizacji z telefonu/AnkiWeb, batch scan przetwarza wszystkie notatki z NEW siblingami (hook `sync_did_finish`).

## Pliki

```
sibling_manager/
├── __init__.py    # hook reviewer'a + sync hook + akcje menu Narzędzia
├── logic.py       # process_note() + process_note_sync() — czysta logika
├── README.md      # dokumentacja użytkowa
└── llm-context.md # ten plik
```

## Stack

Python 3.9+. Brak zewnętrznych zależności. Używa `anki.cards` (CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED), `col.sched.suspend_cards/unsuspend_cards`, `col.update_note`, `aqt.operations.CollectionOp`.

## Hooki

```python
gui_hooks.reviewer_did_answer_card.append(on_reviewer_did_answer_card)
gui_hooks.sync_did_finish.append(on_sync_did_finish)
```

- `reviewer_did_answer_card` — po odpowiedzi na desktopie → `process_note` (reactive)
- `sync_did_finish` — po synchronizacji → 500 ms delay → `_run_sync_scan` → `process_note_sync` (batch)

## Logika

### `process_note` (reactive — reviewer hook)

1. Pobierz siblingi notatki
2. Jeśli `ignore_tag` → pomiń (zwróć `(0, 0)`)
3. Jeśli liczba kart ≤ 1 → pomiń
4. `answered.ivl < interval` → zawieś wszystkie NEW siblingi + dodaj tag
5. `answered.ivl >= interval` → uwolnij wszystkie zawieszone NEW siblingi
6. Cleanup tagu jeśli nie ma już zawieszonych kart
7. Zwróć `(suspended, unsuspended)` — liczby zawieszonych/odwieszonych kart

### `process_note_sync` (batch — sync catch-up)

Nie wie która karta została odpowiedziana, więc sprawdza wszystkie non-NEW karty:
1. Pobierz siblingi notatki
2. Jeśli `ignore_tag` → pomiń (zwróć `(0, 0)`)
3. Jeśli liczba kart ≤ 1 → pomiń
4. Jeśli brak NEW kart → cleanup tagu i return `(0, 0)`
5. Jeśli jakakolwiek non-NEW karta immature (ivl < threshold) → zawieś NEW siblingi
6. Jeśli wszystkie non-NEW karty mature → uwolnij zawieszone NEW siblingi
7. Jeśli brak non-NEW kart (wszystkie NEW) → nic nie rób (brak recenzji)
8. Cleanup tagu
9. Zwróć `(suspended, unsuspended)`

### `_run_sync_scan` (batch runner)

- Query: `is:new` ∪ `tag:{tag}` → notatki z NEW kartami lub z naszym tagiem
- SQL filter: `HAVING COUNT(*) > 1` (tylko notatki z >1 kartą)
- Każda notatka → `process_note_sync`, liczniki agregowane (`suspended`, `unsuspended`, `notes`)
- Działa w tle przez `CollectionOp` (jeden krok undo)
- Zwraca `_changes_for_ui()` (OpChanges z `card`/`note`/`study_queues = True`) gdy coś zawieszono/odwieszono, inaczej pusty `OpChanges()` — pusty obiekt po realnej mutacji zostawiał UI nieodświeżony (liczniki talii/kolejki/przeglądarka) do następnej nawigacji; undo i tak rejestrują `suspend_cards`/`update_note`, zwrócony OpChanges steruje tylko odświeżaniem UI
- Po zakończeniu: `log.info` z podsumowaniem + tooltip `"Sibling Manager: zawieszono X, odwieszono Y"` (gated przez `show_tooltip`, tylko gdy coś zrobiono)

### `_unsuspend_all` / `_changes_for_ui` (Tools menu — escape hatch)

- `_unsuspend_all` odwiesza karty `tag:{tag} is:suspended` i zdejmuje tag z notatek; po mutacji zwraca `_changes_for_ui()` (nie pusty `OpChanges()`), więc UI odświeża się od razu
- `_changes_for_ui()` — helper zwracający `OpChanges` z flagami `card`/`note`/`study_queues`; współdzielony przez `_run_sync_scan` i `_unsuspend_all`

### `on_reviewer_did_answer_card` (reviewer hook)

- Wywołuje `process_note`, unpackuje `(suspended, unsuspended)`
- `log.info` z licznikami i `nid` gdy coś zrobiono (no tooltip — nie spamować przy każdej karcie)

## Konfiguracja

```json
"sibling_manager": {
    "interval": 30,
    "tag": "tk-sib-suspended",
    "ignore_tag": "tk-sib-ignored",
    "show_tooltip": true
}
```

Edycja: **Ustawienia → Narzędzia → Sibling Manager** (sekcja w `narzedzia_tab.py`). Włączenie/wyłączenie modułu: **Ustawienia → Moduły** (`config.json` → `modules.sibling_manager`).

## Zależności

- `common.config.get_module_config` — konfiguracja
- Brak zależności od innych modułów wtyczki

## Rejestracja w root `__init__.py`

```python
if _enabled("sibling_manager"):
    from . import sibling_manager
    gui_hooks.reviewer_did_answer_card.append(sibling_manager.on_reviewer_did_answer_card)
    gui_hooks.sync_did_finish.append(sibling_manager.on_sync_did_finish)
# ...
if _enabled("sibling_manager"):
    _menu_modules.append(sibling_manager)
```

## Anki API używane

- `col.get_note(nid)` — pobierz notatkę
- `col.card_ids_of_note(nid)` — IDs kart notatki
- `col.get_card(cid)` — pobierz kartę
- `col.update_note(note)` — zapisz zmiany notatki (tagi)
- `col.sched.suspend_cards([ids])` — zawieś karty
- `col.sched.unsuspend_cards([ids])` — odwieś karty
- `col.find_cards(query)` / `col.find_notes(query)` — wyszukiwanie
- `col.db.list(sql)` — SQL dla batch filter (>1 card)
- `aqt.operations.CollectionOp` — batch operacja z undo
- `note.has_tag(tag)` / `note.add_tag(tag)` / `note.remove_tag(tag)`
- `card.type`, `card.queue`, `card.ivl`, `card.id`

## Kluczowe stałe

- `CARD_TYPE_NEW` — typ nowej karty (z `anki.cards`)
- `QUEUE_TYPE_SUSPENDED` — stan zawieszenia (z `anki.cards`)
