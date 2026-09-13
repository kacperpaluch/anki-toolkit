# Anki Toolkit: Integrations

Pełna integracja z kolejką n8n: panel 📚 przy oknie Dodaj, adres domowy i
fallback Tailscale, odhaczanie wierszy po dodaniu karty, zakładki słowników oraz
lokalny Web Bridge wpisujący dane do otwartej notatki.

Ustawienia: **Narzędzia → Anki Toolkit: Integrations → Ustawienia…**.

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
listę propozycji z checkboxami. Zatwierdzone znaczenia lądują jako osobne
notatki w talii i typie wybranym w oknie „Dodaj", a wiersz w n8n jest odhaczany.

**Definicje są cytatami, nie tłumaczeniami.** Pola `en` i `example` muszą
występować dosłownie w tekście strony słownikowej — co nie przechodzi tego
sprawdzenia, jest kasowane. Model nie ma jak dopisać definicji, której słownik
nie ma.

**Brak dopasowania 1:1 nie blokuje karty.** Znaczenie bez angielskiej definicji
dostaje pustą definicję, a nie zmyśloną. Każda karta z AI dostaje tag
z pola *Tag wszystkich kart* (domyślnie `ai-auto`), a wszystko poza pewnym
dopasowaniem dodatkowo *Tag niepewnych* (`ai-review`) — w Browserze
przeglądasz tylko to drugie.

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
