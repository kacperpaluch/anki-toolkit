# LLM Context — homograph_manager

## Co robi

Rozdziela w nauce **osobne notatki z tym samym słowem** o różnych znaczeniach (homografy), np. cztery notatki `assault`: *napaść* / *atak wojskowy* / *atak-krytyka* / *napadać*. Wbudowany „bury siblings" Anki grupuje tylko karty jednej notatki; ten moduł grupuje **różne notatki** po wartości pola kluczowego (domyślnie `ang`), opcjonalnie ograniczone do wybranych typów notatek (`note_types`).

Cel: nie **wprowadzać** nowego znaczenia, gdy inne jest jeszcze w nauce. Znaczenie już rozpoczęte (jakakolwiek karta non-NEW, `ivl < threshold`) jest **zwolnione z bramkowania** — nigdy nie zawieszane. Bramkowane są wyłącznie znaczenia całkowicie NEW: zostają zawieszone, dopóki którekolwiek znaczenie jest w nauce; gdy żadne nie jest, uwalnia się **dokładnie jedno** następne (najniższy nid).

## Pliki

| Plik | Rola |
|---|---|
| `logic.py` | Czysty rdzeń bez Qt/Anki-UI. `process_reactive` (po odpowiedzi), `process_group_sync` (odtworzenie niezmiennika po syncu), pomocnicze `note_key`, `group_nids`, `_model_name`. Importuje tylko `anki.cards` (stałe typów). |
| `__init__.py` | Glue: hooki `reviewer_did_answer_card` i `sync_did_finish`, batch scan w `CollectionOp`, menu Narzędzia (`setup_menu`), „Uwolnij wszystkie" i ręczny skan. |
| `README.md` | Dokumentacja użytkownika. |

## Konfiguracja

`interval` (próg dojrzałości, dni), `field` (pole grupujące), `note_types` (lista modeli; **pusta = wszystkie**), `tag`, `ignore_tag`, `show_tooltip`.

## Przepływ danych

```
Reviewer (desktop), po odpowiedzi na kartę notatki N:
  on_reviewer_did_answer_card
    → process_reactive(col, N.nid, answered.id, threshold, tag, field, ignore_tag, note_types)
        key = note_key(N, field, note_types)            # trim+lowercase; None gdy poza note_types lub puste
        others = group_nids(col, field, key, exclude=N, note_types)
        answered.ivl < threshold → _suspend_others()    # zawieś NEW innych CAŁKOWICIE nowych znaczeń
        answered.ivl ≥ threshold → _release_one()        # uwolnij JEDNO znaczenie (najniższy nid), o ile slot wolny

Sync (po synchronizacji):
  on_sync_did_finish → QTimer(600 ms) → _run_sync_scan (CollectionOp)
    → kandydaci = is:new ∪ tag:<tag>
    → dla każdego: key = note_key(note, field, note_types)
        key is None + ma tag → self-heal: odwieś NEW zawieszone tej notatki, zdejmij tag (poza zakresem)
    → grupuj po key (każda grupa raz), pomiń grupy ≤1 notatki
    → process_group_sync(col, group, threshold, tag, field, ignore_tag)
```

## Najważniejsze niezmienniki

- **Nie tykać znaczeń już w nauce.** Notatka z jakąkolwiek kartą non-NEW i `ivl < threshold` jest aktywna i pomijana (`_is_learning`). Można uczyć się kilku znaczeń naraz (np. dodanych zanim moduł istniał) — żadne nie zostanie zawieszone. To była przyczyna błędu po przywróceniu modułu: stary `process_group_sync` wybierał jedno aktywne i zawieszał NEW karty pozostałych uczących się znaczeń.
- **Bramkowanie tylko całkowicie nowych.** Znaczenie all-NEW zostaje zawieszone, dopóki którekolwiek znaczenie jest w nauce. Gdy żadne nie jest — uwalnia się jedno (najniższy nid), reszta dalej zawieszona (inaczej kilka frontów naraz → znów interferencja).
- **Tylko NEW karty.** Moduł nigdy nie zawiesza kart non-NEW. Dojrzałość z `ivl ≥ threshold` (NEW/learning mają `ivl=0`).
- **Sync odwiesza tylko własne (otagowane) znaczenia.** W `process_group_sync` znaczenie jest odwieszane tylko gdy ma `tag` — karta zawieszona ręcznie (bez tagu) jest zostawiana.
- **Zakres note_types.** `note_key` zwraca None dla notatek spoza `note_types` → wypadają z grupowania. Sync self-heali otagowane notatki, które wypadły z zakresu (uwalnia + zdejmuje tag). Chroni np. talię zdań Prestonly, gdzie to samo zdanie w różnych lekcjach ma identyczne `ang`.
- **Grupowanie exact-match.** `group_nids` używa `find_notes('"field:value"')` + potwierdzenia w Pythonie; wartości escapowane (`\ " * _`).
- **Idempotencja.** `process_group_sync` można uruchamiać wielokrotnie — odtwarza ten sam stan.

## Uwaga historyczna

Moduł powstał obok `sibling_manager` (usuniętego). Stąd 600 ms opóźnienie sync scanu (dawniej: po scanie sibling_managera) — dziś to już tylko drobne odroczenie na ustabilizowany stan po syncu. Guard „odwieszaj tylko otagowane" chronił przed ping-pongiem z sibling_managerem; został, bo nadal chroni ręcznie zawieszone karty.

## Test

`tests/test_homograph_manager.py` — stub `anki.cards`, lekki `FakeCol`/`FakeNote` (z `note_type()`); pokrywa: zawieszanie nowych znaczeń, uwalnianie-po-jednym, blokadę slotu, **zwolnienie znaczeń już w nauce**, **self-heal błędnie zawieszonego**, **filtr note_types**, ignore_tag, odtworzenie niezmiennika w sync.
