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
`<br><br>`) jest zawsze HTML-em.

Przyciski userscriptu wysyłają **role**, nie nazwy pól: `headword`, `meaning`,
`definition`, `example`. Mostek zamienia je na pola z ustawień Kolejki słówek
(**Pole notatki** i pola *AI: znaczenia*), więc nazwy pól zmieniasz tylko tam —
userscriptu nie trzeba edytować. Klucz, który nie jest rolą, trafia do pola
o tej nazwie; rola przypisana do pustego pola (np. wyłączony przykład) jest
pomijana. Po aktualizacji dodatku wgraj userscript ponownie w menedżerze
userscriptów. Żądanie jest związane
z konkretną notatką i profilem; timeout anuluje oczekującą zmianę. Okno „Dodaj”
musi być otwarte, inaczej endpoint zwraca błąd.

## Lista słówek

Panel pobiera **całą** tabelę i sam chowa zrobione, żeby „Odśwież” nie gubił
pozycji odhaczonych w tej sesji. Przekroczenie `max_rows` (domyślnie 5000)
zgłasza błąd zamiast pokazywać niepełną listę; zwiększ limit w konfiguracji.
Na liście działają dwa niezależne stany:

| Sygnał | Znaczenie | Gdzie żyje |
|---|---|---|
| checkbox + pogrubienie | wybrane do AI | tylko w panelu |
| szary tekst | zrobione (flaga w n8n) | tabela n8n |

**Checkbox zbiera hasła dla przycisku AI**, a nie oznacza zrobionych. Zaznaczasz
je przez całą listę, przewijasz, klikasz gdzie indziej — wybór zostaje, bo
w odróżnieniu od podświetlenia nie gubi się przy pierwszym kliknięciu obok.
Licznik pokazuje, ile zebrałeś, a przycisk **Utwórz karty z AI (n)** bierze dokładnie
te pozycje. Gdy nic nie jest zaptaszkowane, działa podświetlenie (Ctrl/Shift) —
dla jednorazówek. Po dodaniu kart albo wybraniu **Oznacz jako zrobione** checkbox danego hasła
zostaje wyczyszczony. Ręczne oznaczanie zwalnia wybór do AI również przy
braku połączenia z n8n; szary kolor pojawia się dopiero po potwierdzeniu serwera.
Ukryte wiersze nie trafiają do AI, a liczba na przycisku odpowiada faktycznej paczce.

Wybrane hasło jest dodatkowo pogrubione; tekst nie zawiera drugiego checkboxa.
Lista używa stylu Qt Fusion, żeby checkbox był widoczny przy każdej pozycji
również na macOS.

Panel ma dwie kolumny: **słowa i działania po lewej**, **słowniki po prawej**.
Nad listą są kolejność, **Odśwież**, filtr zrobionych i dodawanie słów.
Pod listą opis wyboru pokazuje, czy AI bierze checkboxy, czy podświetlenie.
**Utwórz karty z AI (n)** otwiera podgląd przed zapisem; bez wyboru jest wyłączony.
**Wyczyść checkboxy** pojawia się po zebraniu paczki. Ręczne **Oznacz jako zrobione**
i **Pomiń** dotyczą bieżącego słowa, nie całej paczki.

Błąd pobrania n8n pozostaje widoczny nad listą; ponowienie to **Odśwież**.
**Zatrzymaj po bieżącym haśle** widać tylko podczas pracy AI, a **Odzyskane
propozycje** tylko wtedy, gdy są zapisane wyniki. W czasie pracy filtry,
dodawanie słów i działania ręczne są wyłączone.
**Wklej listę…** otwiera pole do wklejenia wielu słów.

**Stan „zrobione” zmieniasz** przyciskiem **Oznacz jako zrobione** (odhacza i przechodzi
dalej) albo prawym klikiem na pozycji: *Oznacz jako zrobione* / *Cofnij
odhaczenie*. To samo menu czyści cały wybór do AI. **Pomiń** przechodzi dalej
bez odhaczania, a *Ukryj zrobione* chowa szare pozycje, nie usuwając ich.

