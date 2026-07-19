# LLM Context — SuperMemo (`supermemo`)

Przycisk **SM** w edytorze: bierze słowo z pola `match_field`, znajduje notatkę
typu `source_note_type` w **tej samej kolekcji** i kopiuje zmapowane pola
(`field_map`) do bieżącej notatki. Wszystko lokalnie — żadnej sieci, żadnego
wątku w tle.

## Rola

Reużywa dużych baz SuperMemo (dziesiątki tysięcy notatek) zaimportowanych do
kolekcji, zamiast budować karty od zera przez słownik / AI. Alternatywa dla
`dictionary` i `ai_generator` na etapie wypełniania pól, gdy słowo już istnieje
w SM. Audio bierze z gotowych plików SM (już w mediach) — komplementarnie do
`dictionary`, który pobiera świeże z sieci.

## Pliki

```
supermemo/
├── __init__.py     # przycisk edytora, wyszukiwanie w mw.col, menu wyboru znaczeń, zapis pól
├── logic.py        # czysta logika (bez aqt): build_query, fields_to_fill, clean_pos, truncate
├── README.md
└── llm-context.md
```

Zakładka UI: `settings/supermemo_tab.py` (Ustawienia → Integracje → SuperMemo).
Rejestracja: `__init__.py` głównego dodatku, hook `editor_did_init_buttons`.
Self-check: `tests/test_supermemo.py` (czysta logika, bez Anki).

## Przepływ

```
klik SM → editor.saveNow(start)              # webview → note (świeże 'ang')
  word = clean_html_normalized(note[match_field])
  query = build_query(source_note_type, source_match_field, word)
  nids = mw.col.find_notes(query)
    0   → tooltip "brak"
    1   → _fill_from(get_note(nids[0]))
    >1  → QMenu[_meaning_label] → _fill_from(wybrany)
_fill_from:
  updates = fields_to_fill(sm_fields, existing, field_map, match_field)
  note[dst] = value dla każdego update; editor.loadNote()
```

## Niezmienniki

- **Tylko puste pola docelowe** są wypełniane (`existing[dst].strip()` blokuje
  nadpisanie ręcznej / wygenerowanej treści). Pole `match_field` jest zawsze
  pomijane — słowo już tam jest.
- **Nie zgaduje znaczenia.** Wiele dopasowań → menu wyboru, nigdy „weź pierwsze".
- **`clean_pos`**: SuperMemo zapisuje część mowy jako `n)`, `adj)` — obcinany
  jest końcowy nawias. Reguła zaszyta w `fields_to_fill` dla źródła `PartOfSpeech`.
- **`build_query` escapuje** `\` i `"`, żeby słowo z apostrofem/cudzysłowem nie
  rozbiło składni Anki ani nie wstrzyknęło filtra.
- **Audio bez sieci**: `Sound` → `audio` to kopia tagu `[sound:...]`; plik już
  jest w mediach (zaimportowany z talią SM).

## Konfiguracja (`config.json` → `supermemo`)

```json
"supermemo": {
  "source_note_type": "SuperMemo Extreme",
  "match_field": "ang",
  "source_match_field": "English",
  "field_map": {
    "English": "ang", "Translation": "pol", "Definition": "def",
    "Synonyms": "synonim", "PartOfSpeech": "cz_mowy", "Sound": "audio"
  }
}
```

`field_map` mapuje **nazwa pola SM → nazwa pola talii**. Pole spoza mapy (np.
`Examples`, `Collocations`) jest ignorowane. Zakładka ustawień pokazuje
combo „— pomiń —" dla wyłączenia pojedynczego pola.

## Znane ograniczenia (ponytail)

- Mapowanie jest jedno, nie per typ notatki docelowej — combo pól docelowych to
  unia pól wszystkich typów. Wystarcza przy jednym schemacie SM i jednej talii.
- Menu wyboru znaczeń pokazuje wszystkie dopasowania bez sortowania po poziomie;
  dyskryminatorem jest `Translation` + skrót `Definition`.

## Jak zmieniać

- Nowe pole do przeniesienia → dopisz do `field_map` (kod nie wymaga zmian).
- Inna reguła czyszczenia wartości → rozszerz `clean_pos` / `fields_to_fill`
  w `logic.py` i dołóż asercję w `tests/test_supermemo.py`.
- Masowy import zamiast przycisku → pętla po `mw.col.find_notes` + `fields_to_fill`;
  logika mapowania jest już czysta i gotowa do reużycia.
