# Workload Service — codzienny klient synchronizacji

Samodzielny proces bez GUI, uruchamiany na własnej maszynie w Dockerze. Korzysta
z oficjalnej biblioteki `anki==26.8.1`; nie jest częścią dodatku Anki Toolkit. Cel:
nie przeładować się kartami. Usługa ogranicza dopływ nowych kart. Obsługuje AnkiWeb
oraz własny serwer zgodny z protokołem Anki (w tym oficjalny self-hosted server).
Nie montuje ani nie edytuje bazy serwera: ma własną kopię kolekcji, jak kolejna
aplikacja. Nie wymaga włączonego macOS ani dodatku.

## Uruchomienie

Najpierw zsynchronizuj kolekcję z wybranym serwerem w swojej aplikacji Anki. Potem:

```bash
cd workload_service
docker compose up -d --build
```

Otwórz **http://ADRES-SERWERA:8070** i przejdź **Pierwsze kroki** z panelu:

1. **Konto Anki** — serwer (`ankiweb` albo URL własnego serwera), login i hasło.
   Usługa loguje się, zapisuje token i pobiera kolekcję do prywatnej repliki.
   Hasło nie jest nigdzie zapisywane.
2. **Plan nauki** — zaznacz talie (lista pochodzi z Twojej kolekcji), budżet
   czasu, pułap nowych kart i godzinę przebiegu.
3. **Uruchom teraz** z wyłączonym „Zapisuj limity” — to symulacja: zobaczysz
   plan na dziś bez zmiany limitów.
4. Gdy plan wygląda rozsądnie, włącz **Zapisuj limity** i zapisz.

Wszystkie ustawienia są w jednym miejscu: w panelu (plik `settings.json`
w katalogu danych). W Compose zostają tylko strefa `TZ`, port i katalog danych.
Gdy token wygaśnie, w **Konto Anki** wpisz hasło i kliknij **Odnów logowanie**.

Z wiersza poleceń (bez panelu) konto połączysz tak:

```bash
docker compose run --rm -e ANKI_SYNC_URL=ankiweb -e ANKI_SYNC_USERNAME=ja@example.com \
  -e ANKI_SYNC_PASSWORD='hasło' workload init
```

Aktualizacja ze starszej wersji: jeśli `settings.json` jeszcze nie istnieje,
a stary Compose ma `WORKLOAD_CONFIG`, usługa jednorazowo przepisze te ustawienia
do `settings.json`. Konto jest brane z istniejącego `identity.json`.
`connection.json`, `ANKI_SYNC_PASSWORD_FILE` i `--config` nie są już używane.

## Godzina i cron

Godzinę ustawiasz w panelu (**Plan nauki → Godzina przebiegu**). Dotyczy strefy `TZ`
(domyślnie Europe/Warsaw) i musi wypadać po granicy dnia nauki Anki.
Proces `serve` działa raz dziennie, nadrabia uruchomienie po restarcie i ponawia
nieudany przebieg. Przycisk dashboardu działa niezależnie od tej godziny.

Możesz zamiast wbudowanego harmonogramu użyć crona. Zatrzymaj `workload`,
a pozostaw uruchomiony sam dashboard:

```bash
docker compose stop workload
docker compose up -d dashboard
```

Przykładowy wpis crona (podaj własną bezwzględną ścieżkę do repo i Dockera):

```cron
30 6 * * * cd /srv/anki-toolkit/workload_service && /usr/bin/docker compose run --rm workload run
```

Cron stosuje strefę czasową hosta. W tym trybie `run_at` nie steruje wykonaniem.
Nie włączaj równocześnie dwóch harmonogramów; blokada chroni kolekcję przed
równoległym dostępem, a ponowienia nie podnoszą przydziału tego samego dnia.

## Panel

Panel nie ma logowania — udostępniaj go tylko w zaufanej sieci. Token formularza
chroni tylko przed wywołaniem przez obcą stronę. Układ działa też na telefonie
i w trybie ciemnym.

