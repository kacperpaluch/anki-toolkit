# LLM Context — SuperMemo (`supermemo`)

Przycisk **SM** w edytorze: bierze słowo z pola `match_field`, znajduje wpis w
**`user_files/supermemo.json`** (zrzut baz SuperMemo) i kopiuje zmapowane pola
(`field_map`) do bieżącej notatki. Wszystko lokalnie — żadnej sieci, żadnego
wątku w tle.

## Rola

Reużywa dużych baz SuperMemo (dziesiątki tysięcy haseł) bez trzymania ich w
kolekcji Anki — dane leżą w `user_files` (nie synchronizują się z AnkiWeb, więc
nie obciążają sync). Alternatywa dla `dictionary` i `ai_generator` na etapie
wypełniania pól, gdy słowo już istnieje w bazie SM. Audio, obrazki i przykłady
są celowo pominięte w zrzucie — audio dogrywasz modułem `tts`.

## Pliki

```
supermemo/
├── __init__.py     # przycisk edytora, lookup w JSON (cache), menu wyboru znaczeń, zapis pól
├── logic.py        # czysta logika (bez aqt): fields_to_fill, clean_pos, truncate
├── README.md
└── llm-context.md
```

Baza: `user_files/supermemo.json` — `{ słowo_lower: [ {pola SM}, ... ] }`,
lista bo homonimy / różne znaczenia. Klucz to `English.lower().strip()`.
Zakładka UI: `settings/supermemo_tab.py` (Ustawienia → Integracje → SuperMemo).
Rejestracja: `__init__.py` głównego dodatku, hook `editor_did_init_buttons`.
Self-check: `tests/test_supermemo.py` (czysta logika, bez Anki).

## Przepływ

```
klik SM → editor.saveNow(start)              # webview → note (świeże 'ang')
  word = clean_html_normalized(note[match_field])
  entries = _load_db().get(word.strip().lower(), [])
    0   → tooltip "brak"
    1   → _fill_from(entries[0])
    >1  → QMenu[_meaning_label] → _fill_from(wybrany)
_fill_from:
  updates = fields_to_fill(sm_fields, existing, field_map, match_field)
  note[dst] = value dla każdego update; editor.loadNote()
```

`_load_db()` czyta JSON raz i trzyma w module-level cache (`_db_cache`).

## Niezmienniki

- **Tylko puste pola docelowe** są wypełniane (`existing[dst].strip()` blokuje
  nadpisanie ręcznej / wygenerowanej treści). Pole `match_field` jest zawsze
  pomijane — słowo już tam jest.
- **Nie zgaduje znaczenia.** Wiele wpisów → menu wyboru, nigdy „weź pierwsze".
- **`clean_pos`**: SuperMemo zapisuje część mowy jako `n)`, `adj)` — obcinany
  jest końcowy nawias. Reguła zaszyta w `fields_to_fill` dla źródła `PartOfSpeech`.
- **Bez sieci**: cały lookup to odczyt lokalnego JSON.

## Konfiguracja (`config.json` → `supermemo`)

```json
"supermemo": {
  "source_note_type": "SuperMemo Extreme",
  "match_field": "ang",
  "source_match_field": "English",
  "field_map": {
    "English": "ang", "Translation": "pol", "Definition": "def",
    "Synonyms": "synonim", "PartOfSpeech": "cz_mowy"
  }
}
```

`field_map` mapuje **nazwa pola SM → nazwa pola talii**; klucze to nazwy pól w
JSON (`Translation`, `Definition`, `Synonyms`, `PartOfSpeech`). `source_note_type`
/ `source_match_field` napędzają już tylko listę pól w zakładce ustawień (model
`SuperMemo Extreme` zostaje w kolekcji jako pusty, żeby UI miało skąd wziąć nazwy
pól). Zakładka pokazuje combo „— pomiń —" dla wyłączenia pojedynczego pola.

## Znane ograniczenia (ponytail)

- Zrzut do JSON jest jednorazowy (skrypt eksportu). Nowy import SM → trzeba
  odświeżyć `supermemo.json`. Realnie baza jest stabilna, więc nie ma automatu.
- Mapowanie jest jedno, nie per typ notatki docelowej — combo pól docelowych to
  unia pól wszystkich typów. Wystarcza przy jednym schemacie SM i jednej talii.
- Menu wyboru znaczeń pokazuje wszystkie wpisy bez sortowania po poziomie;
  dyskryminatorem jest `Translation` + skrót `Definition`.

## Jak zmieniać

- Nowe pole do przeniesienia → dopisz do `field_map` **i** dodaj je do listy
  `KEEP` w skrypcie eksportu, potem odśwież JSON.
- Inna reguła czyszczenia wartości → rozszerz `clean_pos` / `fields_to_fill`
  w `logic.py` i dołóż asercję w `tests/test_supermemo.py`.