Wiersz jest odhaczany automatycznie po dodaniu notatki powiązanej z tą pozycją
i z odpowiadającym jej hasłem. Jeśli zmienisz formę hasła, np. z „sprawling” na
„sprawl”, użyj ręcznie **Oznacz jako zrobione**. Brak trafionego wiersza w n8n jest błędem,
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
a hasła wracają do pola **własne hasło** — nic nie trafia na listę, a ponowienie
to Enter. Panel wymaga działającego n8n; pozycji offline nie ma.

POST dopisujący hasła ma **jedną próbę**. Dostępny host jest wybierany przez
GET przed zapisem. Przy utracie odpowiedzi dodatek sprawdza tabelę, ale nie
powtarza POST-a na drugim adresie. Jeśli nie da się ustalić wyniku, pokazuje
komunikat o niepewnym zapisie i oddaje hasła do pola — przed ponowieniem
kliknij **Odśwież**, żeby zapisane już hasła zostały pominięte. Nie jest to blokada
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
czeka na wczytanie po każdym kliknięciu w zakładkę, a **Utwórz karty z AI** ma
zwykle komplet stron gotowy, zanim go naciśniesz.

Na stronach działają przyciski userscriptu — te same, co w przeglądarce.

Wpis diki z kilkoma nagłówkami (np. *hippophae*, *sea buckthorn*, także:
*sandthorn*, *seaberry*) ma **→ hasło** przy każdym z nich — do pola trafia ten,
który klikniesz. **→ oba** przy znaczeniu bierze nagłówek, którego szukałeś
(z adresu strony), a gdy żaden nie pasuje — pierwszy. Karta dostaje zawsze jedno
hasło; pozostałe warianty nie są dopisywane.

**Skrypty samej strony działają tylko na zakładkach z listy `page_js`**
(domyślnie `["diki"]`). Pozostałe zakładki pokazują treść słownika bez nich:
nie ma reklam ani okien zgód, ale nie działają też przyciski odsłuchu, rozwijane
sekcje i wyszukiwarka strony. Przyciski userscriptu i **Utwórz karty z AI** działają
na każdej zakładce. Powód: QtWebEngine 6.11.2 (Anki 26.09) wywraca proces strony
na każdym pliku w starym kodowaniu znaków (windows-1250, ISO-8859-x), a takie
skrypty doładowują reklamy Cambridge, Oxfordu i LDoCE — strona pokazywała się
i po chwili znikała. Dopisz etykietę do `page_js`, jeśli wolisz pełną stronę
i ryzyko jej zniknięcia; zakładka, której proces padł, mówi o tym wprost
i wczytuje się ponownie po powrocie na nią.

## AI: znaczenia → karty

Przycisk robi z hasła po jednej karcie na znaczenie z **diki**: polskie
odpowiedniki razem z kontekstem, np. *ograniczać (np. wydatki, podatki)*. Do
każdego znaczenia dobiera angielską definicję z Cambridge EN-PL, Oxfordu albo
LDoCE i pokazuje propozycje z checkboxami oraz edytowalnym polskim znaczeniem
i definicją. Przykładów nie wypełnia — dodajesz je przyciskami **+ przykład**.

### Paczka

Zaptaszkuj kilka haseł (albo zaznacz Ctrl/Shift) — przycisk pokaże ich liczbę,
np. **Utwórz karty z AI (3)** — i cała paczka idzie do **jednego okna wyboru**,
z sekcją na hasło i checkboxem *Zaznacz wszystkie* u góry. Zatwierdzasz raz,
karty powstają jedną transakcją i jednym krokiem cofania, a odhaczane są tylko
te hasła, z których faktycznie powstały karty.

Hasła idą **po kolei**: załaduj zakładki, zbierz wpisy, zapytaj model, następne.
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

### Skąd biorą się znaczenia i definicje