- **Dziś** — porcja nowych kart (łącznie z już wprowadzonymi), liczba i szacowany
  czas należnych powtórek, powód decyzji, tempo tygodnia i podział na talie.
  Widać też, czy działa symulacja czy zapis, i kiedy jest następny przebieg.
- **Nowe karty — ostatnie dni** — słupki z ostatnich 14 dni; jaśniejsze to symulacja.
- **Historia przebiegów** — ostatnie 200 operacji z powodem, błędem, zmianami
  limitów przed/po i czasem odpowiedzi z ostatniego tygodnia. Przy błędzie zmiany
  nie są oznaczane jako potwierdzone; część mogła trafić na serwer. To historia
  automatu, nie potwierdzenie synchronizacji telefonu.
- **Uruchom teraz** — zwykły przebieg z aktualnym ustawieniem zapisu, także przed
  godziną harmonogramu. W trakcie przebiegu strona sama przeładuje się po jego końcu.
- **Konserwacja** — przywrócenie limitów oraz pobranie kolekcji z serwera.

Błędne wartości w formularzu panel pokazuje nad treścią strony i niczego nie zapisuje.
Worker czyta `settings.json` pod blokadą przed każdym przebiegiem, więc zmiana
obowiązuje od najbliższego przebiegu bez restartu kontenera.

## Konfiguracja

Pola panelu i klucze `settings.json`:

| Klucz | Znaczenie |
|---|---|
| `apply` | `false`: propozycja; `true`: synchronizowanie limitów. |
| `run_at` | Godzina lokalna HH:MM; musi wypadać po granicy dnia Anki. |
| `minutes_per_day` | Cel czasu, domyślnie 15 minut. |
| `max_minutes_per_day` | Górny budżet, domyślnie 30 minut. |
| `new_cards_per_day` | Maksymalne spokojne tempo łącznie, domyślnie 3. |
| `decks` | Talie objęte planem; nadrzędna obejmuje podtalie. Bez talii harmonogram czeka. |
| `split_strategy` | `proportional` dzieli porcję proporcjonalnie do limitów talii, `heaviest_first` najpierw zmniejsza największy. Obie dopuszczają zero. |
| `seconds_per_card` | Czas powtórki; `0` = mediana z 30 dni, bez danych 9 s. |
| `learn_seconds_per_card` | Czas odpowiedzi w nauce; `0` = mediana z 30 dni, bez danych 12 s. |
| `learn_answers_per_new_card` | Odpowiedzi w nauce na wprowadzoną kartę; `0` = z historii, bez danych 2,5. |

Usługa może zmniejszać porcję albo wrócić do skonfigurowanego pułapu; nie
stosuje automatycznie sugestii +1. Nie gwarantuje 15–30 minut: czas odpowiedzi
jest przybliżeniem, istniejące powtórki nadal trzeba wykonać.

## Jak liczona jest porcja

Najpierw należne powtórki i nauka rozpoczętych kart, nowe karty tylko z zapasu:

- Każda zaległość (karta po terminie) oznacza dziś zero nowych.
- Jeśli należna kolejka zajmuje co najmniej 80% górnej granicy czasu — zero nowych.
- Z czasu zwykłego dnia plan odejmuje zapisany dziś czas odpowiedzi, szacowany
  koszt kolejki i już wprowadzone nowe karty, a 20% zostawia w zapasie.
- Przy co najmniej 20 odpowiedziach w ostatnich 7 zakończonych dniach udział
  „Ponownie” od 30% zmniejsza tempo o jedną kartę, od 50% wstrzymuje nowe.
- Dzień ponad górną granicę czasu w ostatnim tygodniu zmniejsza tempo o jedną kartę.
- Po tygodniu bez nauki powrót zaczyna się od najwyżej trzech nowych dziennie.
- Po dwóch pełnych, spokojnych tygodniach raport sugeruje +1 — tylko jako tekst;
  pułap zmieniasz sam w panelu.

