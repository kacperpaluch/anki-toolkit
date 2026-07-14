# LLM Context — homograph_manager

## Co robi

Rozdziela w nauce **osobne notatki z tym samym słowem** o różnych znaczeniach (homografy), np. cztery notatki `assault`: *napaść* / *atak wojskowy* / *atak-krytyka* / *napadać*. Sibling Manager grupuje karty jednej notatki; ten moduł grupuje różne notatki po wartości pola kluczowego (domyślnie `ang`). W obrębie grupy aktywne jest **jedno znaczenie** — NEW karty pozostałych są zawieszone, aż aktywne dojrzeje; wtedy uwalnia się **dokładnie jedno** następne.

Ortogonalny do Sibling Managera: dotyka wyłącznie NEW kart **innych** notatek z grupy, nigdy kart notatki, na którą właśnie odpowiedziano.

## Pliki

| Plik | Rola |
|---|---|
| `logic.py` | Czysty rdzeń bez Qt/Anki-UI. `process_reactive` (po odpowiedzi), `process_group_sync` (odtworzenie niezmiennika po syncu), pomocnicze `note_key`, `group_nids`. Importuje tylko `anki.cards` (stałe typów). |
| `__init__.py` | Glue: hooki `reviewer_did_answer_card` i `sync_did_finish`, batch scan w `CollectionOp`, menu Narzędzia (`setup_menu`), „Uwolnij wszystkie" i ręczny skan. |
| `README.md` | Dokumentacja użytkownika. |

## Przepływ danych

```
Reviewer (desktop), po odpowiedzi na kartę notatki N:
  on_reviewer_did_answer_card
    → process_reactive(col, N.nid, answered.id, threshold, tag, field, ignore_tag)
        key = note_key(N, field)                       # trim + lowercase, None → noop
        others = group_nids(col, field, key, exclude=N) # find_notes('"ang:key"') + potwierdzenie w Pythonie
        answered.ivl < threshold → _suspend_others()    # zawieś NEW innych znaczeń, otaguj
        answered.ivl ≥ threshold → _release_one()        # uwolnij JEDNO znaczenie (najniższy nid), o ile slot wolny

Sync (po synchronizacji, 600 ms — po Sibling Managerze):
  on_sync_did_finish → QTimer → _run_sync_scan (CollectionOp)
    → kandydaci = is:new ∪ tag:<tag>
    → grupuj po key (każda grupa raz), pomiń grupy ≤1 notatki
    → process_group_sync(col, group, threshold, tag, field, ignore_tag)
        # odtwarza niezmiennik: aktywne = uczące się znaczenie, inaczej najniższy nid;
        # matured notatki → zdejmij tag; reszta remaining → zawieś NEW
```

## Najważniejsze niezmienniki

- **Jeden aktywny naraz.** W grupie co najwyżej jedno niedojrzałe znaczenie ma odwieszone NEW karty.
- **Uwalnianie po jednym.** Po dojrzeniu aktywnego znaczenia uwalnia się dokładnie jedno następne — nie wszystkie (inaczej kilka frontów naraz → znów interferencja). `_release_one` sortuje kandydatów po nid.
- **Slot zajęty blokuje uwolnienie.** Jeśli jakieś znaczenie już się uczy (non-NEW immature) lub ma dostępne NEW karty, `_release_one` zwraca 0.
- **Tylko cudze NEW karty.** Moduł nigdy nie tyka kart notatki, na którą odpowiedziano — to domena Sibling Managera. Dojrzałość liczona z `ivl ≥ threshold` (NEW/learning mają `ivl=0`, więc nie dają fałszywej dojrzałości).
- **Własny tag.** Zawieszenia oznaczane `tag` (domyślnie `tk-homograph-suspended`), rozłączny z tagiem Sibling Managera. `ignore_tag` wyłącza regułę dla notatki.
- **Grupowanie exact-match.** `group_nids` używa `find_notes('"field:value"')` (dokładne pole) i dodatkowo potwierdza równość w Pythonie; wartości escapowane (`\ " * _`). Zdania (inny model, całe zdanie w polu) nie zderzą się z pojedynczym słowem.
- **Idempotencja.** `process_group_sync` można uruchamiać wielokrotnie — odtwarza ten sam stan.

## Współistnienie

Sibling Manager rozkłada dwie strony jednego znaczenia; Homograph Manager rozkłada znaczenia. Sync scan homografów startuje 600 ms po syncu, czyli po scanie Sibling Managera (500 ms), by działać na ustabilizowanym stanie. Przy zmianie jednego sprawdź scenariusz współistnienia z drugim.

## Test

`tests/test_homograph_manager.py` — stub `anki.cards`, lekki `FakeCol`; pokrywa reaktywne zawieszanie/uwalnianie-po-jednym, blokadę slotu, ignore_tag i odtworzenie niezmiennika w sync.
