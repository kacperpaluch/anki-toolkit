# Workload Service — codzienny klient synchronizacji

Samodzielny proces bez GUI, uruchamiany na własnej maszynie. Korzysta z oficjalnej
biblioteki `anki==26.8.1` i wspólnej logiki modułu Workload z Anki Toolkit. Obsługuje AnkiWeb
oraz własny serwer zgodny z protokołem Anki (w tym oficjalny self-hosted server).
Nie montuje ani nie edytuje bazy serwera: ma własną kopię kolekcji, jak kolejna
aplikacja. Nie wymaga włączonego macOS ani dodatku.

## Uruchomienie Docker Compose

Najpierw zsynchronizuj istniejącą kolekcję z wybranym serwerem w swojej aplikacji.
W katalogu `workload_service` edytuj **compose.yaml**. Wszystkie ustawienia są
w jednym miejscu: `ANKI_SYNC_URL` (`ankiweb` lub URL własnego serwera),
`ANKI_SYNC_USERNAME`, `ANKI_SYNC_PASSWORD`, `TZ` i obiekt `WORKLOAD_CONFIG`.
Wpisz nazwy swoich talii w `decks`. Nie potrzebujesz `.env`, pliku hasła ani
montowanego `config.json`. Literalny znak `$` w haśle zapisz jako `$$`, aby
Compose nie potraktował go jako zmiennej. Nie commituj pliku z prawdziwym hasłem.

```bash
docker compose build
docker compose run --rm workload init
docker compose run --rm workload run
docker compose up -d
```

`init` pobiera całą kolekcję do świeżego prywatnego wolumenu. `run` przy
`apply: false` pokazuje propozycję bez zmiany limitów. Po sprawdzeniu propozycji
ustaw `apply: true` w Compose i wykonaj `docker compose up -d`.
Zmiany Compose wymagają odtworzenia kontenerów tym poleceniem.
Token hkey pozostaje w prywatnym wolumenie; po inicjalizacji możesz wyczyścić
hasło w Compose. Gdy token wygaśnie, wpisz hasło i wykonaj
`docker compose run --rm workload login`. Starszy sposób z
`ANKI_SYNC_PASSWORD_FILE` i `--config` nadal działa (także dla `dashboard`,
który przekazuje tę ścieżkę uruchamianym przebiegom); `WORKLOAD_CONFIG` ma
pierwszeństwo nad plikiem konfiguracyjnym. Przebieg czyta ustawienia ponownie
pod blokadą workera, więc wyłączenie `apply` w panelu obowiązuje od najbliższego
przebiegu.

## Godzina i cron

W `WORKLOAD_CONFIG` ustaw np. `"run_at": "06:30"`. Godzina dotyczy strefy `TZ`
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

## Dashboard

Otwórz **http://ADRES-SERWERA:8070**. Port jest dostępny na interfejsach sieciowych serwera.
Panel nie ma logowania — udostępniaj go tylko w zaufanej sieci.

Na górze pokazuje wynik ostatniej operacji, budżet nauki i ustawioną godzinę
harmonogramu. Ustawienia oraz naprawa synchronizacji są w zwijanych sekcjach.
Historia ma rozwinięty najnowszy wpis; starsze rozwiniesz kliknięciem.
Układ dopasowuje się do ekranu telefonu.

Pokazuje ostatnie 200 zakończonych przebiegów: czas rozpoczęcia i zakończenia,
sukces lub błąd, tryb symulacji/zapisu, powód decyzji i wartości limitów przed/po.
Przy błędzie planowane zmiany nie są oznaczane jako potwierdzone; część mogła
już trafić na serwer. Historia jest zapisana w `user_files/history.json`.
To historia automatu, nie potwierdzenie synchronizacji telefonu.

**Uruchom teraz** wykonuje pełny zwykły przebieg z aktualnym `apply`, również
przed godziną harmonogramu. Nie wymusza pełnego nadpisania kolekcji.
Po kliknięciu panel pokazuje działający proces. Wynik sprawdzisz przyciskiem
**Odśwież historię**. Strona nie odświeża się automatycznie.
Blokada kolekcji zapobiega równoległemu zapisowi przez harmonogram i przycisk.
Panel i worker współdzielą ustawienia przez kotwicę YAML oraz prywatny wolumen.

## Konfiguracja

| Klucz | Znaczenie |
|---|---|
| `apply` | `false`: propozycja; `true`: synchronizowanie limitów. |
| `run_at` | Godzina lokalna HH:MM; musi wypadać po granicy dnia Anki. |
| `minutes_per_day` | Cel czasu, domyślnie 15 minut. |
| `max_minutes_per_day` | Górny budżet, domyślnie 30 minut. |
| `new_cards_per_day` | Maksymalne spokojne tempo łącznie, domyślnie 3. |
| `decks` | Wymagana niepusta lista nazw normalnych talii. |
| `split_strategy` | `proportional` lub `heaviest_first`. |