**Automatycznie przygotowana treść karty pochodzi ze słowników — model jej nie pisze.** Userscript
wyciąga z każdej zakładki wyłącznie wpis z nagłówkiem zgodnym z hasłem.
Spacje i łączniki (także typograficzne) są równoważne przy porównaniu:
`brother in law` pasuje do `brother-in-law`. Nie zmienia to zapisywanego hasła
ani adresu strony; inna fraza nadal nie jest dopasowaniem. Źródła:

| Źródło | Co daje |
|---|---|
| diki | znaczenia — polskie odpowiedniki z kontekstem (bez kategorii, synonimów i przykładów) |
| Cambridge EN-PL | definicje z polskim tłumaczeniem |
| Oxford, LDoCE | definicje |

Model dostaje dane JSON: hasło, ponumerowane znaczenia (D1…) i definicje (E1…),
źródła oraz opcjonalne części mowy (`pos`) i kwalifikatory (`labels`). Metadane
są odczytywane z HTML słownika, nie zgadywane. Diki przypisuje część mowy z
nagłówka właściwej sekcji; Oxford, LDoCE i Cambridge przekazują część mowy wpisu
oraz lokalne kwalifikatory/gramatykę, jeśli są dostępne. Dane bez metadanych
nadal mogą być dopasowane. Kontekst w nawiasach pozostaje częścią polskiego znaczenia.

Model odpowiada wyłącznie identyfikatorami: `{"D1": "E2", "D2": null}`.
Kod kopiuje definicję ze słownika — model nie pisze ani nie poprawia jej treści.
Wciąż może wybrać niewłaściwy sens, dlatego podgląd i tag do weryfikacji pozostają.

Prompt wymaga tego samego sensu, ale dopuszcza różną długość opisu i przykładowe
zastosowania. „Ograniczać (np. wydatki)” może pasować do „to limit or control
something”. Istotna zmiana zakresu znaczenia, sprzeczny kontekst lub brak
wiarygodnego rozstrzygnięcia oznacza `null`. Polskie tłumaczenie przy definicji
jest dodatkową wskazówką; różnica aspektu nie wyklucza tego samego sensu.
Przy kilku równie zgodnych definicjach preferowana jest najczytelniejsza i
samodzielna, a przy dalszym remisie najniższy numer E. Jedno E może pasować do wielu D.

**Tylko jawne JSON `null` oznacza świadomy brak dopasowania.** Odpowiedź musi
zawierać każdy D dokładnie raz, bez dodatkowych kluczy, a wartościami mogą być
wyłącznie istniejące identyfikatory E lub `null`. Brak D, powtórzony klucz,
nieistniejący numer, liczba zamiast `"E1"` albo tekst poza JSON-em oznaczają
błąd całego wyniku danego hasła; nie powstają z niego propozycje kart. Otoczka markdown z oznaczeniem `json` jest tolerowana, ale nie zmienia wymagań zawartości. Nie ma automatycznego
ponownego zapytania, które zużywałoby dodatkowe limity. Błąd jednego hasła
nie zatrzymuje reszty paczki.

Deduplikacja porównuje tekst i kontekst (`pos`, `labels`). Identyczna definicja
może zostać uzupełniona polskim tłumaczeniem z kolejnego źródła — jego pochodzenie
zostaje zachowane osobno. Różne niepuste tłumaczenia, części mowy lub kwalifikatory
pozostają oddzielnymi kandydatami. Definicja zachowuje swoje pierwotne źródło.

- **Brak wpisu w diki** (np. rzadkie hasło): kartami są gotowe pary z Cambridge
  EN-PL — słownik sam dobrał tłumaczenie do definicji, model nie jest pytany.
- **Brak definicji w słownikach angielskich** (np. *household income*): karty
  mają samo polskie znaczenie, model też nie jest pytany.
- Znaczenia tylko ze słowników angielskich są pomijane — to diki wyznacza,
  jakie karty powstają.

