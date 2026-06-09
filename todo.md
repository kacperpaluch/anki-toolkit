# TODO — dalszy rozwój Anki Toolkit

## Kierunek produktu

Najlepszy kierunek to zostawić projekt jako jeden modularny dodatek, ale coraz mocniej prowadzić użytkownika przez jeden główny przepływ:

`Generuj fiszkę` = AI -> Słownik -> TTS

Ustawienia powinny być zapleczem tego przepływu, a nie głównym doświadczeniem. Użytkownik po instalacji ma szybko zrozumieć:
- co jest gotowe,
- czego brakuje,
- gdzie kliknąć, żeby to naprawić,
- czy workflow zadziała na jego typie notatki.

## Zrobione teraz

- Zakładka `Start` została przebudowana z prostej tabeli statusu na dashboard.
- Dashboard pokazuje gotowość pipeline'u, kafelki statusu, podgląd workflow i listę problemów.
- Przyciski `Otwórz` przełączają do odpowiednich zakładek ustawień.

Pliki:
- `settings/status_tab.py`
- `settings/__init__.py`
- `README.md`
- `llm-context.md`

## Priorytet 1: Sprawdź workflow

Cel: dodać przycisk `Sprawdź workflow`, który bezpiecznie sprawdzi konfigurację przed użyciem przycisku `Generuj fiszkę`.

Jak to widzę:
- przycisk w dashboardzie `Start`,
- opcjonalnie drugi przycisk w `AI Generator -> Workflow`,
- wynik w formie krótkiego raportu:
  - Workflow: OK / brak kroków,
  - AI: OK / brak klucza lub modelu,
  - Prompty: OK / brak zadań dla typu notatki,
  - Słownik: OK / brak pola `ang`, `audio`, `IPA`,
  - TTS: OK / brak głosów, zadań lub pola docelowego,
  - Kokoro: opcjonalnie sprawdzenie URL bez generowania audio.

Co edytować:
- `settings/status_tab.py` — dodać przycisk i miejsce na wynik walidacji.
- Nowy plik, np. `settings/workflow_check.py` albo `ai_generator/workflow_check.py` — czysta logika walidacji.
- `ai_generator/workflow.py` — można współdzielić mapowanie kroków workflow, ale nie mieszać UI z walidacją.
- `tts/config.py` — użyć `validate_config()` i `get_tasks()`.
- `dictionary/service.py` — nie wywoływać sieci, tylko walidować pola i konfigurację.

Uwaga implementacyjna:
Pierwsza wersja powinna sprawdzać konfigurację i pola, ale nie wykonywać API. Realny test jednej karty można dodać później jako osobny przycisk.

## Priorytet 2: Lepsze podsumowanie po `Generuj fiszkę`

Cel: po kliknięciu workflow użytkownik powinien wiedzieć, co dokładnie się stało.

Docelowy tooltip lub małe okno:
- AI: uzupełniono `def`, `przyklad`,
- Słownik: pobrano Oxford UK/US, IPA,
- TTS: wygenerowano 3 pliki,
- Pominięto: `audio` już miało dźwięk,
- Błędy: konkretny krok i krótki komunikat.

Co edytować:
- `ai_generator/workflow.py` — zamiast samego `None`/`err` zwracać strukturę wyniku kroku.
- `ai_generator/field_generator.py` — już zwraca `dict[str, str]`, można użyć listy kluczy jako podsumowania AI.
- `dictionary/service.py` — `ProcessNoteResult` już ma część danych, można rozszerzyć o źródła i komunikaty.
- `tts/processor.py` — `process_single_note()` zwraca teraz `bool`; warto dodać wariant zwracający liczby lub obiekt wyniku.

Uwaga implementacyjna:
Nie robić od razu dużego systemu logów. Wystarczy mały `WorkflowStepResult` w `workflow.py`.

## Priorytet 3: Ostatnie działania / diagnostyka

Cel: dać użytkownikowi miejsce, gdzie zobaczy ostatnie błędy AI/TTS/słownika bez konsoli Anki.

Jak to widzę:
- menu `Narzędzia -> Anki Toolkit -> Ostatnie działania...`,
- lista ostatnich 50 zdarzeń,
- filtry: Workflow, AI, Słownik, TTS,
- przycisk kopiowania szczegółów błędu.

Co edytować:
- Nowy moduł pomocniczy, np. `common/activity_log.py`.
- `ai_generator/workflow.py`, `ai_generator/browser_ui.py`, `tts/processor.py`, `dictionary/browser_ui.py` — dopisywać zdarzenia.
- `__init__.py` albo `settings/status_tab.py` — dodać wejście do logu.

