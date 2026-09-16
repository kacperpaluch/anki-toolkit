# Kolejka słówek (`integrations/`)

Panel 📚 przy oknie **Dodaj**: kolejka słówek z n8n DataTable, cztery słowniki
w zakładkach, tworzenie kart przez AI i lokalny Web Bridge, który wpisuje dane
ze stron słownikowych do otwartej notatki.

Panel otwiera przycisk 📚 w oknie **Dodaj** albo **Narzędzia → Anki Toolkit →
Kolejka słówek (n8n)…**. Ustawienia (połączenie z n8n, AI: znaczenia, Web
Bridge): **Narzędzia → Anki Toolkit → Ustawienia… → Kolejka słówek**.

## Web Bridge

Mostek słucha na `127.0.0.1:8767` (pole **Port** w ustawieniach, klucz
`web_bridge.port`; zmiana działa po restarcie Anki). Ten sam port musi być
w stałej `ENDPOINT` userscriptu — po zmianie przeładuj
`dictionaries-to-anki.user.js` w menedżerze userscriptów. 8765 i 8766 należą do
AnkiConnect i jego forków; gdy port jest zajęty, Anki pokazuje ostrzeżenie przy
starcie profilu.

Mostek przyjmuje wyłącznie POST-y z polami notatki (`{"fields": {...}}`)
i zapisuje bufor edytora przed wypełnieniem pól. Wartości są zwykłym tekstem —
`<` czy `&` trafiają do pola jako znaki, nie znaczniki. Skrypt, który wysyła
gotowy HTML, dodaje `"html": true`. Separator doklejania (`separator`, domyślnie
`<br><br>`) jest zawsze HTML-em. Żądanie jest związane
z konkretną notatką i profilem; timeout anuluje oczekującą zmianę. Okno „Dodaj”
musi być otwarte, inaczej endpoint zwraca błąd.

## Lista słówek

Panel pobiera **całą** tabelę i sam chowa zrobione, żeby „Odśwież” nie gubił
pozycji odhaczonych w tej sesji. Przekroczenie `max_rows` (domyślnie 5000)
zgłasza błąd zamiast pokazywać niepełną listę; zwiększ limit w konfiguracji.
Na liście działają dwa niezależne stany:

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

Adres główny (np. domena za Cloudflare) i opcjonalny zapasowy (np. IP w sieci
domowej). Host, który odpowiedział, jest zapamiętywany i próbowany pierwszy, ale
tylko jeśli nadal figuruje w aktualnej konfiguracji.

**Cloudflare Access.** Gdy n8n stoi za Cloudflare Access, utwórz w Zero Trust
*service token*, a w aplikacji Access dla tej domeny dodaj regułę z akcją
**Service Auth** (zwykła reguła „Allow” przekierowuje na stronę logowania).
Client ID i Client Secret wpisz w ustawieniach Kolejki — trafiają do nagłówków
`CF-Access-Client-Id` / `CF-Access-Client-Secret`, wyłącznie na adresy `https`,
więc adres lokalny ich nie dostaje. Klucz API n8n nadal jest wymagany. Jeśli
zamiast danych przyjdzie strona HTML, panel zgłasza błąd tokenu Access. Gdy w
Cloudflare jest włączony Bot Fight Mode, dodaj wyjątek dla ścieżki
`/api/v1/data-tables/`. Po zmianie ustawień zamknij całe okno „Dodaj”
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
a hasła zostają jako pozycje **lokalne** w `user_files/`, także po zamknięciu Anki.
Działa na nich generowanie i lokalne odhaczanie. Przy odświeżeniu lokalna
pozycja zostaje połączona z n8n, jeśli tabela zawiera dokładnie jedno takie hasło.

POST dopisujący hasła ma **jedną próbę**. Dostępny host jest wybierany przez
GET przed zapisem. Przy utracie odpowiedzi dodatek sprawdza tabelę, ale nie
powtarza POST-a na drugim adresie. Jeśli nie da się ustalić wyniku, pokazuje
komunikat o niepewnym zapisie i zachowuje hasła lokalnie. Nie jest to blokada
równoczesnego dopisania tego samego słowa z dwóch różnych urządzeń.

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

