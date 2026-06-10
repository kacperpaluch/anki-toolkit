# LLM Context — Anki Toolkit

Szybkie podsumowanie projektu dla modeli AI i deweloperów.

---

## Czym jest ten projekt

Scalona wtyczka do Anki łącząca 6 narzędzi w jeden pakiet. Instalowana jako jeden dodatek (`addons21/anki-toolkit/`). Każdy moduł można niezależnie włączyć lub wyłączyć w ustawieniach. Awaria jednego modułu nie blokuje pozostałych.

---

## Stack

| Warstwa | Technologia |
|---|---|
| Język | Python 3.9+ |
| GUI | PyQt6 (dostarczany przez Anki) |
| HTTP | `urllib.request` (stdlib, brak zewnętrznych zależności) |
| HTML parsing | `html.parser` (stdlib) |
| Audio (normalizacja) | ffmpeg (zewnętrzny proces via `subprocess`) |
| AI | REST API (OpenAI / Anthropic / Google Gemini) |
| TTS | Kokoro lokalny serwer (OpenAI-compatible REST) lub OpenRouter TTS API |

**Brak `pip install`** — żadnych zewnętrznych pakietów Python. Jedyną zależnością systemową jest `ffmpeg` (dla `audio_normalizer`).

---

## Struktura i odpowiedzialności

```
anki-toolkit/
├── __init__.py                      # entry point: warunkowo importuje moduły i rejestruje hooki
├── config.json                      # SZABLON domyślny (faktyczna konfiguracja w profilu Anki)
├── config.md                        # dokumentacja konfiguracji
├── manifest.json                    # metadane dla Anki (package name: "anki-toolkit")
│
├── common/                          # współdzielone narzędzia i stałe
│   ├── __init__.py                  # re-eksport wszystkich symboli
│   ├── consts.py                    # ADDON_NAME (wyliczane z __name__ — nazwa folderu wtyczki)
│   ├── html.py                      # clean_html(), clean_html_normalized()
│   ├── text.py                      # unique(), safe_float(), safe_str(), unique_filename(), normalize_float()
│   ├── http.py                      # fetch_url(), fetch_text(), extract_http_error(), RETRYABLE_STATUS_CODES
│   ├── config.py                    # get_full_config(), save_full_config(), get_module_config(), save_module_config()
│   └── ui.py                        # widgety Qt: _expanding_line_edit, _api_key_widget, _scrollable, get_field_names, get_note_type_names, get_fields_for_note_type, get_templates_for_field
│
├── settings/                        # dialog ustawień (wszystkie moduły, jeden UI)
│   ├── __init__.py                  # SettingsDialog, open_settings()
│   ├── status_tab.py                # Zakładka: Start — dashboard konfiguracji
│   ├── modules_tab.py               # Zakładka: Moduły
│   ├── dictionary_tab.py            # Zakładka: Słownik
│   ├── ai_generator_tab.py          # Zakładka: AI Generator
│   ├── prompts_tab.py               # Zakładka: Prompty
│   ├── tts_tab.py                   # Zakładka: TTS
│   ├── audio_normalizer_tab.py      # Zakładka: Normalizacja
│   ├── narzedzia_tab.py             # Zakładka: Narzędzia
│   └── stats_tab.py                 # Zakładka: Statystyki — dashboard użycia AI
│
├── dictionary/                      # Moduł 1
│   ├── __init__.py
│   ├── service.py
│   ├── editor_ui.py
│   ├── browser_ui.py
│   ├── dictionary_service.py
│   └── ipa_service.py
│
├── ai_generator/                    # Moduł 2
│   ├── __init__.py
│   ├── _generator.py
│   ├── editor_ui.py
│   ├── browser_ui.py
│   ├── field_generator.py
│   ├── template_engine.py
│   ├── stats.py                     # lokalne statystyki użycia (usage_stats.json)
│   ├── workflow.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       ├── openai_compat.py
│       ├── openai.py
│       ├── cometapi.py
│       ├── openrouter.py
│       ├── anthropic.py
│       ├── google.py
│       ├── mistral.py
│       ├── opencode_go.py           # OpenCode Go (Chat Completions + Anthropic Messages, auto-detect)
│       └── model_discovery.py
│
├── tts/                             # Moduł 3
│   ├── __init__.py
│   ├── config.py                    # _DEFAULTS, get_tts_config(), validate_config(), get_tasks()
│   ├── api.py                       # generate_audio(), _generate_kokoro(), _generate_openrouter(), fetch_openrouter_tts_models()
│   ├── processor.py                 # process_task_async(), process_tasks_async(), process_single_note() — logika przetwarzania notatek
│   └── editor_ui.py
│
├── filtered_deck/                   # Moduł 4
│   └── __init__.py
│
├── audio_normalizer/                # Moduł 5
│   ├── __init__.py
│   ├── config.py
│   ├── gui.py
│   └── logic.py
│
├── nbsp_remover/                    # Moduł 6
│   ├── __init__.py
│   ├── addcards.py
│   ├── cleaning.py
│   ├── collection.py
│   └── utils.py
│
└── tests/
    └── test_pure_logic.py           # testy czystej logiki bez uruchamiania Anki
```

