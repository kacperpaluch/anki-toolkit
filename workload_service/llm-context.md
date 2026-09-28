# LLM Context — Workload Service

Klient headless w Dockerze: codziennie pobiera zmiany z serwera Anki do własnej
repliki, liczy ostrożną porcję nowych kart i wysyła ją jako limit talii
„tylko dziś”. Nie jest częścią dodatku; niczego z niego nie importuje.

## Pliki

- `logic.py` — czysty plan (bez Anki): `analyze(snapshot, settings)` zwraca
  `Report` z `StudyPlan`; `scale_limits` dzieli porcję między talie.
- `snapshot.py` — odczyt kolekcji do słownika (karty, revlog), bez zapisów.
- `worker.py` — CLI, sync, stan limitów, harmonogram, historia i e-mail.
- `dashboard.py` — panel HTTP; przebiegi uruchamia jako osobny proces `worker.py`.

Ustawienia: jedynym źródłem jest `settings.json` (edytuje go tylko panel przez
`worker.save_settings`, walidacja w `worker.validate`, nieznane klucze zostają).
Konto pochodzi z `identity.json` zapisanego przy `init`; zmienne `ANKI_SYNC_*`
są tylko wejściem dla `init`/`login`, nie ustawieniem. `WORKLOAD_CONFIG` jest
czytane jednorazowo, gdy `settings.json` nie istnieje (migracja). Worker czyta
ustawienia pod blokadą; `decks.json` (lista talii dla panelu) odświeża każdy sync.
Przywrócenie z panelu najpierw wyłącza `apply`, żeby harmonogram nie nałożył
limitów ponownie.
- `notifications.py` — raporty SMTP i deduplikacja alertów.

Importy: `from . import x` w pakiecie (testy), fallback `import x` przy
uruchomieniu jako skrypt (`/app/worker.py` w obrazie).

## Niezmienniki planu

- Każda zaległość (termin < dziś) daje zero nowych. Kolejka zajmująca >=80%
  górnej granicy czasu wstrzymuje nowe. Plan odejmuje dzisiejszy czas
  odpowiedzi, koszt należnych powtórek/nauki i już wprowadzone nowe karty
  i zostawia 20% zapasu zwykłego czasu.
- `new_cards_per_day` to pułap. Automat może zejść niżej (−1 przy dniu ponad
  górną granicę lub >=30% „Ponownie” przy >=20 odpowiedziach z 7 zakończonych dni,
  0 przy >=50%), ale +1 zostaje tylko tekstem w `weekly_reason`.
- Bez nauki przez 7 zakończonych dni powrót ma tempo <=3.
- Dzień historii liczony wstecz od `sched.day_cutoff`; typy revlog 0–3 są nauką,
  4/5 pomijane. Historia przypisywana do talii macierzystej (`odid or did`).
  Pierwszy wpis typu 0 liczy wprowadzenie karty tylko raz.
- Kolejka 1 to osobny licznik nauki; kolejki 2/3 dają terminy. Zapas nowych
  obejmuje zakopane nowe, wyklucza zawieszone.
- `card_costs` (7 zakończonych dni, kohorta 14 dni, top 5 kart) jest tylko
  diagnostyką w historii i mailu; nie steruje limitami.

## Niezmienniki limitów

- Zarządzane są wyłącznie `newLimit` i `newLimitToday` wybranych talii. Bazowy
  `newLimit` = 0, porcja to `newLimitToday`; awaria usługi = zero nowych.
- Porcja danego dnia nigdy nie rośnie (`state.daily`), a `pending` jest
  zapisywane przed wysyłką — ponowienie nie daje więcej kart.
- Telefon jest nadrzędny: nauka offline zapisuje całą talię (nowszy `mod`),
  więc stara kopia naszych limitów może wygrać sync. `worker.ours()` uznaje
  każdy stan z bazowym `newLimit == 0` za własny i nakłada plan ponownie.
  Tylko niezerowy limit bazowy to świadoma zmiana, która zatrzymuje automat.
- Konflikty talii Anki rozstrzyga z dokładnością do sekundy — testy
  integracyjne czekają 1,1 s przed edycją, która ma wygrać.
- Pełny sync nigdy nie jest automatyczny: `intervention.json` wstrzymuje
  harmonogram do ręcznego `download` (backup + zgodność limitów).

Testy: `tests/test_workload_logic.py` (logika, SQLite w pamięci) oraz
`tests/test_workload_service.py` (z `WORKLOAD_INTEGRATION=1` na lokalnym
oficjalnym serwerze sync).
