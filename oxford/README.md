# Oxford 5000 — gotowe karty z eksportu talii

Przycisk **OX** w edytorze wypełnia pola nowej karty danymi z talii Oxford 5000.
Eksport ma dokładnie te same nazwy pól co typ notatki `angielski`, więc
mapowanie jest tożsamościowe — nie ma czego konfigurować.

Dane leżą w **`user_files/oxford.json`** (~10 MB, 4 946 haseł / 12 704 znaczeń),
poza kolekcją Anki — `user_files` nie synchronizuje się z AnkiWeb.

## Jak używać

1. Wpisz angielskie słowo w pole źródłowe (`ang`).
2. Kliknij **OX**.
3. Puste pola docelowe zostają uzupełnione. To, co już wpisałeś lub
   wygenerowałeś, **nie jest nadpisywane**.

### Wiele znaczeń

Prawie każde hasło ma kilka wpisów (`open` — 31). Moduł **nie zgaduje** — pokazuje
menu `poziom · tłumaczenie · początek definicji`, np. `B2 · otwarty · not closed`.
Poziom CEFR pochodzi z tagów Oxford (`Oxford::B2`) i służy tylko do wyboru w menu —
tagi **nie** są dopisywane do notatki.

## Co przenosi

Wszystkie pola eksportu poza `audio`: `pol`, `def`, `synonim`, `przyklad`,
`dodatkowe`, `cz_mowy`, `IPA`, `p1`–`p3`, `p1-nauka`–`p3-nauka`.

Audio jest pominięte świadomie: pliki MP3 zostały w paczce `.apkg` (1,27 GB),
więc referencje `[sound:...]` byłyby martwe — są wycinane z tekstu przy budowie
bazy. Wymowę dogrywasz [Słownikiem](../dictionary/README.md), przykłady
[TTS](../tts/README.md).

## Budowa bazy

`user_files/oxford.json` powstaje z eksportu notatek Anki (TSV, 19 kolumn,
`#separator:tab`, `#html:true`) — jednorazowa konwersja poza dodatkiem:
klucz to `ang` z małych liter, wartość to lista znaczeń, `[sound:...]` i puste
pola są odrzucane, poziom CEFR z tagów trafia do klucza `_level`. Klucze
zaczynające się od `_` nigdy nie są nazwą pola notatki.

## Konfiguracja

`config.json` → `"oxford": { "match_field": "ang" }` — pole, z którego brane jest
szukane słowo. Włączanie/wyłączanie modułu: **Ustawienia → System → Moduły**.

## Uwagi

- Wyszukiwanie dokładne, case-insensitive.
- Wypełniane są tylko puste pola — przycisk można kliknąć ponownie po ręcznym
  wyczyszczeniu pola, nie psując reszty karty.
- Całość lokalnie (odczyt JSON), bez sieci. Baza wczytuje się raz na sesję.
