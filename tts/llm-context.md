# LLM Context — tts

## Co robi

Generuje pliki audio MP3 przez dwa źródła:
- **Kokoro** — lokalny serwer TTS (Docker, darmowy)
- **OpenRouter** — API TTS w chmurze (płatne per znak, nie wymaga lokalnego serwera)

System **zadań TTS** (`tasks` w konfiguracji) zastępuje sztywno zakodowane pola. Każde zadanie definiuje:
- `label` — etykieta w menu
- `source_field` / `target_field` — które pola czytać/zapisywać
- `mode` — `single` (jedno audio na notatkę) lub `split` (osobne audio na segment, dzielone `split_separator`)
- `split_separator` — string dzielący tekst (tylko tryb `split`)

Menu TTS w przeglądarce jest budowane dynamicznie z listy zadań + opcja "Uruchom wszystkie". Backward compat: jeśli klucz `tasks` **nie istnieje** (lub nie jest listą), `get_tasks()` buduje domyślne zadania z legacy pól `ang_source_field`/`ang_target_field`/`przyklad_target_field` — te pola nie są już w `_DEFAULTS` ani w UI, ale są czytane ze starych zapisanych configów; wystarczy raz zapisać ustawienia, by `tasks` stało się jedynym źródłem. Jawnie zapisana **pusta lista** oznacza "brak zadań" — usunięte zadania nie wracają.

Dostępne przez submenu `TTS` w menu kontekstowym przeglądarki. Konfiguracja w głównym dialogu ustawień wtyczki (zakładka TTS) oraz w sekcji `tts` konfiguracji profilu Anki.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Hooki Anki — dynamiczne submenu `TTS` w przeglądarce + eksport `on_editor_buttons_init` |
| `config.py` | Konfiguracja: `_DEFAULTS`, `get_tts_config()`, `validate_config()`, `get_tasks()`, `resolve_openrouter_key()` — używa `common.config.get_module_config()` |
| `api.py` | API TTS: `generate_audio()`, `_generate_kokoro()`, `_generate_openrouter()`, `fetch_openrouter_tts_models()` — `_generate_*` delegują POST z retry do `common.http.post_json()` (zwraca `(bytes\|None, err\|None)`, wyjątek rzucany dopiero na poziomie `generate_audio` gdy `err` niepuste); `fetch_openrouter_tts_models()` używa `urllib.request` bezpośrednio (GET, jednorazowy); loguje DEBUG (parametry/czas żądania) i WARNING (retry) — widoczne w Ustawienia → Logi |
| `processor.py` | Przetwarzanie notatek w przeglądarce: `process_task_async()`, `process_tasks_async()`, `_generate_items()`, `_collect_work_items()`, `_save_batch_results()`; `process_single_note()` (używane przez workflow) — zbiera work itemy ze wszystkich zadań i generuje równolegle przez `ThreadPoolExecutor(max_workers)`; przy błędach generowania rzuca `Exception` z podsumowaniem (workflow pokazuje ją jako tooltip kroku) |
| `editor_ui.py` | Przycisk TTS w toolbarze edytora — `saveNow(start)`, `_GENERATING`, `validate_config()`, własny batch work items w tle (`run_in_background`), task-indexed klucze wyników |

## Przepływ danych

