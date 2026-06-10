# Anki Toolkit

Scalona wtyczka łącząca sześć narzędzi do zarządzania kartami Anki.

## Struktura

```
anki-toolkit/
├── __init__.py                      # entry point — rejestruje wszystkie hooki
├── config.json                      # szablon domyślny (nie nadpisywany)
├── config.md                        # dokumentacja konfiguracji
├── manifest.json                    # metadane Anki
│
├── common/                          # współdzielone narzędzia
│   ├── __init__.py
│   ├── consts.py                    # ADDON_NAME (wyliczane z nazwy folderu wtyczki)
│   ├── html.py                      # clean_html(), clean_html_normalized()
│   ├── text.py                      # unique(), safe_float(), safe_str(), unique_filename(), normalize_float()
│   ├── http.py                      # fetch_url(), fetch_text(), extract_http_error(), RETRYABLE_STATUS_CODES
│   ├── config.py                    # get_full_config(), save_full_config(), get_module_config(), save_module_config()
│   └── ui.py                        # widgety Qt: _expanding_line_edit, _api_key_widget, _scrollable, get_field_names, get_templates_for_field
│
├── settings/                        # Dialog ustawień dla wszystkich modułów
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
├── dictionary/                      # Moduł 1: pobieranie audio + IPA
│   ├── __init__.py                  # re-eksport hooków
│   ├── service.py                   # logika biznesowa (ProcessNoteResult, process_note_group)
│   ├── editor_ui.py                 # przyciski edytora
│   ├── browser_ui.py                # submenu przeglądarki + batch
│   ├── dictionary_service.py        # fetching MP3 z Oxford/Cambridge/Diki/Longman
│   └── ipa_service.py               # fetching IPA z Oxford/Cambridge/Wiktionary
│
├── ai_generator/                    # Moduł 2: generowanie pól przez AI + workflow
│   ├── __init__.py                  # re-eksport hooków
│   ├── _generator.py                # zarządzanie stanem generatora (config-aware cache)
│   ├── editor_ui.py                 # przycisk AI + workflow button
│   ├── browser_ui.py                # menu przeglądarki + batch
│   ├── field_generator.py           # logika generowania, niezależna od dostawcy
│   ├── template_engine.py           # silnik szablonów {{pole}} / {% if %}
│   ├── stats.py                     # lokalne statystyki użycia (tokeny, requesty)
│   ├── workflow.py                  # workflow "Generuj fiszkę" (AI → Dict → TTS)
│   └── providers/
│       ├── __init__.py              # rejestr dostawców + fabryka get_provider()
│       ├── base.py                  # BaseProvider (ABC)
│       ├── openai_compat.py         # helpery OpenAI-compatible
│       ├── openai.py
│       ├── cometapi.py
│       ├── openrouter.py
│       ├── anthropic.py
│       ├── google.py
│       ├── mistral.py
│       ├── opencode_go.py
│       └── model_discovery.py
│
├── tts/                             # Moduł 3: generowanie audio przez Kokoro TTS lub OpenRouter
│   ├── __init__.py                  # submenu TTS w menu kontekstowym przeglądarki + przycisk edytora
│   ├── config.py                    # _DEFAULTS, get_tts_config(), validate_config(), get_tasks()
│   ├── api.py                       # generate_audio(), _generate_kokoro(), _generate_openrouter(), fetch_openrouter_tts_models()
│   ├── processor.py                 # process_task_async(), process_tasks_async(), process_single_note()
│   └── editor_ui.py                 # przycisk TTS w toolbarze edytora (async)
│
├── filtered_deck/                   # Moduł 4: tworzenie talii filtrowanej
│   └── __init__.py                  # dialog ustawień + tworzenie talii
│
├── audio_normalizer/                # Moduł 5: normalizacja audio przez ffmpeg
│   ├── __init__.py
│   ├── config.py                    # konfiguracja ffmpeg, parametry EBU R128
│   ├── gui.py                       # dialog postępu Qt + wątek roboczy
│   └── logic.py                     # skanowanie plików, historia, przetwarzanie równoległe
│
├── nbsp_remover/                    # Moduł 6: czyszczenie &nbsp; i tagów <div>
│   ├── __init__.py
│   ├── cleaning.py                  # czysta logika czyszczenia pól + liczniki
│   ├── addcards.py                  # hook na dodawanie kart — czyszczenie w locie
│   ├── collection.py                # akcja czyszczenia HTML w całej kolekcji
│   └── utils.py
│
└── tests/                           # testy czystej logiki bez uruchamiania Anki
```

