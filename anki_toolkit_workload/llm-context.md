# LLM Context — Anki Toolkit: Workload

## Zakres

Elastyczny plan na dziś i ostrożna propozycja tempa nowych kart. Raport
obciążenia i terminy są szczegółami rozwijanymi w tym samym oknie.

## Niezmienniki

- Kolekcja jest **wyłącznie odczytywana**, na głównym wątku. Dodatek nie zmienia
  limitów Anki, kart ani harmonogramu i nie zatrzymuje sesji. Zapisuje tylko
  własne ustawienia przez addonManager, zachowując nieznane klucze.
- `logic.py` nie importuje Anki/Qt. `build_snapshot` dostarcza migawkę-słownik;
  `analyze` zwraca raport z `StudyPlan`. HTML i tekst zawierają ten sam plan.
- `minutes_per_day` (domyślnie 15) jest zwykłym czasem; `new_cards_per_day`
  (domyślnie 3) jest łącznym spokojnym tempem. `max_minutes_per_day` (domyślnie
  30, minimum zwykły cel) wyznacza górną granicę czasu. Czas na dziś jest argumentem
  `analyze`, pozostaje tylko w oknie i nie zmienia propozycji tygodniowej.
- Krótszy dzień i każda zaległość oznaczają zero nowych. Dłuższy dzień nie
  podnosi tempa. Kolejka zajmująca >=80% górnej granicy wstrzymuje nowe. Plan odejmuje dzisiejszy czas odpowiedzi, koszt pozostałych
  powtórek/nauki oraz już wprowadzone nowe karty i zostawia 20% czasu zapasu.
- Podział na talie dopuszcza zero i nigdy nie przekracza porcji na dziś ani
  własnego limitu/zapasu talii. To propozycja, nie emulacja zbierania kart przez
  scheduler: rodzice, zakopywanie i limity „tylko dziś” nadal obowiązują w Anki.
- +1 jest warunkową propozycją po dwóch pełnych tygodniach kalendarzowych z
  >=5 dniami nauki w każdym, czasem <=80% budżetu i rzeczywistym tempem nowych
  odpowiadającym ustawionemu. Nie trafia automatycznie do dzisiejszej porcji.
  Historia odpowiedzi nie dowodzi zakończenia kolejki; UI mówi to wprost.
- Przy >=20 odpowiedziach z 7 zakończonych dni udział Again >=30% proponuje
  −1, >=50% proponuje zero. Wzrost wymaga <=20% Again w każdym pełnym tygodniu
  i dodatnich czasów odpowiedzi w dniach nauki. Typy 0/2 dają koszt nauki.
- Bez nauki przez 7 zakończonych dni powrót ma tempo <=3. Dzień ponad zwykły
  górny limit czasu w ostatnich 7 zakończonych dniach proponuje −1. To heurystyki, nie model
  przyszłych powtórek. Nie ma utrwalanych obserwacji dziennych.
- `_revlog_data` filtruje historię przez obecne macierzyste talie kart
  (`odid or did`), także dla czasu i nowych wprowadzonych dziś. Pierwszy wpis
  typu 0 liczy wprowadzenie tylko raz. Typy 0–3 są nauką; 4/5 są pomijane.
- Dzień historii jest liczony wstecz od `sched.day_cutoff`; `today` w migawce
  to data bieżącego dnia nauki Anki, także przed nocną granicą dnia. Okna
  używają odcinków po 86400 s; przy zmianie czasu graniczna godzina jest przybliżona.
- Kolejka 1 ma termin w sekundach, więc jest osobnym licznikiem rozpoczętych
  kart, nie przesunięciem dni. Kolejki 2/3 dają terminy, `ivl=0` liczy się jak 1.
- Zapas nowych obejmuje zakopane nowe (−2/−3, typ 0), wyklucza zawieszone −1.
  Talie filtrowane nie tworzą własnego dopływu. Pusty rodzic talii z kartami
  pozostaje w raporcie. „Ta talia” ma pierwszeństwo nad limitem presetu.
- Przybliżenie `suma(1/ivl)` i scenariusz `limit × mnożnik` są wyraźnie
  opisane jako przybliżenia. Nie sterują planem. Wysoki limit powtórek nie
  jest alarmem i dodatek nie proponuje obniżania limitów powtórek.
- Brak klucza flagi kolekcji daje `None`; wyjątek daje wpis `flag_errors`.

`snapshot.py` zbiera dane bez Qt; `__init__.py` buduje okno, `settings.py` zawiera jeden dialog
ustawień. **Narzędzia → Anki Toolkit: Workload…** otwiera plan z przyciskami
**Pokaż szczegóły raportu**, **Odśwież**, **Kopiuj raport**, **Ustawienia…**.
Odświeżanie i zapis ustawień przeliczają plan w tym samym oknie.

Testy: `tests/test_workload_standalone.py` — logika oraz odczyt na atrapach
`aqt` z prawdziwym SQLite w pamięci. Zmiany UI sprawdzamy także w Anki.

Osobny `../workload_service/worker.py` współdzieli `logic.py` i `snapshot.py`,
ale sam zapisuje limity przez API Anki i synchronizuje własną replikę.
Niezmiennik wyłącznie odczytu dotyczy dodatku GUI.

`card_costs` w migawce/raporcie: czas typów revlog 0–3 z 7 zakończonych dni,
kohorta z pierwszym dostępnym wpisem typu 0 w 14 zakończonych dniach; ranking
5 kart ze wszystkich wybranych talii, bez treści notatek. Dzisiaj wykluczone.
HTML, tekst i JSON usługi pokazują te dane; nie sterują limitami.