### Moduły

| Katalog | Co robi | Punkt wejścia |
|---|---|---|
| `common/` | Współdzielone narzędzia: HTML cleaning, HTTP z retry, konfiguracja, widgety Qt — używane przez wszystkie moduły | importowane selektywnie |
| `dictionary/` | Pobiera audio MP3 i IPA z Oxford/Cambridge/Diki/Longman przez scraping HTML; edytor (async, `saveNow` przed fetchowaniem) + submenu batchowe (w tle, z paskiem postępu i anulowaniem) | `on_editor_buttons_init`, `add_to_context_menu` |
| `ai_generator/` | Generuje treść pól kart przez AI (7 dostawców); batch w tle z grupowaniem i anulowaniem; workflow "Generuj fiszkę" (AI → Słownik → TTS); `reasoning_effort` z fallbackiem | `on_editor_buttons_init`, `add_to_context_menu` |
| `tts/` | Generuje audio MP3 przez Kokoro lub OpenRouter TTS API; przycisk w edytorze + submenu w przeglądarce; "Uruchom wszystkie" działa jako jedna operacja z jednym paskiem postępu i podsumowaniem | `on_editor_buttons_init`, `add_to_context_menu` |
| `filtered_deck/` | Tworzy talię filtrowaną z formularzem ustawień; nazwa talii i deck docelowy konfigurowalne | `setup_menu(parent_menu)` |
| `audio_normalizer/` | Normalizuje głośność plików audio ffmpegiem (EBU R128); po normalizacji synchronizuje zmodyfikowane pliki z Anki media DB przez `write_data()` | `setup_menu(parent_menu)` |
| `nbsp_remover/` | Czyści HTML w polach kart: `&nbsp;` i `<div>`; czysta funkcja `clean_field()` jest współdzielona przez hook dodawania kart, masowe czyszczenie kolekcji (`CollectionOp`) i testy | `setup_menu(parent_menu)` + auto-hook |
| `settings/` | Zbiorczy dialog ustawień dla wszystkich modułów | `open_settings()` |

---

## Jak Anki ładuje wtyczkę

Anki importuje `anki-toolkit/__init__.py` przy starcie. Główny `__init__.py`:
1. Czyta sekcję `modules` z konfiguracji
2. Importuje tylko włączone moduły (`true` w sekcji `modules`)
3. Rejestruje hooki edytora (natychmiast, bez `main_window_did_init`); kolejność to AI/workflow → słownik → TTS, więc główny przycisk workflow jest pierwszy
4. Rejestruje **jeden** centralny hook `_on_browser_context_menu` — tworzy submenu **Anki Toolkit** w prawym kliknięciu i wywołuje `add_to_context_menu(browser, toolkit_menu)` każdego włączonego modułu przeglądarki
5. Po załadowaniu okna głównego tworzy submenu **Narzędzia → Anki Toolkit** i przekazuje je do `setup_menu(parent_menu)` każdego modułu
6. Dodaje na końcu submenuu separator i pozycję **Ustawienia...**

Wyłączony moduł nie jest importowany w ogóle — brak hooków, brak wpisów w menu.

### Wzorce hooków

```python
# Editor — przycisk w toolbarze edytora
gui_hooks.editor_did_init_buttons.append(fn)

# Browser — menu kontekstowe (prawy klik) — SCENTRALIZOWANE w root __init__.py
# Moduły NIE rejestrują własnych hooków; zamiast tego eksportują:
#   add_to_context_menu(browser, menu)
# Root tworzy submenu "Anki Toolkit" i przekazuje je do każdego modułu.
addHook("browser.onContextMenu", _on_browser_context_menu)  # tylko w root

# Menu Narzędzia — po załadowaniu okna głównego
gui_hooks.main_window_did_init.append(fn)
```