**Do promptu idzie treść pasującego hasła z poprawnie wczytanych zakładek.**
Userscript wybiera bloki znaczeń we wpisie z nagłówkiem zgodnym z hasłem,
usuwając przyciski i elementy poboczne. Błąd ładowania, CAPTCHA lub brak obsługi
słownika oznaczają pominięcie źródła. Gdy słownik zmieni układ strony i żaden wpis
nie zostanie rozpoznany, model dostaje całą stronę, a podgląd pokazuje ostrzeżenie
**⚠ Cała strona** — cytaty mogą wtedy pochodzić z sąsiednich haseł. Czy reguły
nadal pasują, sprawdzisz poleceniem (wymaga sieci):
`QT_QPA_PLATFORM=offscreen "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" tests/live_selectors.py`.
Gdy pojedyncze słowo przekierowuje na formę podstawową (np. *went* → *go*),
brany jest pierwszy wpis strony; dla fraz (*give up*) nigdy — tam inny nagłówek
oznacza pominięcie źródła. Oczekiwanie na ładowanie ma limit 20 sekund, a odczyt
treści z silnika przeglądarki osobny limit 5 sekund. Dodanie nowego słownika do zakładek nie wystarcza do AI;
potrzebna jest reguła ekstrakcji w userscripcie.

Postęp i podgląd wskazują wykorzystane źródła; podgląd wymienia też pominięte.
Model sam wybiera,
z którego słownika wziąć definicję, i zapisuje to w polu `src` widocznym w oknie
wyboru jako link do źródła. Nie ma stałego pierwszeństwa słownika, a znaczenie
opisane w kilku słownikach ma wrócić raz. Kolejność znaczeń bierze się
z pierwszego źródła PL.

**Cytaty są sprawdzane względem źródła, z granicami wyrazów** (`kot` nie pasuje do `kotlet`). Definicja i przykład muszą występować
w tekście słownika wskazanego w `src` (lista `ai_en_sources`); polskie
odpowiedniki — rozdzielone przecinkami lub średnikami — w dowolnym słowniku
z `ai_pl_sources`. Cambridge EN-PL jest na obu listach; poza nim źródło polskie
nie może dostarczyć angielskiej definicji. Obie listy muszą używać etykiet
z `link_templates` — literówka kończy się konkretnym komunikatem, a nie pustym
wynikiem bez powodu. Sprawdzany jest ten sam, przycięty tekst, który otrzymał
model. Brak polskiego cytatu odrzuca znaczenie, brak angielskiego zostawia pustą
definicję. To kontrola pochodzenia tekstu, nie gwarancja zgodności znaczeń —
sprawdź propozycje przed zatwierdzeniem.

Weryfikacja dowodzi obecności cytatu we wpisie, ale nie zgodności znaczeń.
`exact` oznacza **AI: dopasowane**, a nie ręczne sprawdzenie. Prompt nadal
preferuje `approx` przy wątpliwości.

### Przerwanie i odzyskiwanie

**Zatrzymaj po bieżącym haśle** kończy bieżące zapytanie i otwiera wybór dla
wyników już uzyskanych. Każde ukończone hasło jest zapisywane na dysku.
**Odzyskane propozycje** pozwalają wrócić do wyników po anulowaniu podglądu,
zamknięciu okna lub restarcie Anki. Ponowna paczka wykorzystuje zachowane
propozycje tych samych haseł bez ponownego pytania modelu.
Niezakończone zapytanie trzeba uruchomić ponownie. Robocze edycje w podglądzie
nie są zapisywane przy anulowaniu. Po zapisie kart propozycje danego hasła
znikają z odzyskiwania.

### Zapis kart i potwierdzenie n8n

Dopisek **karty są, czeka n8n** oznacza, że notatki już istnieją, ale n8n
nie potwierdził odhaczenia (brak sieci, restart). Po każdym **Odśwież** dodatek
sprawdza, czy karty z tym hasłem są w kolekcji, i ponawia samo odhaczenie.
Takie hasło nie jest ponownie wysyłane do AI.

**Cofnij** (Undo) po zapisie paczki nie cofa odhaczenia w n8n — zrób to ręcznie
przez **Cofnij odhaczenie** w menu pozycji.

Pliki `user_files/word_queue_<hash>.json` przechowują propozycje AI, lokalne
hasła i oczekujące odhaczenia osobno dla kolekcji, głównego adresu i tabeli n8n.
Nie zawierają kluczy API. Uszkodzony plik jest odkładany jako `.broken`, a panel
startuje od zera.

### Okno wyboru