```
Menu `TTS` → zadanie z listy
  → _make_runner(browser, task) → browser.selected_notes()
  → process_task_async(browser, nids, task)
      → config = get_tts_config()
      → validate_config(config)
      → _collect_work_items(nids, task, voices)
      → QProgressDialog + run_in_background
      → _generate_items(items, config, label, cancel_flag, progress, state)
          → ThreadPoolExecutor(max_workers=config.get("max_workers", 12))
              → generate_audio(text, config, voice)  # dispatcher → Kokoro / OpenRouter
      → _save_batch_results(items, results, task)
      → zapis [sound:fname.mp3] do target_field
      → mw.col.update_note(note)

Menu → "Uruchom wszystkie"
  → _make_run_all(browser, tasks) → process_tasks_async(browser, nids, tasks)
      → config = get_tts_config(); validate_config(config)
      → precollect jobs: dla każdego taska zbierz _collect_work_items(...)
      → jeden QProgressDialog z maksimum = suma work items
      → dla każdego joba sekwencyjnie: _generate_items(...)
      → po zakończeniu: _save_batch_results(...) dla każdego taska
      → jeden browser.mw.reset() i jeden tooltip z podsumowaniem

Przycisk edytora
  → _on_tts_editor(editor)
      → jeśli editor_id w _GENERATING: tooltip i return
      → editor.saveNow(start) synchronizuje webview → note przed odczytem pól
      → _start_tts_editor(editor, editor_id)
          → validate_config(config), get_tasks(config), unique(voices)
          → zbuduj work_items ze wszystkich zadań TTS
          → run_in_background(bg_task)
              → ThreadPoolExecutor → generate_audio(...) → mw.col.media.write_data(...)
              → results[(task_i, target_field, seg_i)] = filename
          → on_done: editor.saveNow(apply), zastosuj wyniki do notatki złapanej na starcie
              → jeśli editor.note is note: editor.loadNote()
              → w przeciwnym razie (użytkownik przełączył kartę): mw.col.update_note(note)
          → jeden tooltip z podsumowaniem
```

### get_tasks() — backward compat

```
get_tasks(config)
  → jeśli config["tasks"] jest listą (także pustą) → zwróć przefiltrowaną listę
  → else (klucz nie istnieje / zły typ): zbuduj z legacy pól
       (ang_source_field + ang_target_field → mode=single,
        przyklad_target_field → mode=split)
       — te pola nie są w _DEFAULTS od wersji X; fallback czyta je
         tylko ze starych zapisanych configów użytkownika
```

### Dispatcher providera

`generate_audio()` sprawdza `config["tts_provider"]`:
- `"kokoro"` (domyślnie) → `_generate_kokoro()` — POST do `config["api_url"]`
- `"openrouter"` → `_generate_openrouter()` — POST do `https://openrouter.ai/api/v1/audio/speech` z `Authorization: Bearer`

### Proces przykładów (process_przyklad)

```
Pole: "He ran fast.<br><br>She walked slowly.<br><br>They jumped high."
  → split po /<br\s*\/?>\s*){2,}/
  → ["He ran fast.", "She walked slowly.", "They jumped high."]
  → każde zdanie → osobny plik audio
  → po złożeniu: "He ran fast.[sound:tts_abc.mp3]<br><br>She walked...[sound:tts_def.mp3]..."
```

Głosy dla segmentów w jednej notatce są przetasowane losowo (`random.shuffle`) — każdy segment dostaje inny głos z puli. Separator split jest konfigurowalny per zadanie (`split_separator`, domyślnie `<br><br>`).

## OpenRouter — pobieranie modeli i głosów

`fetch_openrouter_tts_models(force=False)` (w `api.py`) woła `GET https://openrouter.ai/api/v1/models?output_modalities=speech` (nie wymaga klucza API). Zwraca listę `[{id, name, voices, pricing}]`.

- Wynik jest cachowany globalnie (`_OR_MODELS_CACHE`); `force=True` wymusza ponowne pobranie
- `pricing` jest parsowane z `pricing.prompt` (dolary/znak), przeliczane i formatowane jako `$X.XXX/1k zn`
- `voices` to `supported_voices` z API — pełna lista głosów dla danego modelu

W UI (settings/tts_tab.py) przycisk **Pobierz** wywołuje tę funkcję (import z `tts.api`) i wypełnia QComboBox. Po wybraniu modelu, QListWidget z checkboxami pokazuje dostępne głosy, synchronizowane dwukierunkowo z polem tekstowym "Głosy".

## Konfiguracja (sekcja `tts` w config.json)