### Sygnatura `setup_menu`

```python
def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools  # fallback jeśli wywołane poza root __init__
    action = QAction("...", mw)
    menu.addAction(action)
```

---

## Konfiguracja

### Jak działa przechowywanie konfiguracji

- `config.json` w folderze wtyczki to **szablon domyślny** — nigdy nie jest nadpisywany
- `mw.addonManager.getConfig(name)` zwraca konfigurację użytkownika (nadpisuje defaults)
- `mw.addonManager.writeConfig(name, dict)` zapisuje do profilu Anki (`addons21/{id}/meta.json`)
- Zmiany wprowadzone w **Narzędzia → Anki Toolkit → Ustawienia...** są trwałe między sesjami
- `common/config.py` udostępnia helpery: `get_full_config()`, `save_full_config()`, `get_module_config(module_key, defaults)`, `save_module_config(module_key, cfg)` — używane przez wszystkie moduły

### Dialog ustawień (`settings/`)

Otwarcie: **Narzędzia → Anki Toolkit → Ustawienia...**

Struktura:
```
settings/
├── __init__.py              # SettingsDialog, open_settings()
├── status_tab.py            # StatusTab — dashboard gotowości, pipeline, lista problemów
├── modules_tab.py           # ModulesTab
├── dictionary_tab.py        # DictionaryTab
├── ai_generator_tab.py      # AIGeneratorTab + _PROVIDER_NAMES + model discovery + embedded PromptsTab
├── prompts_tab.py           # PromptsTab (embedded in AI Generator tab, not standalone)
├── tts_tab.py               # TTSTab
├── audio_normalizer_tab.py  # AudioNormalizerTab
├── narzedzia_tab.py         # NarzedziaTab
└── stats_tab.py             # StatsTab — dashboard użycia AI
```

Zakładki (8 zakładek):
- **Start** — dashboard gotowości: wynik pipeline'u, kafelki statusu, podgląd workflow i lista problemów z przyciskami nawigacji do zakładek
- **Moduły** — włącz/wyłącz każdy moduł (wymaga restartu)
- **Słownik** — pola, format IPA, wiktionary_ipa_fallback, diki_ipa_fallback + diki_ipa_fallback_source, przyciski w edytorze, limity sieci (max_retries, page_timeout, mp3_timeout)
- **AI Generator** — podzakładki **Workflow**, **Prompty**, **Dostawcy**; dostawcy AI są rozdzieleni na karty, a limity batch/retry/request timeout są w sekcji **Zaawansowane**
- **TTS** — dostawca (Kokoro / OpenRouter), klucz API OpenRouter (lub współdzielony z AI), model (z przyciskiem Pobierz), głosy (checklista), zadania TTS (Dodaj/Edytuj/Usuń), speed, wydajność (max_workers, max_retries, timeout)
- **Normalizacja** — ścieżka ffmpeg (z przyciskiem "Sprawdź"), opcje loudnorm, liczba wątków
- **Narzędzia** — dwie sekcje jako QGroupBox: Talia filtrowana (deck_name, search_deck), Czyszczenie HTML (show_tooltip, auto_run_startup, skip_field)
- **Statystyki** — dashboard użycia AI: wybór zakresu (dziś / 7 / 30 / 365 dni / wszystko / własny zakres dat od–do przez QDateEdit z kalendarzem), tabela per model (requesty, błędy, tokeny wej./wyj., wygenerowane pola), licznik zaktualizowanych notatek, przyciski Odśwież/Resetuj; dane z `ai_generator/stats.py`

### Sekcja `modules` — włączanie/wyłączanie modułów

```json
"modules": {
    "dictionary":        true,
    "ai_generator":      true,
    "tts":               true,
    "filtered_deck":     true,
    "audio_normalizer":  true,
    "nbsp_remover":      true
}
```

Brakujący klucz = `true` (domyślnie włączony). Zmiana wymaga restartu Anki.

### Sekcje konfiguracyjne modułów

| Sekcja | Moduł | Edycja przez UI |
|---|---|---|
| `dictionary` | `dictionary/` | Zakładka Słownik |
| `tts` | `tts/` | Zakładka TTS |
| `ai_generator` | `ai_generator/` | Zakładka AI Generator (w tym `skip_tags`) + Prompty |
| `audio_normalizer` | `audio_normalizer/` | Zakładka Normalizacja |
| `filtered_deck` | `filtered_deck/` | Zakładka Narzędzia (sekcja Talia filtrowana) |
| `nbsp_remover` | `nbsp_remover/` | Zakładka Narzędzia (sekcja Czyszczenie HTML) |
| `workflow` | `ai_generator/` | Zakładka AI Generator → Workflow |