Puste polskie znaczenie blokuje zatwierdzenie zaznaczonej propozycji. Ręczne
poprawki cofają potwierdzenie ręcznej weryfikacji; nie są ponownie sprawdzane jako
cytaty. Anulowanie odrzuca poprawki. Zwykły tekst jest zabezpieczony przed
interpretacją jako HTML. Zatwierdzone znaczenia lądują jako osobne notatki
w talii i typie wybranym w oknie „Dodaj”.

**Słowo, które już jest w Anki, nie trafia do AI.** Przed wysłaniem do modelu
dodatek sprawdza pole angielskie (wielkość liter bez znaczenia) — jeśli masz już
kartę z tym słowem, jest pomijane i znika z wyboru do AI. Jeśli któreś z nich
nie jest jeszcze odhaczone, dodatek pyta, czy odhaczyć je w kolejce — **Tak**
odhacza (z ponowieniem po **Odśwież**, gdy n8n nie odpowie), **Nie** tylko je
pomija. Liczy się wyłącznie słowo, nie znaczenia: kolejne znaczenie takiego
słowa dodajesz ręcznie. Gdy sprawdzenie
się nie uda, paczka nie rusza. Przy odzyskanych propozycjach okno wyboru
dodatkowo ostrzega na czerwono, jeśli karty z tym słowem powstały w międzyczasie.

**Brak dopasowania 1:1 nie blokuje karty.** Znaczenie bez angielskiej definicji
dostaje pustą definicję, a nie zmyśloną. Każda karta dostaje **Tag kart z AI**
(`ai_tag`, domyślnie `ai-auto`). Dodatkowo dostaje **Tag do weryfikacji**
(`ai_review_tag`, domyślnie `ai-review`), chyba że zaznaczysz przy niej
**Sprawdziłem znaczenie i zgodność ze źródłem**. Samo zatwierdzenie okna ani
ocena `exact` nie zastępują tej czynności. Puste ustawienie tagu wyłącza go.
Zmiana nie retaguje wcześniejszych notatek.

Pole angielskie i polskie są wymagane. Wszystkie niepuste przypisania muszą
być różne i istnieć w docelowym typie notatki — sprawdzenie przed zapisem
obejmuje również konfigurację zmienioną ręcznie.

Puste ustawienie *Pole przykładu* wyłącza przykłady w prompcie i podglądzie;
ewentualny przykład zwrócony mimo to przez model jest pomijany.

### Model

Ustawienia → Kolejka słówek → sekcja *AI: znaczenia*: **Dostawca AI**
(rozwijanka) i **Model** (rozwijanka edytowalna — możesz wpisać dowolną nazwę).
Puste pole *Model* oznacza model domyślny wybranego dostawcy z **Ustawienia →
AI Generator → Dostawcy**.

**Dostawca jest jeden, własny i osobny od AI Generatora.** Z zakładki AI
Generator brane są tylko klucze API i lista dostawców — dzięki temu `claude_cli`
i `codex_cli` jadą na Twojej subskrypcji, bez klucza. **Modele wybrane w AI
Generatorze per pole notatki nie mają tu zastosowania**; ten przycisk ma jedno
ustawienie na całą swoją pracę.

Okno wyboru pokazuje u góry, czym faktycznie policzono (np. *Policzone przez:
Claude CLI · opus*). Po zmianie ustawień zamknij okno „Dodaj” i otwórz panel
ponownie.

Reszta pól (audio, IPA, TTS, przykłady) to zadanie dla workflowu: zaznacz
świeże notatki w Browserze i uruchom go na zaznaczeniu.

## Konfiguracja

Sekcja `word_queue`: adresy n8n (`n8n_url` główny, `fallback_url` zapasowy),
klucz API, token Cloudflare Access (`cf_client_id`, `cf_client_secret`),
`table_id`, nazwy kolumn (`word_column`, `flag_column`), pole notatki
(`word_field`), `link_templates` i `link_columns`, ustawienia `ai_*` (dostawca,
model, limity, tagi, pola, listy źródeł PL/EN), `order` oraz `page_size`
i `max_rows` (stronicowanie). Sekcja `web_bridge` trzyma `port`.
`link_templates`, `link_columns`, `ai_pl_sources`, `ai_en_sources`, `page_size`
i `max_rows` nie mają pól w oknie ustawień — zmienisz je, edytując `meta.json`
dodatku przy zamkniętym Anki (przycisk **Config** w menedżerze dodatków otwiera
okno ustawień, a nie edytor JSON). Klucze, token i pozostałe
dane prywatne trafiają do `meta.json`, które nie jest wersjonowane.