```json
{
  "tts_provider": "kokoro",
  "api_url": "http://localhost:8880/v1/audio/speech",
  "model": "kokoro",
  "openrouter_api_key": "",
  "use_ai_openrouter_key": false,
  "openrouter_model": "openai/gpt-4o-mini-tts-2025-12-15",
  "voices": ["af_bella", "af_heart", "bm_lewis"],
  "speed": 0.9,
  "button_label": "TTS",
  "max_workers": 12,
  "max_retries": 3,
  "timeout": 60
}
```

- `tts_provider` — `"kokoro"` lub `"openrouter"`; domyślnie `"kokoro"` dla kompatybilności wstecznej
- `api_url` / `model` — tylko dla Kokoro
- `button_label` — etykieta przycisku TTS w edytorze
- `openrouter_api_key` — klucz API z https://openrouter.ai/keys (tylko dla OpenRouter)
- `use_ai_openrouter_key` — gdy `true`, TTS używa klucza OpenRouter z sekcji `ai_generator.providers.openrouter`
- `openrouter_model` — ID modelu TTS
- `voices` — lista głosów do losowania
- `tasks` — lista zadań TTS, każde z `label`, `source_field`, `target_field`, `mode` (`single`/`split`), opcjonalnie `split_separator`. Jeśli klucz nie istnieje → backward compat czyta legacy pola `ang_source_field`/`ang_target_field`/`przyklad_target_field` ze starego configu (pola nie są już w `_DEFAULTS` ani w UI); pusta lista = brak zadań
- `max_workers` — liczba wątków w `ThreadPoolExecutor`
- `max_retries` i `timeout` — retry logic w `generate_audio()` (HTTP 429/5xx; timeouty zgłaszane jako błąd)
- Wszystkie domyślne wartości zdefiniowane w `_DEFAULTS` (config.py) i mergowane przez `get_tts_config()` używającego `get_module_config()` z `common.config`

### Walidacja konfiguracji

`validate_config()` (config.py) sprawdza:
- Dla `"openrouter"`: czy `openrouter_api_key` nie jest pusty (lub `use_ai_openrouter_key` wskazuje na klucz z AI)
- Dla `"kokoro"`: czy `api_url` nie jest pusty
- Zawsze: czy `voices` nie jest pusta

Ostrzeżenia (`showWarning`) są wysyłane przez `mw.taskman.run_on_main` — `validate_config()` może być wywołane z wątku tła (np. krok TTS w workflow), a wywołania Qt UI muszą iść z głównego wątku.

## Kokoro API

```
POST {api_url}
Content-Type: application/json
{
  "model": "kokoro",
  "input": "tekst do syntezy",
  "voice": "af_bella",
  "speed": 0.9,
  "response_format": "mp3"
}
→ raw MP3 bytes
```

## OpenRouter TTS API

```
POST https://openrouter.ai/api/v1/audio/speech
Authorization: Bearer {api_key}
Content-Type: application/json
{
  "model": "openai/gpt-4o-mini-tts-2025-12-15",
  "input": "tekst do syntezy",
  "voice": "alloy",
  "speed": 0.9,
  "response_format": "mp3"
}
→ raw MP3 bytes (success) / JSON (error)
```

`speed` jest wysyłane tylko gdy ustawione w konfiguracji (niektóre providery go nie obsługują).

## Nazwy plików audio

Generowane losowo przez `unique_filename()` z `common.text`: `tts_` + 12 znaków `[a-z0-9]` + `.mp3`. Unikalność przez losowość, nie przez hash.

## Zależności

- Stdlib: `urllib.request` (GET w `fetch_openrouter_tts_models`), `json`, `concurrent.futures`, `random`, `re`, `time`, `logging`
- Anki API: `mw.col.get_note`, `mw.col.update_note`, `mw.col.media.write_data`, `mw.taskman`
- Własne: `common.config` (get_module_config), `common.text` (normalize_float, unique_filename, unique), `common.html` (clean_html), `common.http` (post_json — POST z retry; używany przez `_generate_kokoro`/`_generate_openrouter`)
- Kokoro: wymaga lokalnego serwera Kokoro TTS (Docker)
- OpenRouter: tylko klucz API, żadnych lokalnych zależności
- Brak pip packages