> Każdy moduł można niezależnie włączyć lub wyłączyć — patrz sekcja **Ustawienia**.

---

## Instalacja

1. Skopiuj folder `anki-toolkit/` do katalogu addons Anki:
   - macOS: `~/Library/Application Support/Anki2/addons21/`
   - Windows: `%APPDATA%\Anki2\addons21\`
2. Uruchom Anki.
3. Otwórz **Narzędzia → Anki Toolkit → Ustawienia...** i uzupełnij klucze API.
4. Upewnij się, że `ffmpeg` jest zainstalowany i dostępny w PATH (wymagane przez `audio_normalizer`).

---

## Ustawienia

Wszystkie moduły można skonfigurować przez jeden centralny dialog:

**Narzędzia → Anki Toolkit → Ustawienia...**

### Zakładki

| Zakładka | Zawartość |
|---|---|
| **Start** | Dashboard gotowości: wynik pipeline'u, kafelki statusu, podgląd workflow i lista problemów z przyciskami nawigacji |
| **Moduły** | Włącz/wyłącz każdy moduł (zmiana wymaga restartu Anki) |
| **Słownik** | Pola źródłowe/docelowe, format IPA, przyciski słowników, limity sieci |
| **AI Generator** | Workflow, prompty oraz dostawcy AI w osobnych podzakładkach |
| **TTS** | Dostawca (Kokoro/OpenRouter), klucz API, model, wybór głosów, zadania TTS, szybkość, liczba wątków |
| **Normalizacja** | Ścieżka ffmpeg (z przyciskiem "Sprawdź"), opcje loudnorm, liczba wątków |
| **Narzędzia** | Talia filtrowana · czyszczenie HTML (`&nbsp;`, `<div>`) |
| **Statystyki** | Dashboard użycia AI: requesty, błędy, tokeny wej./wyj. i wygenerowane pola per model, licznik zaktualizowanych notatek; wybór zakresu (dziś / 7 / 30 / 365 dni / wszystko / własny zakres dat od–do) i przycisk resetu |

> **Gdzie są przechowywane ustawienia?** `config.json` w folderze wtyczki to szablon domyślny — nie jest nadpisywany. Twoje zmiany są zapisywane przez Anki w katalogu profilu (`addons21/.../meta.json`). Po ponownym otwarciu dialogu zobaczysz zapisane wartości.

---

## Włączanie i wyłączanie modułów

Przez dialog **Ustawienia → zakładka Moduły**, lub ręcznie w `config.json`:

```json
"modules": {
    "dictionary":        true,
    "ai_generator":      true,
    "tts":               false,
    "filtered_deck":     true,
    "audio_normalizer":  false,
    "nbsp_remover":      true
}
```

Zmiana wymaga restartu Anki. Brakujący klucz jest traktowany jako `true`.

---

## Opis modułów

### Słownik (`dictionary`)

Przyciski pojawiają się w toolbarze edytora kart — kliknięcie najpierw zapisuje bieżące pola, a pobieranie działa w tle (Anki nie zamarza). W przeglądarce dostępne jest też submenu **Pobierz wymowę** pod prawym przyciskiem myszy w sekcji **Anki Toolkit**, które pozwala uruchomić batch dla wszystkich włączonych słowników albo tylko dla wybranego, np. Diki lub Oxford. Moduł pobiera audio i IPA z wybranych słowników. Batch działa w tle — Anki nie zamraża się, widoczny pasek postępu z przyciskiem Anuluj.

Konfiguracja w **Ustawienia → Słownik**:

| Pole | Opis |
|---|---|
| `source_field` | Pole z angielskim słowem (np. `"ang"`) |
| `target_field` | Pole docelowe dla audio (np. `"audio"`) |
| `ipa_field` | Pole docelowe dla IPA (puste = wyłączone) |
| `ipa_format` | `"compact"` / `"both"` / `"uk_only"` / `"us_only"` |
| `wiktionary_ipa_fallback` | `true` — gdy Oxford/Cambridge nie znajdzie IPA, odpyta Wiktionary API (domyślnie `true`) |
| `diki_ipa_fallback` | `true` — gdy fetchujesz z Diki (brak natywnego IPA), pobierz IPA z osobnego źródła (domyślnie `false`) |
| `diki_ipa_fallback_source` | Źródło IPA dla Diki: `"wiktionary"` / `"oxford"` / `"cambridge"` (domyślnie `"wiktionary"`) |
| `max_retries` | Liczba prób przy błędach sieci (domyślnie 3) |
| `page_timeout` | Timeout pobierania strony słownika w sekundach (domyślnie 10) |
| `mp3_timeout` | Timeout pobierania pliku MP3 w sekundach (domyślnie 10) |
| Przyciski | Zaznacz które słowniki mają być widoczne w edytorze |

Dostępne słowniki: `oxford_uk`, `oxford_us`, `cambridge_uk`, `cambridge_us`, `diki_uk`, `diki_us`, `longman_uk`, `longman_us`.

Wpisy `buttons` sterują jednocześnie:
- przyciskami w edytorze
- pozycjami w submenu batchowym w przeglądarce

---

### Workflow "Generuj fiszkę"

Główna akcja w toolbarze edytora uruchamiająca AI → Słownik → TTS w jednym kliknięciu. Konfigurowalny przez UI: **Ustawienia → AI Generator → Workflow**.

- Dodaj kroki przyciskami **+ AI**, **+ Słownik**, **+ TTS**
- Zmieniaj kolejność przyciskami ▲▼
- Etykieta przycisku konfigurowalna (domyślnie "Generuj fiszkę")

Domyślna konfiguracja: AI → Oxford → TTS.

---

### Generator AI (`ai_generator`)

Pomocniczy przycisk **AI** w toolbarze edytora generuje tylko pola AI dla pojedynczej karty. W przeglądarce batch jest dostępny przez **prawy klik → Anki Toolkit → Generuj pola**.

- **Edytor**: działa asynchronicznie — Anki nie zamarza podczas oczekiwania na API. Możesz swobodnie edytować inne pola w tym czasie. Pola docelowe AI są zawsze nadpisywane wynikiem; pola których AI nie dotyka są chronione przez `saveNow` przed skasowaniem Twoich edycji. Jeśli w trakcie generowania przełączysz się na inną kartę, wynik trafia do właściwej notatki (zapis do kolekcji), nie do aktualnie wyświetlanej.
- **Batch**: działa w tle z paskiem postępu i przyciskiem Anuluj. Po zakończeniu jeden tooltip z podsumowaniem.
- Pola z treścią są zawsze pomijane — generator uzupełnia tylko puste pola.
- Zmiana kluczy API i promptów **nie wymaga restartu Anki**.
- **Statystyki użycia** (requesty, tokeny, pola per model) są zliczane lokalnie i widoczne w **Ustawienia → Statystyki**.

Konfiguracja w **Ustawienia → AI Generator**:

| Pole | Opis |
|---|---|
| `button_label` | Etykieta przycisku w edytorze |
| `skip_tags` | Lista tagów wykluczających — notatki z dowolnym z tych tagów są pomijane w całości (brak wywołań API, brak aktualizacji) |
| `batch_limit` | Liczba kart w jednej paczce — po paczce następuje przerwa `batch_sleep` |
| `batch_sleep` | Pauza (sekundy) między paczkami kart — zapobiega limitom API |
| `max_retries` | Liczba prób przy błędach API 429/5xx (domyślnie 3) |
| `request_timeout` | Timeout żądania do API w sekundach (domyślnie 30) |
| Dostawcy | Klucz API, model (przycisk **Pobierz** pobiera listę dostępnych modeli z API), temperatura osobno dla każdego dostawcy; dla OpenAI, CometAPI i OpenRouter także poziom reasoning |

`reasoning_effort` jest konfigurowalne dla `openai`, `cometapi` i `openrouter` i wysyłane tylko dla modeli obsługujących reasoning. Jeśli model zwróci błąd HTTP 400 z powodu nieobsługiwanego `reasoning_effort`, żądanie jest automatycznie ponawiane bez tego parametru. Modele OpenAI reasoning nie dostają `temperature`. `max_tokens` jest konfigurowalne dla Anthropic (wymagany przez ich API, domyślnie `2048`). Pola notatki zawierające HTML są automatycznie oczyszczane przed wstawieniem do promptu.

#### Dostępni dostawcy

| Dostawca | Endpoint |
|---|---|
| `openai` | `https://api.openai.com/v1/chat/completions` |
| `cometapi` | `https://api.cometapi.com/v1/chat/completions` |
| `openrouter` | `https://openrouter.ai/api/v1/chat/completions` |
| `anthropic` | `https://api.anthropic.com/v1/messages` |
| `google` | `https://generativelanguage.googleapis.com/v1beta/models` |
| `mistral` | `https://api.mistral.ai/v1/chat/completions` |
| `opencode_go` | `https://opencode.ai/zen/go/v1/chat/completions` (większość modeli) / `.../messages` (MiniMax, Qwen3.x) |