Nagłówek z zaślepką w diki (*give **something** up*) liczy się jak *give up*.
Pojedyncze słowo przekierowane na formę podstawową (*went* → *go*) bierze
pierwszy wpis strony; fraza (*give up*) nigdy nie spada do *give*. Błąd
ładowania, CAPTCHA albo zmieniony układ strony oznaczają pominięcie źródła,
nigdy zgadywanie z całej strony. Czy zakładki nadal się ładują, a reguły pasują,
sprawdzisz poleceniem (wymaga sieci; używa Qt z zainstalowanego Anki i tych
samych ustawień zakładek co panel, łącznie z `page_js`):
`QT_QPA_PLATFORM=offscreen PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages python3.13 tests/live_selectors.py 2>/dev/null`.
Kod wyjścia 1 oznacza, że reguła przestała pasować, strona wymaga własnych
skryptów albo jej proces padł (`PADŁ`). Uruchom je po każdej aktualizacji Anki;
możesz też uruchamiać je cyklicznie (np. zadaniem `launchd` z powiadomieniem
przez `osascript`).
Oczekiwanie na ładowanie ma limit 20 sekund, a odczyt wpisów z silnika
przeglądarki osobny limit 5 sekund. Nowy słownik w zakładkach wymaga reguły
ekstrakcji w userscripcie, zanim trafi do AI.

Postęp i podgląd wskazują wykorzystane źródła; podgląd wymienia też pominięte
i linkuje do słownika znaczenia i definicji.

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

Pliki `user_files/word_queue_<hash>.json` przechowują propozycje AI
i oczekujące odhaczenia osobno dla kolekcji, głównego adresu i tabeli n8n.
Nie zawierają kluczy API. Uszkodzony plik jest odkładany jako `.broken`, a panel
startuje od zera.

### Okno wyboru

Okno **Wybierz karty do dodania** grupuje propozycje według haseł.
Każda karta ma osobną ramkę: checkbox **Dodaj kartę**, informację o pochodzeniu
definicji oraz pola **Hasło (EN)**, **Znaczenie (PL)** i **Definicja (EN)**.
Odznaczenie wyłącza edycję tej propozycji; jej treść pozostaje zachowana.
U góry widać licznik **Wybrane: n z wszystkich**, a checkbox **Zaznacz wszystkie**
pokazuje też częściowy wybór. Przycisk **Dodaj karty (n)** podaje liczbę kart,
które zostaną zapisane, i jest wyłączony przy pustym wyborze.
Jeśli zaznaczona karta nie ma polskiego znaczenia, okno przewija się do jej pola
i ustawia tam kursor. **Anuluj** wraca do kolejki bez zapisu kart.

Okno pokazuje **wszystkie** znaczenia z diki, ale zaznaczone jest tylko pierwsze
N (**Domyślnie zaznacz znaczeń**, `ai_max_senses`, domyślnie 3) — diki podaje je od
najczęstszych. Przy każdym widać, skąd jest definicja: *para ze słownika*,
*definicję dobrało AI* albo *✗ bez definicji*. Każde znaczenie ma też pole
**Hasło (EN)** — wypełnione hasłem z kolejki, do poprawienia dla tej jednej
karty (np. *salvage* → *salvage sth*); puste wraca do hasła z kolejki. Zmiana
hasła nie cofa potwierdzenia definicji. Kolejka nadal rozpoznaje „mam już karty”
po haśle z listy, więc słowa, którego wszystkie karty dostały zmienione hasło,
nie pominie przy ponownym uruchomieniu. Puste polskie znaczenie blokuje
zatwierdzenie zaznaczonej propozycji. Anulowanie odrzuca poprawki. Zwykły tekst jest zabezpieczony przed
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

