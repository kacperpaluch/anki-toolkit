# Anki Toolkit: Integrations

Panel 📚 przy oknie **Dodaj**: kolejka słówek z n8n DataTable, cztery słowniki
w zakładkach, tworzenie kart przez AI i lokalny Web Bridge, który wpisuje dane
ze stron słownikowych do otwartej notatki.

Ustawienia: **Narzędzia → Anki Toolkit: Integrations → Ustawienia…**.

## Web Bridge

Mostek słucha na `127.0.0.1:8767` (klucz `web_bridge.port`). Ten sam port musi
być w stałej `ENDPOINT` userscriptu — po zmianie przeładuj
`dictionaries-to-anki.user.js` w menedżerze userscriptów. 8765 i 8766 należą do
AnkiConnect i jego forków; gdy port jest zajęty, Anki pokazuje ostrzeżenie przy
starcie profilu.

Mostek przyjmuje wyłącznie POST-y z polami notatki (`{"fields": {...}}`)
i zapisuje bufor edytora przed wypełnieniem pól. Żądanie jest związane
z konkretną notatką i profilem; timeout anuluje oczekującą zmianę. Okno „Dodaj”
musi być otwarte, inaczej endpoint zwraca błąd.

## Lista słówek

Panel pobiera **całą** tabelę i sam chowa zrobione, żeby „Odśwież” nie gubił
pozycji odhaczonych w tej sesji. Na liście działają dwa niezależne stany:

| Sygnał | Znaczenie | Gdzie żyje |
|---|---|---|
| „☑” przed hasłem + pogrubienie | wybrane do AI | tylko w panelu |
| szary tekst | zrobione (flaga w n8n) | tabela n8n |

**Checkbox zbiera hasła dla przycisku AI**, a nie oznacza zrobionych. Zaznaczasz
je przez całą listę, przewijasz, klikasz gdzie indziej — wybór zostaje, bo
w odróżnieniu od podświetlenia nie gubi się przy pierwszym kliknięciu obok.
Licznik pokazuje, ile zebrałeś, a przycisk **AI: znaczenia (n)** bierze dokładnie
te pozycje. Gdy nic nie jest zaptaszkowane, działa podświetlenie (Ctrl/Shift) —
dla jednorazówek. Po dodaniu kart ptaszki zebranych haseł znikają same, więc to
samo hasło nie poleci do modelu drugi raz.

Wskaźnik checkboxa rysuje motyw Anki i przy kilkuset wierszach bywa praktycznie
niewidoczny, dlatego wybór niesie też tekst pozycji — ten wyrenderuje się zawsze.

**Stan „zrobione” zmieniasz** przyciskiem **Zrobione →** (odhacza i przechodzi
dalej) albo prawym klikiem na pozycji: *Oznacz jako zrobione* / *Cofnij
odhaczenie*. To samo menu czyści cały wybór do AI. **Następne** przechodzi dalej
bez odhaczania, a *Ukryj zrobione* chowa szare pozycje, nie usuwając ich.

Wiersz jest odhaczany automatycznie po dodaniu notatki powiązanej z tą pozycją
i z odpowiadającym jej hasłem. Jeśli zmienisz formę hasła, np. z „sprawling” na
„sprawl”, użyj ręcznie **Zrobione →**. Brak trafionego wiersza w n8n jest błędem,
a nie sukcesem — panel cofa wtedy zmianę koloru i pokazuje dymek.

### Kolejność

Rozwijanka w pasku: **Od początku** (kolejność tabeli), **Najnowsze** (ostatnio
dopisane na górze — tam znajdziesz dzisiejszą wklejkę) i **Losowo**. Sortowanie
idzie po `id`, które rośnie z każdym dopisanym wierszem, więc jest tym samym co
data dodania, a nie zależy od nazwy kolumny w tabeli. Wybór przeżywa restart,
a przebudowa listy zachowuje zaznaczoną pozycję, jeśli nadal istnieje.

### Adres n8n

Adres domowy z adresem zapasowym (np. Tailscale MagicDNS). Host, który
odpowiedział, jest zapamiętywany i próbowany pierwszy, ale tylko jeśli nadal
figuruje w aktualnej konfiguracji. Po zmianie ustawień zamknij całe okno „Dodaj”
i otwórz panel ponownie — konfigurację czyta przy otwarciu.

## Własne hasła

Dwie drogi na hasła spoza tabeli:

- pole **własne hasło** w pasku — wpisz i Enter; kilka naraz rozdziel przecinkiem,
- przycisk **+ lista** — okno na wklejenie kolumny haseł, po jednym na linię.

Spacja nie rozdziela haseł, więc „give up” i „household income” zostają
całością; powtórzenia w jednej wklejce lecą raz.

**Hasła są dopisywane do tabeli n8n** i lądują na liście jako pełnoprawne
pozycje kolejki — z własnym `id`, widoczne na innych urządzeniach i normalnie
odhaczane. Panel skacze na pierwszą z nich.