---

## Kluczowe pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Master entry point — tu dodajesz nowe moduły i wpisy w `modules` |
| `config.json` | Szablon domyślny (nie nadpisywany — patrz wyżej) |
| `common/consts.py` | `ADDON_NAME` — wyliczane z `__name__` (nazwa folderu wtyczki), używane przez wszystkie moduły; config działa nawet gdy folder nie nazywa się `anki-toolkit` |
| `common/html.py` | `clean_html()`, `clean_html_normalized()` — czyszczenie HTML, używane przez dictionary, ai_generator, tts |
| `common/text.py` | `unique()`, `safe_float()`, `safe_str()`, `unique_filename()`, `normalize_float()` |
| `common/http.py` | `fetch_url()`, `fetch_text()`, `extract_http_error()`, `RETRYABLE_STATUS_CODES` |
| `common/config.py` | `get_full_config()`, `save_full_config()`, `get_module_config()`, `save_module_config()` |
| `common/ui.py` | Widgety Qt: `_expanding_line_edit`, `_api_key_widget`, `_scrollable`, `get_field_names`, `get_templates_for_field` |
| `settings/__init__.py` | Dialog ustawień — `open_settings()`, `SettingsDialog` |
| `settings/status_tab.py` | Zakładka Start — dashboard gotowości, statusy Workflow/AI/Promptów/Słownika/TTS, pipeline i problemy konfiguracyjne |
| `settings/modules_tab.py` | Zakładka Moduły — `ModulesTab` |
| `settings/dictionary_tab.py` | Zakładka Słownik — `DictionaryTab` |
| `settings/ai_generator_tab.py` | Zakładka AI Generator — `AIGeneratorTab`, `_PROVIDER_NAMES` |
| `settings/prompts_tab.py` | Zakładka Prompty — `PromptsTab`, `_PROVIDER_NAMES`; comboboxy typu notatki i pola docelowego z danymi z kolekcji, przyciski „Wstaw pole ▾" i „Wstaw warunek ▾" (owija zaznaczenie w `{% if %}`), walidacja na żywo: `{{pola}}` + struktura bloków `{% if %}` |
| `settings/tts_tab.py` | Zakładka TTS — `TTSTab` |
| `settings/audio_normalizer_tab.py` | Zakładka Normalizacja — `AudioNormalizerTab` |
| `settings/narzedzia_tab.py` | Zakładka Narzędzia — `NarzedziaTab` |
| `settings/stats_tab.py` | Zakładka Statystyki — `StatsTab`, dashboard użycia AI (czyta `ai_generator/stats.py`) |
| `ai_generator/stats.py` | Lokalne statystyki użycia AI — `record_request()`, `record_note()`, `get_stats(days=None, start=None, end=None)`, `reset_stats()`; liczniki per dzień kalendarzowy (agregacja zakresów, w tym własny zakres dat inclusive), zapis do `usage_stats.json` (gitignored), thread-safe (`threading.Lock`) |
| `ai_generator/_generator.py` | Zarządzanie stanem generatora — `get_generator()`, `reset_generator()` |
| `ai_generator/providers/__init__.py` | Rejestr providerów AI + fabryka `get_provider()` |
| `ai_generator/providers/base.py` | ABC dla nowych providerów — implementuj `call_api()` |
| `ai_generator/providers/openai_compat.py` | Helpery dla OpenAI-compatible Chat Completions: wykrywa modele OpenAI reasoning, pomija `temperature`, parsuje `message.content` string/list, wykrywa błąd unsupported `reasoning_effort` |
| `ai_generator/providers/opencode_go.py` | OpenCode Go — auto-detect formatu (Chat Completions vs Anthropic Messages), `User-Agent` header, reasoning jako wolny tekst |
| `ai_generator/providers/model_discovery.py` | Pobieranie dostępnych modeli z API każdego providera (w tym `fetch_opencode_go_models`) |
| `ai_generator/field_generator.py` | Główna logika generowania — niezależna od UI; zwraca `dict[str, str]` wypełnionych pól |
| `ai_generator/editor_ui.py` | UI edytora — główny przycisk workflow przed przyciskiem AI, async (`run_in_background` + `saveNow`), ochrona `_GENERATING` |
| `ai_generator/workflow.py` | Workflow "Generuj fiszkę" — sekwencyjne AI → Dict → TTS na pojedynczej notatce, guard `_RUNNING` |
| `ai_generator/browser_ui.py` | UI przeglądarki — batch z QProgressDialog, tooltip podsumowania |
| `dictionary/service.py` | Logika biznesowa słownika — `process_note_group()`; używa `clean_html_normalized()` z common |
| `dictionary/editor_ui.py` | UI edytora — przyciski słownikowe; `saveNow(start)` + `run_in_background` + guard `_FETCHING` |
| `dictionary/browser_ui.py` | UI przeglądarki — submenu batch |
| `dictionary/dictionary_service.py` | Scrapery HTML dla 4 słowników; używa `fetch_url`, `fetch_text` z common |
| `dictionary/ipa_service.py` | Scrapery IPA + parser Wiktionary API; używa `fetch_text` z common |
| `tts/config.py` | Konfiguracja TTS — `_DEFAULTS`, `get_tts_config()`, `validate_config()`, `get_tasks()`, `resolve_openrouter_key()` |
| `tts/api.py` | API TTS — `generate_audio()`, `_generate_kokoro()`, `_generate_openrouter()`, `fetch_openrouter_tts_models()` |
| `tts/processor.py` | Przetwarzanie notatek — `process_task_async()`, `process_tasks_async()`, `process_single_note()` (równoległe przez `ThreadPoolExecutor`, używane przez workflow), `_collect_work_items()`, `_save_batch_results()` |
| `tts/editor_ui.py` | Przycisk TTS w edytorze — `saveNow(start)`, `_GENERATING`, `validate_config()`, task-indexed wyników |
| `audio_normalizer/logic.py` | ffmpeg wrapper + historia przetworzonych plików |
| `nbsp_remover/cleaning.py` | Czysta funkcja `clean_field()` + regexy do czyszczenia HTML |
| `nbsp_remover/collection.py` | Masowe czyszczenie kolekcji przez `CollectionOp` + `clean_field()` |
| `tests/test_pure_logic.py` | Testy bez Anki: template engine, common HTML, `nbsp_remover.cleaning.clean_field()` |

