# LLM Context — Anki Toolkit

Ten plik jest zawsze czytaną mapą projektu. Zawiera reguły przekrojowe i kieruje
do szczegółowego kontekstu tylko tego obszaru, którego dotyczy zadanie.

## Projekt w skrócie

Anki Toolkit jest dodatkiem do Anki napisanym w Pythonie i PyQt. Techniczne
moduły są niezależnie przełączane, lecz interfejs grupuje je w cztery domeny:

| Domena | Moduły |
|---|---|
| Treść | `ai_generator`, `dictionary`, `tts`, `field_splitter`, workflowy |
| Nauka | `filtered_deck`, `homograph_manager` |
| Integracje | `word_queue`, `web_bridge` |
| System | `audio_normalizer`, `audio_embed`, `nbsp_remover`, `field_hider` |

Entry point: `__init__.py`. Domyślna konfiguracja: `config.json`. Konfiguracja
profilu Anki jest obsługiwana przez `mw.addonManager` i zapisywana w `meta.json`.

## Routing kontekstu

Przed zmianą przeczytaj tylko odpowiedni plik:

| Zadanie | Kontekst |
|---|---|
| AI, prompty, providerzy, workflowy, Batch API | `ai_generator/llm-context.md` |
| TTS, głosy, generowanie audio | `tts/llm-context.md` |
| Słowniki, audio słownikowe, IPA | `dictionary/llm-context.md` |
| Talie filtrowane i presety powtórek | `filtered_deck/README.md` |
| Rozkładanie homografów (osobne notatki, to samo słowo) | `homograph_manager/llm-context.md` |
| Kolejka n8n, panel słowników, Web Bridge | `word_queue/llm-context.md` oraz README Web Bridge |
| Prosty moduł narzędziowy | README modułu i jego kod |
| Klucze konfiguracyjne | `config.md` i `config.json` |

Nie czytaj wszystkich kontekstów modułowych bez potrzeby.

## Ładowanie dodatku

Anki importuje główny `__init__.py` podczas startu. Loader:

1. Czyta `config["modules"]`.
2. Importuje włączone moduły.
3. Rejestruje hooki edytora, synchronizacji i Add Cards.
4. Rejestruje jedno wspólne menu kontekstowe Browsera.
5. Po inicjalizacji okna tworzy menu **Narzędzia → Anki Toolkit**.

Wyłączenie modułu wymaga restartu. Importy modułów nie są izolowane: wyjątek
podczas importu może zatrzymać ładowanie całego dodatku. Nie twierdź, że awaria
jednego modułu jest automatycznie izolowana.

## Struktura

```text
__init__.py              rejestracja modułów i hooków
common/                  HTTP, tekst, konfiguracja, logi, UI, progress, guard edytora
settings/                domenowy dialog ustawień
ai_generator/            generowanie pól, workflowy, providerzy, Batch API
dictionary/              pobieranie nagrań i IPA
tts/                     synteza oraz zapis audio
filtered_deck/           presety talii filtrowanej
homograph_manager/       rozkłada w czasie osobne notatki z tym samym słowem
field_splitter/          czyste dzielenie pola i akcje batch
audio_normalizer/        ffmpeg, historia i watcher katalogu mediów
audio_embed/             [sound:...] → <audio> w wybranych typach notatek i polach
nbsp_remover/            normalizacja HTML
field_hider/             widoczność pól w Add Cards
web_bridge/              lokalny serwer HTTP i userscript
word_queue/              n8n DataTable i dock ze słownikami
tests/                   testy logiki bez działającej instancji Anki
user_files/              trwałe dane robocze
```

## Najważniejsze niezmienniki

### Anki i wątki

- Kolekcja Anki jest jednowątkowa. Pobieraj i zapisuj notatki na głównym wątku.
- Worker może wykonywać HTTP, AI, TTS i ffmpeg oraz przetwarzać dane w pamięci.
- Operacje kolekcji uruchamiane z UI powinny używać `CollectionOp`, jeśli pasuje
  do przepływu.
- Po mutacji ręcznej zwróć poprawne `OpChanges`, aby Anki odświeżyło widok.
- Callback Qt musi sprawdzać, czy jego widget nadal istnieje, jeśli praca może
  zakończyć się po zamknięciu okna.