Każda karta dostaje **Tag kart z AI** (`ai_tag`, domyślnie `ai-auto`).
Przy definicjach dobranych przez AI pole **Sprawdziłem, że definicja pasuje do
znaczenia** jest domyślnie zaznaczone. **Tag do weryfikacji** (`ai_review_tag`,
domyślnie `ai-review`) dostają tylko te z nich, przy których je odznaczysz albo
zmienisz polskie znaczenie — edycja pól cofa potwierdzenie. Definicja wpisana
ręcznie przestaje być definicją AI. Pary ze
słownika i karty bez definicji nie mają czego weryfikować. Puste ustawienie
tagu wyłącza go. Zmiana nie retaguje wcześniejszych notatek.

Każda notatka zapisana przez **Utwórz karty z AI** dostaje również automatyczny tag
**`ai-import::YYYY-MM-DD`**, np. `ai-import::2026-10-01`. Data to lokalny dzień
zapisu kart, również przy zapisie odzyskanych propozycji. Wszystkie notatki
w jednej zatwierdzonej paczce mają tę samą datę; nie ma identyfikatora paczki.
Tag trafia także na pary ze słownika i notatki bez definicji, niezależnie od
potwierdzenia dopasowania i ustawień pozostałych tagów. Nie jest dopisywany wstecz.

W Browserze wybierz dzień pod tagiem `ai-import` albo wpisz
`tag:ai-import::2026-10-01`, zaznacz notatki i uruchom **Przygotuj fiszki** lub
wybrane zadania AI. Zwykłe uzupełnianie zachowuje istniejące pola.

Pole angielskie i polskie są wymagane. Wszystkie niepuste przypisania muszą
być różne i istnieć w docelowym typie notatki — sprawdzenie przed zapisem
obejmuje również konfigurację zmienioną ręcznie.

*Pole przykładu* nie jest wypełniane przez AI — to pole, do którego piszą
przyciski **+ przykład** na stronach słowników.

### Model

Strona **Kolejka słówek** zaczyna się od ustawień **AI: znaczenia**. Mapowanie pól,
tagi i limit czasu są w sekcji **Pola notatki, tagi i limit czasu**. Połączenie
z n8n, Cloudflare Access i Web Bridge mają osobne, domyślnie zwinięte sekcje.
Rozwinięcie sekcji nie zmienia zapisanych wartości.

Ustawienia → Kolejka słówek → sekcja *AI: znaczenia*: **Dostawca AI**
(rozwijanka) i **Model** (rozwijanka edytowalna — możesz wpisać dowolną nazwę).
Puste pole *Model* oznacza model domyślny wybranego dostawcy z **Ustawienia →
AI Generator → Dostawcy**.

**Poziom rozumowania** ustawia poziom wysiłku osobno dla dopasowania definicji przez
Codex CLI lub Claude CLI (`word_queue.ai_reasoning_effort`). „Dziedzicz: medium” (lub inny poziom dostawcy) korzysta z poziomu w **AI Generator → Dostawcy**. Zmiana dostawcy resetuje
nadpisanie. Etykieta dziedziczenia aktualizuje się również po niezapisanej zmianie poziomu dostawcy
w tym samym oknie ustawień. Dostępne poziomy zależą od modelu i wersji CLI; pole jest nieaktywne
dla dostawców API.

**Dostawca jest jeden, własny i osobny od AI Generatora.** Z zakładki AI
Generator brane są klucze API, lista i domyślne ustawienia dostawców — dzięki temu `claude_cli`
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
(`word_field`), `link_templates`, `link_columns` i `page_js`, ustawienia `ai_*` (dostawca,
model, zaznaczone znaczenia, limit czasu, tagi, pola), `order` oraz `page_size`
i `max_rows` (stronicowanie). Sekcja `web_bridge` trzyma `port`.
`link_templates`, `link_columns`, `page_js`, `page_size`
i `max_rows` nie mają pól w oknie ustawień — zmienisz je, edytując `meta.json`
dodatku przy zamkniętym Anki (przycisk **Config** w menedżerze dodatków otwiera
okno ustawień, a nie edytor JSON). Klucze, token i pozostałe
dane prywatne trafiają do `meta.json`, które nie jest wersjonowane.