Pozostałe parametry obliczeń i ich domyślne wartości opisuje
[Plan nauki](../workload/README.md#ustawienia).
Ustawienia modułu w Anki i usługi są niezależne. Usługa może zmniejszać porcję
albo wrócić do skonfigurowanego pułapu; nie stosuje automatycznie sugestii +1.
Nie gwarantuje 15–30 minut: czas odpowiedzi jest przybliżeniem, istniejące
powtórki nadal trzeba wykonać. Ogranicza dopływ nowych kart.

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
Panel pokazuje **Wymagana interwencja**. W **Napraw synchronizację** możesz wybrać
**Pobierz kolekcję z serwera** po potwierdzeniu, że urządzenia wysłały aktualne dane.
Operacja pobiera wyłącznie do repliki Workload; nie wysyła pełnej kolekcji.
Zapisuje kopię kolekcji i stanu w `user_files/before-download-*/`, zachowuje stan
limitów i sprawdza jego zgodność z pobranymi taliami. Niezgodność lub błąd pobrania
pozostawia dotychczasową replikę i wstrzymany harmonogram; szczegóły są w historii.
Udane pobranie odblokowuje harmonogram; **Uruchom teraz** pozwala przeliczyć limity
od razu. Odpowiednik CLI: `docker compose run --rm workload download`. Nie wybieraj w ciemno
pobrania całej kolekcji na telefon z niewysłanymi odpowiedziami.
Telefon z dawnymi ustawieniami może przy synchronizacji przywrócić starsze
limity talii; historia odpowiedzi pozostaje zachowana, ale automat może się
zatrzymać. Dlatego po pierwszym zastosowaniu planu zsynchronizuj wszystkie
urządzenia przed dalszą nauką.
Ręczne zmiany limitów lub konflikt synchronizacji mogą zatrzymać automat;
sprawdź logi. Anki rozstrzyga konflikty także według czasu modyfikacji talii:
nie edytuj równolegle zarządzanych limitów. Usługa nie nadpisuje wykrytej obcej
zmiany. Nie uruchamiaj drugiego kontrolera tego samego konta.

Aby wyłączyć automat i przywrócić zapamiętane limity (usuń też wpis crona, jeśli go używasz):

```bash
docker compose stop workload dashboard
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
Obejmują synchronizację limitów, naukę offline, ponowienia, przywracanie oraz
wygaśnięcie dziennej porcji. AnkiWeb nie został przetestowany na rzeczywistym
koncie; przed stałym użyciem sprawdź działanie na swoim koncie i aplikacjach.
Wszystkie klienty i serwer muszą obsługiwać limity talii „tylko dziś” i zgodny
protokół synchronizacji. Nie podmieniaj biblioteki Anki bez testu integracyjnego.

Wynik JSON polecenia `run` zawiera też `card_costs`: czas odpowiedzi w sekundach
z 7 zakończonych dni, koszt kohorty wprowadzonej w 14 zakończonych dniach oraz
5 najbardziej czasochłonnych kart (ID, czas, odpowiedzi, Ponownie).
Treść notatek nie trafia do logów. Ten pomiar nie zmienia decyzji o limitach;
szczegóły interpretacji opisuje [Plan nauki](../workload/README.md#co-zabiera-czas).

### Konfiguracja w panelu

Możesz uruchomić samo `docker compose up -d --build` i rozwinąć **Ustawienia i konto Anki**.
Wpisz serwer, login, hasło, nazwy talii, godzinę i budżet. **Zapisz ustawienia / zaloguj**
zapisuje ustawienia, a podane hasło uruchamia inicjalizację (pierwszy raz) lub
odnowienie tokenu (istniejąca kopia). Poczekaj na sukces w historii, następnie
kliknij **Uruchom teraz**. Zacznij od odznaczonego **Zapisuj limity**.

Ustawienia panelu są trwałe w wolumenie (`settings.json`, `connection.json`) i mają
pierwszeństwo nad Compose. Worker odczytuje je przed kolejnym przebiegiem;
nie trzeba restartować kontenera. Strefę `TZ` i port nadal ustawiasz w Compose.
Hasło z formularza jest przekazywane tylko do procesu logowania, nie jest zapisywane
w plikach ani historii. Panel nie ma logowania. Token formularza chroni tylko
przed przypadkowym wywołaniem przez obcą stronę, nie ogranicza dostępu w LAN.

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