**Duplikat nie jest zapisywany.** Hasło, które już jest na liście, zostaje
pominięte — porównanie ignoruje wielkość liter i nie patrzy, czy pozycja
przyszła z tabeli, czy z wcześniejszej wklejki. Ponieważ panel trzyma **całą**
tabelę, jest to zarazem kontrola duplikatów w n8n, bez dodatkowego zapytania.
Pod uwagę brane są też hasła, których zapis właśnie trwa, więc dwa szybkie
wklejenia tego samego słowa nie zrobią dwóch wierszy. Pominięte hasła pokazuje
dymek, a panel skacze na tę pozycję, która już istnieje.

Gdy n8n nie przyjmie zapisu (offline, zła tabela), dostajesz dymek z powodem,
a hasła zostają jako pozycje **tylko w panelu**: działa na nich wszystko poza
odhaczaniem, którego nie ma dokąd wysłać, i znikają z zamknięciem okna „Dodaj”.

## Słowniki w zakładkach

Zakładki są **cztery, nie pięć** — Cambridge EN-PL wystarcza za dwa źródła, bo
jedna strona niesie i polski odpowiednik, i angielską definicję:

| Zakładka | Rola | Adres |
|---|---|---|
| diki | PL | `diki.pl/slownik-angielskiego?q=…` |
| Cambridge EN-PL | PL + EN | `dictionary.cambridge.org/pl/dictionary/english-polish/…` |
| Oxford | EN | `oxfordlearnersdictionaries.com/definition/english/…` |
| LDoCE | EN | `ldoceonline.com/dictionary/…` |

**Adresy składają się z samego hasła (`link_templates`), więc kolumny z URL-ami
w DataTable nie są do niczego potrzebne** — możesz je skasować razem z częścią
workflow w n8n, która je wypełnia. Wystarczy kolumna z hasłem i kolumna flagi.
Wielowyrazowe hasło dostaje myślnik w ścieżce („give up” → `give-up`).
`link_columns` zostaje wyłącznie jako nadpisanie: jeśli wiersz ma niepusty URL
w przypisanej kolumnie, wygrywa on. Etykieta wymieniona tylko w `link_columns`
nie tworzy zakładki.

**Wybór słówka ładuje wszystkie cztery zakładki naraz**, zaczynając od widocznej.
Kosztuje to pamięć — Chromium bierze ~100 MB na zakładkę — ale przeglądanie nie
czeka na wczytanie po każdym kliknięciu w zakładkę, a **AI: znaczenia** ma
zwykle komplet stron gotowy, zanim go naciśniesz.

Na stronach działają przyciski userscriptu — te same, co w przeglądarce.

## AI: znaczenia → karty

Przycisk robi z jednego hasła tyle kart, ile ma ono znaczeń: bierze tekst
otwartych zakładek, prosi model o dopasowanie polskich odpowiedników do
angielskich definicji i pokazuje propozycje z checkboxami oraz edytowalnymi
polami polskiego znaczenia, definicji i przykładu.

### Paczka

Zaptaszkuj kilka haseł (albo zaznacz Ctrl/Shift) — przycisk pokaże ich liczbę,
np. **AI: znaczenia (3)** — i cała paczka idzie do **jednego okna wyboru**,
z sekcją na hasło i checkboxem *Zaznacz wszystkie* u góry. Zatwierdzasz raz,
karty powstają jedną transakcją i jednym krokiem cofania, a odhaczane są tylko
te hasła, z których faktycznie powstały karty.

Hasła idą **po kolei**: załaduj zakładki, zbierz tekst, zapytaj model, następne.
Zakładki są jedne na panel, więc nakładanie kroków nic by nie przyspieszyło.
Hasło, które się nie powiedzie — brak odpowiedzi modelu albo niewczytana
zakładka — nie zatrzymuje paczki; wypada z niej i trafia do dymka
z podsumowaniem. Powyżej dziesięciu haseł panel pyta o potwierdzenie, bo to tyle
samo pytań do modelu (a przy lokalnym CLI tyle samo procesów).

W czasie pracy lista jest zablokowana, a *Odśwież*, rozwijanka kolejności
i dopisywanie haseł czekają — panel nie może przebudować się w połowie paczki.
Wynik wiąże się z wierszem po jego `id`, nie po tym, co akurat jest zaznaczone.
Jeśli między otwarciem okna wyboru a zatwierdzeniem zmieni się profil albo
zamkniesz okno „Dodaj”, zapis nie następuje i dostajesz o tym dymek.

Przy zaznaczaniu wielu pozycji panel **nie rusza notatki ani zakładek** — pola
edytora zostają takie, jakie były.

### Skąd biorą się definicje

