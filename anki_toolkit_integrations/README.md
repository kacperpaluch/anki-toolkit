# Anki Toolkit: Integrations

Pełna integracja z kolejką n8n: panel 📚 przy oknie Dodaj, adres domowy i
fallback Tailscale, odhaczanie wierszy po dodaniu karty, zakładki słowników oraz
lokalny Web Bridge wpisujący dane do otwartej notatki.

Ustawienia: **Narzędzia → Anki Toolkit: Integrations → Ustawienia…**.

Mostek słucha na `127.0.0.1:8767` (klucz `web_bridge.port` w konfiguracji).
Ten sam port musi być w stałej `ENDPOINT` userscriptu — po zmianie przeładuj
`dictionaries-to-anki.user.js` w menedżerze userscriptów. 8765 i 8766 należą do
AnkiConnect i jego forków; gdy port jest zajęty, Anki pokazuje ostrzeżenie
przy starcie profilu.

Mostek zapisuje bufor edytora przed wypełnieniem pól. Żądanie jest związane
z konkretną notatką i profilem; timeout anuluje oczekującą zmianę.
Przy zmianie słowa w rozpoczętej notatce panel pyta o zgodę i zachowuje inne pola.
Tasowanie i odświeżanie zachowują aktualnie wybraną pozycję, jeśli nadal istnieje.

Wiersz jest automatycznie odhaczany tylko po dodaniu notatki powiązanej z tą
pozycją i z odpowiadającym jej hasłem. Jeśli zmienisz formę hasła, np. z
„sprawling” na „sprawl”, użyj ręcznie **Zrobione →**. Checkbox jest blokowany
na czas zapisu; brak trafionego wiersza jest błędem, a nie sukcesem.
Odświeżenie listy jest dostępne po zakończeniu zapisów. Po zmianie ustawień
zamknij całe okno Dodaj i otwórz panel ponownie; zapamiętany adres n8n jest
używany wyłącznie, jeśli nadal znajduje się w aktualnej konfiguracji.

## AI: znaczenia → karty

Przycisk **AI: znaczenia** w pasku panelu robi z jednego hasła tyle kart, ile
ma ono znaczeń. Bierze tekst otwartych zakładek (diki + Oxford/Longman),
prosi model o dopasowanie polskich znaczeń do angielskich definicji i pokazuje
listę propozycji z checkboxami oraz edytowalnymi polami polskiego znaczenia,
definicji i przykładu. Linki do diki i wskazanego źródła otwierają przeglądarkę.
Puste polskie znaczenie blokuje zatwierdzenie zaznaczonej propozycji. Ręczne
poprawki trafiają do tagu do weryfikacji; nie są ponownie sprawdzane jako cytaty.
Puste ustawienie „Pole przykładu” wyłącza przykłady w prompcie i podglądzie;
ewentualny przykład zwrócony mimo to przez model jest pomijany.
Anulowanie odrzuca poprawki. Zatwierdzone znaczenia lądują jako osobne
notatki w talii i typie wybranym w oknie „Dodaj", a wiersz w n8n jest odhaczany.

**Cytaty są sprawdzane względem źródła.** Definicja i przykład muszą
występować w tekście wskazanego angielskiego słownika; polskie odpowiedniki
(rozdzielone przecinkami lub średnikami) w diki. Sprawdzany jest ten sam,
przycięty tekst, który otrzymał model. Brak polskiego cytatu odrzuca znaczenie,
brak angielskiego zostawia pustą definicję. To kontrola pochodzenia tekstu,
nie gwarancja zgodności znaczeń — sprawdź propozycje przed zatwierdzeniem.

Zmiana słowa lub notatki podczas oczekiwania unieważnia wynik AI. Paczka
jest przygotowywana przed zapisem i dodawana jedną transakcją Anki, z jednym
krokiem cofnięcia. Zwykły tekst jest zabezpieczony przed interpretacją jako HTML.

**Brak dopasowania 1:1 nie blokuje karty.** Znaczenie bez angielskiej definicji
dostaje pustą definicję, a nie zmyśloną. Każda karta z AI dostaje **dokładnie
jeden** tag: pewne dopasowanie *Tag pewnych dopasowań* (domyślnie `ai-auto`),
wszystko pozostałe *Tag do weryfikacji* (`ai-review`). Tagi się nie nakładają,
więc `tag:ai-review` w Browserze to cała robota do przejrzenia, a `tag:ai-auto`
oznacza dopasowania ocenione przez model jako pewne, nie niezależnie zweryfikowane.

**Definicje pochodzą ze wszystkich zakładek naraz.** Do promptu idzie tekst
każdej zakładki, która ma URL w wierszu n8n (`link_columns`); model sam
wybiera, z którego słownika wziąć definicję, i zapisuje to w polu `src`
widocznym w oknie wyboru. Nie ma stałego pierwszeństwa słownika.

Reszta pól (audio, IPA, TTS, przykłady) to zadanie dla workflowu z dodatku
Content: zaznacz świeże notatki w Browserze i uruchom go na zaznaczeniu.

Wszystko ustawiasz w **Narzędzia → Anki Toolkit: Integrations → Ustawienia…**,
sekcja *AI: znaczenia*: dostawca i model z rozwijanek (lista pochodzi
z dodatku **Content** — to on trzyma klucze, więc `claude_cli` / `codex_cli`
jadą na Twojej subskrypcji), limit znaczeń, limit czasu, oba tagi i nazwy pól
notatki. Pole angielskie to *Pole notatki* z sekcji n8n — nie duplikuje się.

## Słownik lokalny (StarDict)

Czytnik offline'owego słownika StarDict — **niezależny od kolejki n8n**.
Otwierasz go z **Narzędzia → Anki Toolkit: Integrations → Słownik lokalny…**
albo przyciskiem **📖** w edytorze (wtedy podpowiada hasłem z pola notatki).
Kolejka, konfiguracja n8n ani panel 📚 nie są do niczego potrzebne.

Artykuł jest rozbity na osobne znaczenia i zwroty; **każde ma własny przycisk**,
który wysyła do otwartej notatki **tylko to jedno znaczenie** — nie cały artykuł.
Do pola notatki idzie samo tłumaczenie: kwalifikatory (`pot.`, `tech.`),
przykłady po ➤ i odsyłacze po `=` zostają na ekranie. Checkbox *dokleja do pola*
decyduje, czy kolejne kliknięcie dopisuje znaczenie, czy nadpisuje pole.
Odsyłacze w artykule są klikalne, a wyszukiwarka zna formy odmienione z `.syn`
(`ran` → `run`). Samo czytanie działa zawsze; wstawianie wymaga otwartego okna
„Dodaj", bo tam pisze mostek.

Bazę budujesz raz, offline — pliki źródłowe słownika zostają nietknięte:

```
python anki_toolkit_integrations/local_dict.py ~/Słowniki/slownik/dictionary.ifo
```

Powstaje `user_files/stardict.sqlite` (czytany z dysku, nie ładowany do RAM).
Bez tego pliku czytnik pokazuje instrukcję, a zakładka w panelu 📚 się nie pojawia.

Konfiguracja w sekcji `local_dict`: `label` (etykieta zakładki w panelu),
`fields` (pola notatki dostające znaczenie) i `headword_field` (pole na hasło
oraz na zwrot — z nim jedno kliknięcie robi kartę idiomu).

Strona czytnika jest serwowana przez mostek (`GET /dict`), więc ma jego origin.
Mostek wpuszcza POST-y **dokładnie z tego portu**, a nie z całego localhosta.

