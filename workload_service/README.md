# Workload — codzienny klient synchronizacji

Samodzielny proces bez GUI, uruchamiany na własnej maszynie. Korzysta z oficjalnej
biblioteki `anki==26.8.1` i wspólnej logiki dodatku Workload. Obsługuje AnkiWeb
oraz własny serwer zgodny z protokołem Anki (w tym oficjalny self-hosted server).
Nie montuje ani nie edytuje bazy serwera: ma własną kopię kolekcji, jak kolejna
aplikacja. Nie wymaga włączonego macOS ani dodatku.

## Uruchomienie Docker Compose

Najpierw zsynchronizuj istniejącą kolekcję z wybranym serwerem w swojej aplikacji.
W katalogu `workload_service` utwórz `.env`:

```dotenv
ANKI_SYNC_URL=ankiweb
ANKI_SYNC_USERNAME=twoj-adres-email
```

Dla własnego serwera zamiast `ankiweb` wpisz pełny adres HTTP(S), dostępny
z kontenera, oraz jego nazwę użytkownika. Nie wpisuj danych logowania w URL.
Dla serwera poza zaufaną siecią używaj HTTPS.

Utwórz `user_files/anki_password.txt` z hasłem (pojedyncza linia), nadaj plikowi
uprawnienia 600. Plik oraz `.env` są ignorowane przez Git. W `config.json` wpisz
prawdziwe nazwy wybranych talii; rodzic obejmuje podtalie. Pozostaw `apply: false`.

```bash
mkdir -p user_files
# Utwórz plik hasła w edytorze, następnie:
chmod 600 user_files/anki_password.txt
docker compose build
docker compose run --rm workload init
docker compose run --rm workload run
```

`init` pobiera całą kolekcję do świeżego prywatnego wolumenu; nigdy jej nie
wysyła. `run` przy `apply: false` synchronizuje kopię i wypisuje propozycję,
bez zmiany limitów. Sprawdź nazwy talii i proponowane wartości. Następnie ustaw
`apply: true` i uruchom:

```bash
docker compose run --rm workload run
docker compose up -d
docker compose logs --tail 30 workload
```

Pierwsze polecenie stosuje plan od razu. Usługa wykonuje kolejne plany o 05:00
w strefie `Europe/Warsaw`; po restarcie nadrabia dzisiejsze uruchomienie.
Synchronizuj telefon przed i po nauce. Usługa nie synchronizuje mediów.

Token `hkey` jest zapisywany w prywatnym wolumenie, w `user_files/auth.json`
z uprawnieniami 600. Po inicjalizacji możesz opróżnić plik hasła, pozostawiając
plik wymagany przez Docker secrets. Przy wygaśnięciu tokenu wpisz hasło ponownie
i wykonaj `docker compose run --rm workload login`. Token daje dostęp do konta;
chroń cały wolumen i jego kopie. Przekierowania AnkiWeb są ograniczone do HTTPS
w domenie ankiweb.net; własny serwer może zmieniać ścieżkę w tym samym originie.

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
[Workload](../anki_toolkit_workload/README.md#ustawienia).
Ustawienia dodatku macOS i usługi są niezależne. Usługa może zmniejszać porcję
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

Pełna synchronizacja zawsze zatrzymuje zwykły przebieg. Nie wybieraj w ciemno
pobrania całej kolekcji na telefon z niewysłanymi odpowiedziami.
Telefon z dawnymi ustawieniami może przy synchronizacji przywrócić starsze
limity talii; historia odpowiedzi pozostaje zachowana, ale automat może się
zatrzymać. Dlatego po pierwszym zastosowaniu planu zsynchronizuj wszystkie
urządzenia przed dalszą nauką.
Ręczne zmiany limitów lub konflikt synchronizacji mogą zatrzymać automat;
sprawdź logi. Anki rozstrzyga konflikty także według czasu modyfikacji talii:
nie edytuj równolegle zarządzanych limitów. Usługa nie nadpisuje wykrytej obcej
zmiany. Nie uruchamiaj drugiego kontrolera tego samego konta.

Aby wyłączyć automat i przywrócić zapamiętane limity:

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
Obejmują synchronizację limitów, naukę offline, ponowienia, przywracanie oraz
wygaśnięcie dziennej porcji. AnkiWeb nie został przetestowany na rzeczywistym
koncie; przed stałym użyciem sprawdź działanie na swoim koncie i aplikacjach.
Wszystkie klienty i serwer muszą obsługiwać limity talii „tylko dziś” i zgodny
protokół synchronizacji. Nie podmieniaj biblioteki Anki bez testu integracyjnego.