**Do promptu idzie tekst wszystkich czterech zakładek naraz.** Model sam wybiera,
z którego słownika wziąć definicję, i zapisuje to w polu `src` widocznym w oknie
wyboru jako link do źródła. Nie ma stałego pierwszeństwa słownika, a znaczenie
opisane w kilku słownikach ma wrócić raz. Kolejność znaczeń bierze się
z pierwszego źródła PL.

**Cytaty są sprawdzane względem źródła.** Definicja i przykład muszą występować
w tekście słownika wskazanego w `src` (lista `ai_en_sources`); polskie
odpowiedniki — rozdzielone przecinkami lub średnikami — w dowolnym słowniku
z `ai_pl_sources`. Cambridge EN-PL jest na obu listach; poza nim źródło polskie
nie może dostarczyć angielskiej definicji. Obie listy muszą używać etykiet
z `link_templates` — literówka kończy się konkretnym komunikatem, a nie pustym
wynikiem bez powodu. Sprawdzany jest ten sam, przycięty tekst, który otrzymał
model. Brak polskiego cytatu odrzuca znaczenie, brak angielskiego zostawia pustą
definicję. To kontrola pochodzenia tekstu, nie gwarancja zgodności znaczeń —
sprawdź propozycje przed zatwierdzeniem.

Kontrola dowodzi tylko, że cytat **jest na stronie**, a nie że należy do hasła:
reklamy, listy „podobne słówka" i sąsiednie hasła też są w pobranym tekście.
Zabrania ich prompt, nie walidator. Z tego samego powodu prompt każe wybierać
*approx* w razie wątpliwości — `exact` wyłącza kartę z listy do przejrzenia,
więc niepewność ma kosztować przegląd, a nie cichą akceptację.

### Okno wyboru

Puste polskie znaczenie blokuje zatwierdzenie zaznaczonej propozycji. Ręczne
poprawki trafiają do tagu do weryfikacji; nie są ponownie sprawdzane jako
cytaty. Anulowanie odrzuca poprawki. Zwykły tekst jest zabezpieczony przed
interpretacją jako HTML. Zatwierdzone znaczenia lądują jako osobne notatki
w talii i typie wybranym w oknie „Dodaj”.

**Duplikaty są pokazywane, nie blokowane.** Okno ostrzega na czerwono, gdy masz
już karty z tym hasłem, i wypisuje ich polskie znaczenia. Notatki z AI powstają
poza oknem „Dodaj”, więc jego własna kontrola duplikatów ich nie widzi — kolejne
znaczenie istniejącego hasła jest zamierzone, powtórzenie tego samego nie.

**Brak dopasowania 1:1 nie blokuje karty.** Znaczenie bez angielskiej definicji
dostaje pustą definicję, a nie zmyśloną. Każda karta z AI dostaje **dokładnie
jeden** tag: pewne dopasowanie *Tag pewnych dopasowań* (domyślnie `ai-auto`),
wszystko pozostałe *Tag do weryfikacji* (`ai-review`). Tagi się nie nakładają,
więc `tag:ai-review` w Browserze to cała robota do przejrzenia, a `tag:ai-auto`
oznacza dopasowania ocenione przez model jako pewne, nie niezależnie zweryfikowane.

Puste ustawienie *Pole przykładu* wyłącza przykłady w prompcie i podglądzie;
ewentualny przykład zwrócony mimo to przez model jest pomijany.

### Model

Ustawienia → sekcja *AI: znaczenia*: **Dostawca AI** (rozwijanka) i **Model**
(rozwijanka edytowalna — możesz wpisać dowolną nazwę). Puste pole *Model*
oznacza model domyślny wybranego dostawcy, ustawiony w Contencie.

**Dostawca jest jeden, własny i osobny od Contentu.** Z Contentu pożyczane są
tylko klucze API i lista dostawców — dzięki temu `claude_cli` i `codex_cli` jadą
na Twojej subskrypcji, bez klucza. **Modele wybrane w Contencie per pole notatki
nie mają tu zastosowania**; ten przycisk ma jedno ustawienie na całą swoją pracę.

Okno wyboru pokazuje u góry, czym faktycznie policzono (np. *Policzone przez:
Claude CLI · opus*). Po zmianie ustawień zamknij okno „Dodaj” i otwórz panel
ponownie.

Reszta pól (audio, IPA, TTS, przykłady) to zadanie dla workflowu z dodatku
**Content**: zaznacz świeże notatki w Browserze i uruchom go na zaznaczeniu.

## Konfiguracja

Sekcja `word_queue`: adresy n8n i klucz API, `table_id`, nazwy kolumn
(`word_column`, `flag_column`), pole notatki (`word_field`), `link_templates`
i `link_columns`, ustawienia `ai_*` (dostawca, model, limity, tagi, pola, listy
źródeł PL/EN) oraz `order`. Klucz API i pozostałe dane prywatne trafiają do
`meta.json`, które nie jest wersjonowane.