### Hooki i menu

- Hook menu kontekstowego Browsera jest rejestrowany tylko w root `__init__.py`.
- Moduły eksportują `add_to_context_menu(browser, menu)`.
- Moduły menu Narzędzia eksportują `setup_menu(parent_menu=None)`.
- Przyciski edytora rejestruje root przez `editor_did_init_buttons`.
- Nie rejestruj drugiego globalnego submenu Anki Toolkit w module.

### Konfiguracja

- `config.json` jest szablonem, nie aktywną konfiguracją użytkownika.
- Czytaj przez helpery `common.config` albo `mw.addonManager`.
- Zapisując jedną sekcję, nie usuwaj obcych kluczy.
- Pełna referencja opcji należy wyłącznie do `config.md`; nie kopiuj dużych
  fragmentów JSON do kontekstów modułowych.

### Dane trwałe

- Dane generowane podczas pracy zapisuj w `user_files/`.
- Zapisy plików współdzielonych przez workery muszą być chronione blokadą.
- Nie commituj danych profilu użytkownika ani kluczy API.

## Ustawienia

`settings/__init__.py` tworzy dziewięć stron:

```text
Start
Treść: Workflowy, Generowanie AI, Wymowa
Nauka: Reguły kart
Integracje: Integracje
System: Moduły, Konserwacja, Diagnostyka
```

`settings/domain_tabs.py` składa istniejące panele techniczne w domeny i deleguje
ich `apply(cfg)`. `settings/narzedzia_tab.py` zawiera małe współdzielone panele,
a nie jedną użytkową zakładkę „Narzędzia”.

Ekran Start nie jest pełnym audytem konfiguracji. Pokazuje:

- gotowość pierwszego lub oznaczonego przyciskiem workflow,
- aktywne zadania Batch API,
- tylko problemy blokujące kroki tego workflow.

Nie dodawaj tam statusu każdego opcjonalnego modułu.

## Zależności między domenami

```text
workflow
  ├── ai_generator
  ├── dictionary
  ├── tts
  └── field_splitter

word_queue ──czyta userscript──> web_bridge/dictionaries-to-anki.user.js

dictionary + tts + audio_normalizer
  └── wspólny katalog mediów Anki
```

Unikaj nowych importów między domenami. Jeżeli integracja jest opcjonalna,
preferuj lokalny soft-import w miejscu wywołania.

## Jak dodać funkcję

### Do istniejącej domeny

1. Umieść logikę przy odpowiednim module.
2. Oddziel czystą logikę od Qt i Anki API.
3. Dodaj test czystej logiki.
4. Podepnij istniejący panel domenowy zamiast tworzyć nową główną zakładkę.
5. Uaktualnij `config.md`, właściwy README i tylko właściwy kontekst domenowy.

### Nowy moduł

1. Dodaj katalog z `__init__.py`.
2. Dodaj klucz w `config.json`, `settings/modules_tab.py` i root loaderze.
3. Zarejestruj hook w root `__init__.py`.
4. Przypisz moduł do jednej z czterech domen UI.
5. Nie twórz osobnego `llm-context.md`, jeśli kod jest mały i lokalny.

## Testy

Testy używają `unittest` i stubów Anki. Działają bez instalacji `anki`:

```bash
python3 tests/test_pure_logic.py
python3 tests/test_batch_backfill.py
python3 tests/test_editor_operations.py
python3 tests/test_audio_embed.py
```

Zwykłe `pytest` może próbować zaimportować root `__init__.py`; konfiguracja
pytest musi ograniczyć kolekcję do `tests/` lub dostarczyć stuby środowiska Anki.

## Kontrola przed zakończeniem zmiany

- Czy operacje kolekcji pozostają na głównym wątku?
- Czy wyłączony moduł nie rejestruje hooków?
- Czy konfiguracja zachowuje nieznane klucze?
- Czy nowa funkcja trafiła do istniejącej domeny UI?
- Czy opisano niezmiennik, zamiast kopiować implementację?
- Czy testy czystej logiki przechodzą?
