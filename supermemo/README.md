# SuperMemo — reużycie zaimportowanych baz

Przycisk **SM** w edytorze wypełnia pola nowej karty gotowymi danymi z baz
SuperMemo zaimportowanych do tej samej kolekcji. Zamiast tworzyć kartę od zera
(klikać po słownikach, generować AI), bierzesz to, co SuperMemo już ma:
tłumaczenie, definicję, synonimy, część mowy i wymowę.

## Jak używać

1. W oknie „Dodaj" (albo w przeglądarce) wpisz angielskie słowo w pole źródłowe
   (`ang`).
2. Kliknij **SM** w pasku edytora.
3. Puste pola docelowe zostają uzupełnione. To, co już wpisałeś lub wygenerowałeś,
   **nie jest nadpisywane**.

### Wiele znaczeń

Gdy słowo ma w SuperMemo więcej niż jeden wpis (homonimy, różne poziomy Basic /
Intermediate / Advanced), moduł **nie zgaduje** — pokazuje menu z pozycjami
`tłumaczenie · początek definicji`. Wybierasz właściwe znaczenie. Przy dokładnie
jednym dopasowaniu wypełnia od razu; przy zerowym — krótki tooltip „brak".

## Co przenosi (domyślnie)

| Pole SuperMemo | Pole talii | Uwaga |
|---|---|---|
| `English` | `ang` | pole dopasowania — pomijane przy zapisie |
| `Translation` | `pol` | |
| `Definition` | `def` | |
| `Synonyms` | `synonim` | |
| `PartOfSpeech` | `cz_mowy` | `n)` / `adj)` → `n` / `adj` (obcięty nawias) |
| `Sound` | `audio` | reużywa `[sound:...]` już obecnego w mediach — **zero sieci** |

Przykłady i IPA są celowo pomijane — generujesz je własnym pipeline'em
(Field Splitter, TTS, słownik).

## Audio

`Sound` z SuperMemo to plik MP3 już leżący w mediach kolekcji (zaimportowany
razem z talią), więc skopiowanie tagu `[sound:...]` działa natychmiast, bez
żadnego pobierania. Chcesz spójny głos z resztą talii? Zostaw `Sound` niezmapowany
i pobierz wymowę modułem [Słownik](../dictionary/README.md).

## Konfiguracja

**Ustawienia → Integracje → SuperMemo.** Wszystko jest edytowalne bez ruszania
kodu:

| Ustawienie | Znaczenie |
|---|---|
| Typ notatki SuperMemo | z której bazy czytać (`source_note_type`) |
| Pole SM z hasłem | pole SM z angielskim słowem (`source_match_field`) |
| Pole talii z hasłem | pole, z którego brane jest słowo do wyszukania (`match_field`) |
| Mapowanie pól | które pole SM trafia do którego pola talii (`field_map`); „— pomiń —" wyłącza pole |

Zmiana typu źródłowego przebudowuje listę pól na żywo.

## Uwagi

- Wyszukiwanie jest dokładne i case-insensitive (`English:słowo` w składni Anki),
  ograniczone do wybranego typu notatki.
- Wypełniane są tylko puste pola docelowe — przycisk można kliknąć ponownie po
  ręcznym wyczyszczeniu pola, nie psując reszty karty.
- Moduł działa w całości lokalnie na kolekcji (`mw.col`) — nie odpytuje sieci.