To ostrożne heurystyki, nie model przyszłych powtórek. Do porównania scenariuszy
służy symulator FSRS w Opcjach talii Anki. Historia jest przypisywana do talii
macierzystej (także kart z talii filtrowanych); czas z Anki nie obejmuje przerw.

## Offline, konflikty i wyłączenie

Usługa zmienia wyłącznie limity nowych kart wybranych talii. Bazowy limit
„ta talia” wynosi zero, a porcja jest nadpisaniem „tylko dziś”. Rodzic ogranicza
łączną porcję swoich podtalii. Ponowienie nie zwiększa przydziału tego samego dnia.
Po wygaśnięciu przydziału offline zostają powtórki, ale nie nowe karty. Jeśli
telefon jeszcze nigdy nie pobrał tych ustawień, obowiązują jego stare limity.

Zwykła synchronizacja scala odpowiedzi wykonane offline. Automat nie zmienia
kart, historii, FSRS ani limitów powtórek. Do kolejnej synchronizacji telefonu
analizuje niepełną historię; po przesłaniu odpowiedzi uwzględni je w następnym
uruchomieniu. Dwa urządzenia offline nie mają wspólnego bieżącego licznika,
więc ścisłego globalnego limitu nie da się wtedy zagwarantować.

Pełna synchronizacja zatrzymuje zwykły przebieg i harmonogram (także po restarcie).
Panel pokazuje **Wymagana interwencja** z przyciskiem (także w **Konserwacja**) — możesz wybrać
**Pobierz kolekcję z serwera** po potwierdzeniu, że urządzenia wysłały aktualne dane.
Operacja pobiera wyłącznie do repliki Workload; nie wysyła pełnej kolekcji.
Zapisuje kopię kolekcji i stanu w `user_files/before-download-*/`, zachowuje stan
limitów i sprawdza jego zgodność z pobranymi taliami. Niezgodność lub błąd pobrania
pozostawia dotychczasową replikę i wstrzymany harmonogram; szczegóły są w historii.
Udane pobranie odblokowuje harmonogram; **Uruchom teraz** pozwala przeliczyć limity
od razu. Odpowiednik CLI: `docker compose run --rm workload download`. Nie wybieraj w ciemno
pobrania całej kolekcji na telefon z niewysłanymi odpowiedziami.
Telefon jest nadrzędny. Nauka offline (np. na wakacjach) zapisuje talię na
telefonie, więc przy synchronizacji jego starsza kopia limitów wygrywa z porcją
ustawioną przez usługę. Tego dnia obowiązuje wtedy limit z telefonu: wygasła
porcja przy bazowym zerze daje zero nowych kart, powtórki działają normalnie.
Następny przebieg uznaje taki stan za własny i ustawia porcję ponownie — automat
się nie zatrzymuje. Zatrzymuje go dopiero świadoma zmiana: niezerowy limit
bazowy „ta talia” ustawiony ręcznie. Wtedy usługa nie nadpisze zmiany; przywróć
limit 0 albo wykonaj `restore`. Nie uruchamiaj drugiego kontrolera tego samego konta.

Aby wyłączyć automat i przywrócić zapamiętane limity, w panelu użyj
**Konserwacja → Przywróć limity** (wyłącza też zapis limitów). Odpowiednik CLI
(usuń też wpis crona, jeśli go używasz):

```bash
docker compose stop workload
docker compose run --rm workload restore
```

Następnie zsynchronizuj aplikacje. Samo zatrzymanie kontenera pozostawia
bazowy limit zero. `restore` odmawia nadpisania wykrytych obcych zmian;
w takim przypadku uzgodnij limity ręcznie w Anki. Nie usuwaj wolumenu przed
przywróceniem. Przed zmianą zakresu talii wykonaj `restore`.
Przejście na inny serwer lub konto wymaga osobnego świeżego wolumenu i `init`.

## Sprawdzenie

Testy integracyjne używają sztucznych kart i lokalnego oficjalnego serwera:

```bash
WORKLOAD_INTEGRATION=1 python -m unittest discover -s tests -p test_workload_service.py
```