---

## Jak dodać nowy moduł

1. Utwórz katalog `nazwa_modulu/` z `__init__.py` zawierającym `setup_menu(parent_menu=None)`
2. W `__init__.py` (root) dodaj blok:
   ```python
   if _enabled("nazwa_modulu"):
       from . import nazwa_modulu
       _menu_modules.append(nazwa_modulu)
   ```
3. Dodaj `"nazwa_modulu": true` do sekcji `modules` w `config.json`
4. Opcjonalnie dodaj zakładkę w `settings/__init__.py` i sekcję konfiguracyjną w `config.json`

## Jak dodać nowego providera AI

1. Utwórz `ai_generator/providers/moj_provider.py` dziedzicząc po `BaseProvider`
2. Zaimplementuj `call_api(self, prompt: str) -> Optional[str]`
3. Zarejestruj w `ai_generator/providers/__init__.py` w słowniku `PROVIDERS`
4. Dodaj do listy `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` i `settings/prompts_tab.py`
5. Dodaj sekcję `providers.moj_provider` w `config.json`

---

## Zależności między plikami

```
common/                         ← współdzielone narzędzia (html, http, text, config, ui)
    ├── consts.py               ← ADDON_NAME — używane przez WSZYSTKIE moduły
    ├── html.py                 ← clean_html / clean_html_normalized — używane przez dictionary, ai_generator, tts
    ├── text.py                 ← unique / safe_float / unique_filename — używane przez tts, ai_generator
    ├── http.py                 ← RETRYABLE_STATUS_CODES, fetch_url, fetch_text, extract_http_error — używane przez providers, dictionary, tts
    ├── config.py               ← get_full_config, get_module_config — używane przez tts/config.py, nbsp_remover/utils.py
    └── ui.py                   ← widgety Qt, _expanding_line_edit, _api_key_widget, _scrollable — używane przez settings

dictionary/__init__.py          ← re-eksport: on_editor_buttons_init, add_to_context_menu (używa common/ui dla widgetów, common/consts dla ADDON_NAME)
    └── service.py              ← czysta logika biznesowa (ProcessNoteResult, process_note_group); używa common/clean_html_normalized
    └── editor_ui.py            ← przyciski edytora (saveNow + run_in_background + _FETCHING); używa common/ADDON_NAME
    └── browser_ui.py           ← add_to_context_menu (submenu przeglądarki + batch); używa common/ADDON_NAME
    └── dictionary_service.py   (DictionaryService singleton); używa common/http fetch_url, fetch_text
    └── ipa_service.py          (IPAService singleton); używa common/http fetch_text

ai_generator/__init__.py        ← re-eksport: on_editor_buttons_init, add_to_context_menu
    └── _generator.py           ← zarządzanie stanem generatora (config-aware cache, reset); używa common/ADDON_NAME
    └── editor_ui.py            ← workflow button przed AI; saveNow(start) przed zadaniem, _GENERATING guard
    └── browser_ui.py           ← add_to_context_menu (akcja przeglądarki + batch)
    └── field_generator.py      (FieldGenerator — logika bez UI); używa common/clean_html_normalized, safe_float, safe_str
        └── template_engine.py  (render_template, template_structure_problems — czyste funkcje)
        └── stats.py            (record_request / record_note — statystyki użycia, bez zależności od Anki)
        └── providers/          (BaseProvider + 7 implementacji + model_discovery); używa common/http RETRYABLE_STATUS_CODES
    └── workflow.py             (AI → Dict → TTS sekwencyjnie, _RUNNING guard); używa common/ADDON_NAME

tts/__init__.py                 ← add_to_context_menu + exports on_editor_buttons_init
    └── config.py               (_DEFAULTS, get_tts_config, validate_config, get_tasks); używa common/config get_module_config
    └── api.py                  (generate_audio dispatcher, fetch_openrouter_tts_models); używa common/normalize_float, extract_http_error, RETRYABLE_STATUS_CODES
    └── processor.py            (process_task_async, process_tasks_async, process_single_note, _collect_work_items, _save_batch_results); używa common/unique_filename, clean_html
    └── editor_ui.py            (przycisk TTS w edytorze; saveNow + _GENERATING + validate_config); używa common/unique_filename, clean_html, unique

audio_normalizer/__init__.py
    └── gui.py                  (ProgressDialog, Worker(QThread)); używa common/ADDON_NAME
        └── logic.py            (process_collection, normalize_file)
            └── config.py       (wartości domyślne: FFMPEG_CMD, LOUDNORM_OPTS, MAX_WORKERS)

settings/__init__.py            (SettingsDialog, open_settings); używa common/ADDON_NAME, get_full_config, save_full_config
    ├── status_tab.py           (StatusTab — dashboard gotowości + nawigacja do zakładek)
    ├── modules_tab.py          (ModulesTab)
    ├── dictionary_tab.py       (DictionaryTab); używa common/ui widgetów
    ├── ai_generator_tab.py     (AIGeneratorTab); używa common/ui widgetów, common/ADDON_NAME
    ├── prompts_tab.py          (PromptsTab); używa common/ui widgetów + get_note_type_names, get_fields_for_note_type
    ├── tts_tab.py              (TTSTab); używa common/ui widgetów, tts/api fetch_openrouter_tts_models
    ├── audio_normalizer_tab.py (AudioNormalizerTab); używa common/ui widgetów
    ├── narzedzia_tab.py        (NarzedziaTab); używa common/ui widgetów
    └── stats_tab.py            (StatsTab); używa ai_generator/stats get_stats, reset_stats

nbsp_remover/
    ├── cleaning.py             (clean_field + regexy; testowalne bez Anki)
    ├── addcards.py             (hook dodawania kart; używa clean_field)
    ├── collection.py           (masowe czyszczenie przez CollectionOp + clean_field; jeden krok undo)
    └── utils.py                (config + tooltipy)
```

---

## Uwagi o Anki API

- `mw.col.get_note(nid)` — pobierz notatkę po ID
- `mw.col.update_note(note)` — zapisz zmiany (Anki 2.1.45+); używaj zamiast `note.flush()`; pomijaj dla nowych notatek (`note.id == 0`, okno AddCards)
- `mw.col.media.write_data(filename, bytes)` — zapisz plik do media
- `aqt.operations.CollectionOp` — operacja na kolekcji w tle z undo (używane przez nbsp_remover)
- `mw.progress.start/update/finish` — pasek postępu (blokuje UI)
- `mw.addonManager.getConfig(name)` — odczyt konfiguracji (merged z defaults)
- `mw.addonManager.writeConfig(name, dict)` — zapis do profilu Anki (nie do `config.json`)
- Wywołania Qt UI (`showWarning`, `tooltip`) z wątku tła zawsze przez `mw.taskman.run_on_main`