Uwaga implementacyjna:
Na start trzymać log w pamięci procesu. Dopiero później rozważyć zapis do pliku w katalogu profilu.

## Priorytet 4: Presety konfiguracji

Cel: zmniejszyć próg wejścia dla nowego użytkownika.

Proponowane presety:
- Angielski pełny: AI -> Oxford -> TTS,
- Minimalny: AI + słownik,
- Tylko TTS,
- Tylko słownik i IPA.

Co edytować:
- Nowy plik, np. `settings/presets.py` z definicjami presetów.
- `settings/status_tab.py` — dodać sekcję startową `Wybierz preset`, jeśli konfiguracja wygląda pusto.
- `settings/ai_generator_tab.py`, `settings/tts_tab.py`, `settings/dictionary_tab.py` — upewnić się, że po zastosowaniu presetu UI zapisuje wartości w tej samej strukturze.
- `config.json` — nie powinien być nadpisywany; preset zapisuje konfigurację użytkownika przez `save_full_config()`.

Uwaga implementacyjna:
Preset powinien pytać przed nadpisaniem istniejących promptów lub zadań.

## Priorytet 5: Wizualny edytor workflow

Cel: workflow powinien wyglądać jak pipeline, nie jak zwykła lista tekstowa.

Jak to widzę:
- bloki kroków: `AI`, `Słownik`, `TTS`,
- między nimi strzałki,
- w bloku krótki opis konfiguracji,
- akcje: przesuń, usuń, edytuj.

Co edytować:
- `settings/ai_generator_tab.py` — przebudować część Workflow.
- Można wydzielić widget do nowego pliku, np. `settings/workflow_widget.py`.
- `config.json` zostaje bez zmian: lista `workflow.steps` jest wystarczająca.

Uwaga implementacyjna:
Najpierw poprawić czytelność obecnego UI, dopiero potem robić bardziej złożony custom widget.

## Priorytet 6: Lepszy onboarding po instalacji

Cel: po pierwszym uruchomieniu użytkownik nie powinien zgadywać, od czego zacząć.

Jak to widzę:
- dashboard wykrywa pustą konfigurację,
- pokazuje 3 kroki:
  1. wybierz/potwierdź typ notatki i pola,
  2. dodaj dostawcę AI,
  3. sprawdź workflow,
- każdy krok ma przycisk prowadzący do właściwej zakładki.

Co edytować:
- `settings/status_tab.py` — wykrywanie pustej konfiguracji i sekcja onboardingowa.
- `settings/presets.py` — jeśli powstaną presety, onboarding może ich używać.
- `README.md` — skrócić instrukcję startu do jednego przepływu.

## Priorytet 7: Dopracowanie rytmu UI

Cel: mniej wrażenia surowego formularza Qt.

Zmiany:
- spójne marginesy i odstępy,
- krótsze etykiety,
- mniej sekcji widocznych naraz,
- zaawansowane ustawienia domyślnie schowane lub wyraźnie oddzielone,
- konsekwentne nazwy: dostawca, workflow, TTS, słownik, czyszczenie HTML.

Co edytować:
- `settings/ai_generator_tab.py`
- `settings/tts_tab.py`
- `settings/dictionary_tab.py`
- `settings/narzedzia_tab.py`
- `settings/status_tab.py`

Uwaga implementacyjna:
Nie dodawać ozdobników. To ma być spokojny panel roboczy, szybki do skanowania.

## Priorytet 8: Testy czystej logiki

Cel: utrzymać stabilność bez uruchamiania Anki.

Co warto dopisać:
- test walidatora workflow,
- test mapowania kroków workflow na opis pipeline'u,
- test presetów,
- test `nbsp_remover.cleaning.clean_field()` dla większej liczby przypadków,
- test renderowania promptów z pustymi polami i zagnieżdżonym `{% if %}`.

Co edytować:
- `tests/test_pure_logic.py`
- nowe testy w `tests/`, jeśli plik zacznie być zbyt duży.

## Rzeczy, których na razie bym nie robił

- Nie dzielić dodatku na osobne wtyczki.
- Nie dodawać kolejnych dostawców AI, dopóki workflow i onboarding nie są dopracowane.
- Nie robić ciężkiego systemu logów na plikach, dopóki nie ma prostego logu w UI.
- Nie robić realnych wywołań AI/TTS z dashboardu bez wyraźnego przycisku i ostrzeżenia.