Wymagają zainstalowanego `requirements.txt` i zgodnej wersji Pythona (Docker: 3.13).
Testy logiki bez Anki: `python3 -m unittest tests.test_workload_logic`.
Obejmują synchronizację limitów, naukę offline, ponowienia, przywracanie oraz
wygaśnięcie dziennej porcji. AnkiWeb nie został przetestowany na rzeczywistym
koncie; przed stałym użyciem sprawdź działanie na swoim koncie i aplikacjach.
Wszystkie klienty i serwer muszą obsługiwać limity talii „tylko dziś” i zgodny
protokół synchronizacji. Nie podmieniaj biblioteki Anki bez testu integracyjnego.

Wynik JSON polecenia `run` zawiera też `card_costs`: czas odpowiedzi w sekundach
z 7 zakończonych dni, koszt kohorty wprowadzonej w 14 zakończonych dniach oraz
5 najbardziej czasochłonnych kart (ID, czas, odpowiedzi, Ponownie).
Treść notatek nie trafia do logów. Ten pomiar nie zmienia decyzji o limitach.
Wklej `cid:123…` do wyszukiwarki przeglądarki Anki, aby obejrzeć kartę; przy
częstym „Ponownie” rozważ prostsze pytanie, kontekst lub rozdzielenie znaczeń.

## Dane na dysku i e-mail

Compose montuje `../user_files` do `/data/user_files` w obu kontenerach. Katalog
główny repozytorium jest też dodatkiem Anki, więc w checkoutcie z podpiętą
wtyczką to ten sam `user_files/`, w którym dodatek trzyma `ai_batches.json`
i historię normalizacji audio. Nazwy plików się nie pokrywają; na serwerze bez
Anki nie ma to znaczenia.
Na RPi wszystkie trwałe dane są w **/root/aplikacje/anki-workload/user_files/**:
kolekcja, token, ustawienia, historia i konfiguracja SMTP. Zrób kopię całego
katalogu przy zatrzymanych kontenerach. Nie usuwaj go podczas aktualizacji.

W panelu rozwiń **Powiadomienia e-mail**: podaj host, port, szyfrowanie,
login/hasło (lub lokalny relay bez logowania), nadawcę i jednego odbiorcę.
Włącz wysyłkę i zapisz. Puste hasło zachowuje poprzednie; checkbox pozwala je
usunąć. Hasło SMTP jest zapisane w `mail.json` (uprawnienia 600), nigdy nie
jest odsyłane do formularza ani umieszczane w historii.

Mail jest wysyłany po każdym udanym `run` i `restore`: także bez zmian
limitów i w symulacji. Błąd wysyła jeden alert; identyczne kolejne błędy są
zapisywane w historii bez ponownego maila, również po restarcie. Sukces `run`
lub `restore` resetuje alert, a inny błąd może wysłać nowy. Stan jest zapisany
w `notification_state.json`; nieudana wysyłka SMTP nie oznacza dostarczenia alertu.
Wiadomość zawiera wynik, tryb, czas, powód oraz
wartości przed/po; tylko udany zapis oznacza zmiany jako potwierdzone.
Wersja HTML pokazuje wąską tabelę Talia / Przed / Po z zawijaniem nazw na
telefonie. Wspólny limit bazowy 0 jest opisany pod tabelą; inne wartości są
widoczne przy liczbach. Wiadomość zawiera również zapasową wersję tekstową.
Inicjalizacja, logowanie i ręczne pobranie nie wysyłają wiadomości. Harmonogram uruchamia
przebieg raz dziennie; ponowienia identycznego błędu nie wysyłają kolejnych raportów.
Zatrzymany kontener nie wyśle maila — brak codziennego raportu jest sygnałem
do sprawdzenia usługi, a nie niezależnym monitoringiem jej dostępności.
Błąd SMTP pojawia się w historii, nie cofa synchronizacji i nie uruchamia jej ponownie.
Nie ma kolejki ponowień maili; przerwanie procesu lub błąd dostarczenia może
spowodować brak powiadomienia. `wysłano` oznacza przyjęcie przez serwer SMTP.
