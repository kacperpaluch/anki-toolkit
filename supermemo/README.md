# SuperMemo — reużycie zaimportowanych baz

Przycisk **SM** w edytorze wypełnia pola nowej karty gotowymi danymi z baz
SuperMemo. Zamiast tworzyć kartę od zera (klikać po słownikach, generować AI),
bierzesz to, co SuperMemo już ma: tłumaczenie, definicję, synonimy i część mowy.

Dane leżą w **`user_files/supermemo.json`** — zrzucie baz SuperMemo trzymanym
poza kolekcją Anki. Dzięki temu ~28 tys. haseł nie obciąża synchronizacji z
AnkiWeb (pliki `user_files` się nie synchronizują), a kolekcja zostaje lekka.

## Jak używać

1. W oknie „Dodaj" (albo w przeglądarce) wpisz angielskie słowo w pole źródłowe
   (`ang`).
2. Kliknij **SM** w pasku edytora.
3. Puste pola docelowe zostają uzupełnione. To, co już wpisałeś lub wygenerowałeś,
   **nie jest nadpisywane**.

### Wiele znaczeń

Gdy słowo ma w bazie więcej niż jeden wpis (homonimy, różne poziomy Basic /
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

Audio, obrazki i przykłady są celowo pominięte w zrzucie — audio dogrywasz
modułem [TTS](../tts/README.md), przykłady własnym pipeline'em (Field Splitter).

## Budowa / odświeżenie bazy

`user_files/supermemo.json` powstaje ze skryptu `supermemo/export.py`. Odpal go,
gdy zaimportujesz nową bazę SuperMemo do kolekcji (Anki + AnkiConnect włączone):

```
python3 supermemo/export.py
```

Skrypt czyta notatki typu `SuperMemo Extreme` i zapisuje pola tekstowe do JSON.
Po eksporcie możesz usunąć notatki SuperMemo z kolekcji — moduł już ich nie
potrzebuje. **Zostaw sam typ notatki** (pusty) — zakładka ustawień używa go do
listy pól przy mapowaniu.

## Konfiguracja

**Ustawienia → Integracje → SuperMemo.** Wszystko jest edytowalne bez ruszania
kodu:

| Ustawienie | Znaczenie |
|---|---|
| Typ notatki SuperMemo | z którego typu brać nazwy pól do mapowania (`source_note_type`) |
| Pole SM z hasłem | pole SM z angielskim słowem (`source_match_field`) |
| Pole talii z hasłem | pole, z którego brane jest słowo do wyszukania (`match_field`) |
| Mapowanie pól | które pole SM trafia do którego pola talii (`field_map`); „— pomiń —" wyłącza pole |

## Uwagi

- Wyszukiwanie jest dokładne i case-insensitive (klucz = `English` z małych liter).
- Wypełniane są tylko puste pola docelowe — przycisk można kliknąć ponownie po
  ręcznym wyczyszczeniu pola, nie psując reszty karty.
- Moduł działa w całości lokalnie (odczyt JSON) — nie odpytuje sieci.
