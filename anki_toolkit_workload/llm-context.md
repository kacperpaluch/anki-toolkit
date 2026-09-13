# LLM Context — Anki Toolkit: Workload

## Zakres

Raport obciążenia nauką: budżet czasu, zmierzone obciążenie z interwałów,
projekcja z dopływu nowych kart, trend, prognoza terminów i uwagi o spójności
limitów.

## Niezmienniki

- Dodatek jest **wyłącznie do odczytu**. Nie wywołuje `update_config`, `save`,
  `set_config` ani żadnej operacji `CollectionOp`. Propozycje limitów są tekstem
  w raporcie, nigdy zapisem.
- `logic.py` nie importuje Anki ani Qt. Wejściem jest migawka-słownik z
  `build_snapshot`, więc liczby i renderowanie są testowalne bez Anki.
- **Pomiar i projekcja są rozdzielone.** `structural_load` (suma `1/ivl`) jest
  właściwością kolekcji i nie zależy od historii. `steady_state` jest projekcją
  przez współczynnik „powtórek na nową kartę” i zawsze niesie informację o
  źródle tego współczynnika. Nie wolno ich sumować ani mieszać w jednym zdaniu.
- Budżet czasu odejmuje koszt nowych kart, zanim policzy sufit powtórek —
  nowa karta kosztuje `odpowiedzi_w_nauce × czas_nauki` w dniu wprowadzenia.
- **Sufit powtórek nie jest tą samą liczbą dla korzenia i dla podtalii.** Ta
  sama wartość w każdej podtalii nie ogranicza sumy; korzeń (talia, której
  żaden przodek nie jest w raporcie) dostaje całość, podtalie udział
  proporcjonalny do dopływu. Rozdziela to `_assign_review_ceilings`.
- Przesunięcia terminów zbierane są tylko z kolejek 2 i 3. W kolejce 1 (nauka
  wewnątrz dnia) pole `due` jest znacznikiem czasu, nie numerem dnia.
- Do zapasu nowych kart wchodzą też karty zakopane (kolejki −2 i −3 z `type`
  równym 0), bo wrócą. Zawieszone (−1) są wykluczone w zapytaniu.
- Interwał 0 (kolejka 3) liczy się jak 1 dzień — `1/max(1, ivl)` chroni przed
  dzieleniem przez zero.
- `odid` karty wskazuje talię macierzystą, więc karty wyciągnięte do talii
  filtrowanej liczą się do swojej talii źródłowej. Same talie filtrowane (`dyn`)
  są pomijane — nie mają własnego dopływu.
- Do sumy dopływu wchodzą tylko talie z pozostałym zapasem nowych kart.
  Inaczej szeroki limit talii nadrzędnej bez własnych kart zawyża wynik.
- Talia bez własnych kart trafia do raportu tylko wtedy, gdy jest przodkiem
  talii z kartami: jej preset obowiązuje przy „limitach od góry”, więc musi być
  widoczny, ale z zerowym zapasem nie wchodzi do sumy dopływu.
- Limit „Ta talia” (`newLimit`, `reviewLimit` w słowniku talii) ma pierwszeństwo
  nad wartością z presetu.
- Historia mierzona jest w **dniach z faktyczną nauką** (`count(distinct` numer
  dnia `)`), nie w rozpiętości kalendarzowej — przerwa w nauce nie może udawać
  historii. Numer dnia liczy się z `col.crt`, żeby zgadzał się z `sched.today`.
- Szereg dzienny dla trendu musi zawierać zera dla dni bez nauki, inaczej
  przerwa wygląda jak spadek obciążenia.
- Klucze konfiguracji kolekcji odczytywane przez `_flags`: `fsrs`,
  `loadBalancerEnabled`, `newCardsIgnoreReviewLimit`, `applyAllParentLimits`
  (zweryfikowane w Anki 26.8.1). **Brak klucza daje `None` i nie jest błędem;
  wyjątek przy odczycie ląduje w `flag_errors` i jest raportowany**, bo po cichu
  wycinałby powiązane uwagi.
- Progi pomiarowe: `MIN_ACTIVE_DAYS_FOR_RATIO` dla współczynnika powtórek,
  `MIN_ACTIVE_DAYS_FOR_TREND` dla trendu, `MIN_TREND_SLOPE` odsiewa szum.

`logic.py` liczy i renderuje (HTML dla okna, tekst dla schowka), `__init__.py`
zbiera migawkę z `mw.col` i pokazuje okno, `settings.py` edytuje budżet czasu,
parametry pomiaru i strategię podziału. **Narzędzia → Anki Toolkit: Workload…**
otwiera raport; „Kopiuj raport” i „Ustawienia…” są przyciskami w tym samym
oknie, a zapis ustawień przelicza raport od nowa.

Testy: `tests/test_workload_standalone.py`. Warstwa odczytu testowana jest na
atrapach `aqt` i **prawdziwym SQLite w pamięci**, żeby zapytania wykonywały się
naprawdę.