#### Szablony promptów

- `{{nazwa_pola}}` — wstawia wartość pola karty (oczyszczoną z HTML)
- `{% if pole %} ... {% else %} ... {% endif %}` — warunek

Każde pole notatki może używać innego dostawcy. Pola generowane są w kolejności kluczy w `note_types` — wynik wcześniejszego pola można użyć w prompcie następnego.

#### Dodanie nowego dostawcy AI

1. Utwórz `ai_generator/providers/moj_provider.py` dziedzicząc po `BaseProvider`
2. Zaimplementuj `call_api(self, prompt) -> Optional[str]`
3. Zarejestruj w `ai_generator/providers/__init__.py` w słowniku `PROVIDERS`
4. Dodaj nazwę do listy `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` i `settings/prompts_tab.py`
5. Dodaj sekcję `providers.moj_provider` w `config.json`

#### OpenCode Go — szczegóły

Dostawca `opencode_go` obsługuje niskokosztową subskrypcję [OpenCode Go](https://opencode.ai/zen). Automatycznie wybiera format API na podstawie nazwy modelu:
- **Chat Completions** — GLM-5/5.1, Kimi K2.5/K2.6, DeepSeek V4 Pro/Flash, MiMo-V2.5/V2.5-Pro
- **Anthropic Messages** — MiniMax M2.5/M2.7, Qwen3.5/3.6 Plus

Pole `reasoning_effort` to wolny tekst (nie dropdown jak przy OpenAI) — wartości różnią się per model, np. `max` dla DeepSeek V4 Pro. Puste = nie wysyłane. Klucz API uzyskasz na [opencode.ai/auth](https://opencode.ai/auth).

---

### TTS

Dostępny przez **prawy klik → Anki Toolkit → TTS** w przeglądarce (batch z QProgressDialog i Anuluj) oraz **przycisk TTS w edytorze** (pojedyncza karta). Przycisk edytora najpierw zapisuje bieżące pola, więc synteza używa aktualnego tekstu. Obsługuje dwa źródła:
- **Kokoro** — lokalny serwer TTS przez Dockera (darmowy, bez limitu)
- **OpenRouter** — API TTS przez chmurę (płatne per znak, nie wymaga lokalnego serwera)

Konfiguracja w **Ustawienia → TTS**:

| Pole | Opis |
|---|---|
| `tts_provider` | Dostawca: `kokoro` (lokalny) lub `openrouter` (API) |
| `button_label` | Etykieta przycisku w edytorze (domyślnie `"TTS"`) |
| `api_url` | Adres serwera Kokoro (tylko dla Kokoro) |
| `model` | Nazwa modelu Kokoro (tylko dla Kokoro) |
| `openrouter_api_key` | Klucz API OpenRouter (lub zaznacz "Użyj klucza z AI Generatora") |
| `use_ai_openrouter_key` | `false` — użyj klucza OpenRouter z AI Generatora zamiast wpisywać osobno |
| `openrouter_model` | Model TTS OpenRouter — kliknij **Pobierz** aby zobaczyć dostępne modele z cenami |
| `voices` | Lista głosów do losowania. Dla OpenRouter: po wybraniu modelu pojawia się lista z checkboxami |
| `tasks` | Lista zadań TTS (konfigurowalna przez UI: Dodaj/Edytuj/Usuń) |
| `speed` | Tempo mowy (0.1–3.0, domyślnie 0.9) |
| `max_workers` | Liczba równoległych wątków generowania audio (domyślnie 12) |
| `max_retries` | Liczba prób przy błędach API 429/5xx (domyślnie 3) |
| `timeout` | Timeout żądania TTS w sekundach (domyślnie 60) |

Dla OpenRouter: po kliknięciu **Pobierz** wtyczka pobiera listę dostępnych modeli TTS z OpenRouter (wraz z cenami w `$/1k zn`). Po wybraniu modelu pojawia się lista głosów z checkboxami — zaznacz które chcesz używać.

**Zadania TTS**: zamiast sztywnych pól `ang`/`przyklad`, moduł używa konfigurowalnej listy zadań. Każde zadanie definiuje etykietę menu, pola źródłowe/docelowe oraz tryb (`single` — jedno audio, `split` — dzielone separatorem). Menu TTS jest budowane dynamicznie. Opcja **Uruchom wszystkie** wykonuje zadania sekwencyjnie jako jedną operację z jednym paskiem postępu i jednym podsumowaniem. Backward compat: stare pola `ang_source_field`/`przyklad_target_field` nadal działają gdy `tasks` jest puste.

---

### Talia filtrowana (`filtered_deck`)

Dostępny przez **Narzędzia → Anki Toolkit → Utwórz talię filtrowaną: ...** — nazwa talii w menu odpowiada skonfigurowanej nazwie wyszukiwanej talii.

Konfiguracja w **Ustawienia → Narzędzia** (sekcja Talia filtrowana):

| Pole | Opis |
|---|---|
| `deck_name` | Nazwa tworzonej talii filtrowanej (domyślnie `"Angielski - Powtórka z wyprzedzeniem"`) |
| `search_deck` | Nazwa talii do wyszukiwania w `deck:` (domyślnie `"angielski"`) |

Dialog przy każdym użyciu pozwala wybrać dodatkowe opcje:

| Opcja | Opis |
|---|---|
| Dni do przodu | Zakres `prop:due<=X` (domyślnie 9999 = wszystkie) |
| Limit kart | Maksymalna liczba kart w talii (domyślnie 99999) |
| Kolejność | Losowo, wg interwału, wg terminu itp. |

---

### Normalizacja audio (`audio_normalizer`)

Dostępny przez **Narzędzia → Anki Toolkit → Normalizuj Audio (ffmpeg)**.

Normalizuje wszystkie pliki audio w katalogu media Anki do głośności EBU R128 (`I=-14 LUFS, TP=-1.5, LRA=8`).
Przetworzone pliki są zapamiętywane w `audio_normalizer/processed_history.json` — ponowne uruchomienie pomija już znormalizowane pliki.
Błędy są logowane przez standardowy logger Pythona i są widoczne w konsoli/debug logach Anki.

**Synchronizacja z Anki Media DB:** Po normalizacji wtyczka automatycznie re-readuje zmodyfikowane pliki przez `mw.col.media.write_data()`, co aktualizuje hashe w bazie mediów Anki.

Konfiguracja w **Ustawienia → Normalizacja**:

| Pole | Opis |
|---|---|
| `ffmpeg_path` | Ścieżka do ffmpeg — puste = wykryj automatycznie; przycisk **Sprawdź** testuje ścieżkę i pokazuje wersję |
| `loudnorm_opts` | Parametry filtra loudnorm (standard EBU R128) |
| `max_workers` | Liczba równoległych wątków ffmpeg (domyślnie 4) |

---

### Czyszczenie HTML (`nbsp_remover`)

Działa automatycznie przy dodawaniu kart. Ręczne czyszczenie całej kolekcji przez **Narzędzia → Anki Toolkit → Wyczyść HTML w kolekcji...**

| Akcja | Opis |
|---|---|
| Dodawanie karty | Usuwa `&nbsp;` i czyści `<div>` z każdego pola w locie |
| Wyczyść HTML w kolekcji | Jednorazowe czyszczenie całej kolekcji — działa w tle, z możliwością cofnięcia (jeden krok undo) |

Dla pola konfigurowalnego (domyślnie `ang`): tagi `<div>` są usuwane całkowicie.
Dla pozostałych pól: `<div>tekst</div>` zastępowane przez `tekst<br>`.

Konfiguracja w **Ustawienia → Narzędzia** (sekcja Czyszczenie HTML):

| Opcja | Domyślnie | Opis |
|---|---|---|
| Pokazuj tooltip | `true` | Wyświetlaj powiadomienie po wyczyszczeniu |
| Czyść przy starcie | `false` | Automatycznie uruchamiaj czyszczenie kolekcji przy starcie Anki |
| Pole pomijane | `"ang"` | Pole z którego tagi `<div>` są usuwane całkowicie (zamiast zamiany na `<br>`) |

---

## Bezpieczeństwo

Klucze API są przechowywane w profilu Anki w czystym tekście. Nie udostępniaj katalogu profilu publicznie.
