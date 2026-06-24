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
| `api.py` | API TTS: `generate_audio()` (dispatcher + statystyki), `_generate_kokoro()`, `_generate_openrouter()` — `_generate_*` delegują POST z retry do `common.http.post_json()` (zwraca `(bytes\|None, err\|None)`); **wyjątek `raise Exception(...)` rzucany wewnątrz `_generate_*`** gdy `err` niepuste (`api.py:64,106`), a nie na poziomie `generate_audio()` (ten jedynie łapie i re-raise dla statystyk). `fetch_openrouter_tts_models()` używa `urllib.request` bezpośrednio (GET, jednorazowy); loguje DEBUG (parametry/czas żądania) i WARNING (retry) — widoczne w Ustawienia → Logi |
| `processor.py` | Wspólne building blocks + batch: `build_note_work_items()`, `generate_for_items()`, `apply_results_to_note()`; `process_task_async()` / `process_tasks_async(browser, nids, tasks, on_complete=None)` (batch z `QProgressDialog` i `CollectionOp`; `on_complete` odpala się na **każdym** wyjściu — sukces, miękki skip „brak pól", błąd — żeby łańcuch zewnętrzny szedł dalej; spina full pipeline z `ai_generator.browser_ui`); `process_single_note(note, config=None, tasks=None, overwrite=False) -> (changed, error)` (używane przez workflow i PPM w edytorze) — `tasks` filtruje do podzbioru zadań, `overwrite=True` stripuje `[sound:...]` z target fields przed generowaniem; generuje równolegle przez `ThreadPoolExecutor(max_workers)`; **przy błędach generowania zwraca `(False, error_msg)` — NIE rzuca `Exception`** (workflow/edytor zamieniają to w tooltip) |
| `editor_ui.py` | Przycisk TTS w toolbarze edytora — `saveNow(start)`, `_GENERATING`, `validate_config()`, własny batch work items w tle (`run_in_background`); rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na `target_field` zadania TTS: „Generuj/Regeneruj TTS: [label]" (Regeneruj = `overwrite=True`); `_on_tts_field_editor` woła `process_single_note(tasks=[task], overwrite=...)` |

## Przepływ danych

```
Menu `TTS` → zadanie z listy
  → _make_runner(browser, task) → browser.selected_notes()
  → process_task_async(browser, nids, task)  →  _process_batch_async(browser, nids, [task], label)
Menu → "Uruchom wszystkie"
  → _make_run_all(browser, tasks) → process_tasks_async(browser, nids, tasks)  →  _process_batch_async(browser, nids, tasks, label)

_process_batch_async(browser, nids, tasks, label, on_complete=None):
  → _continue() = on_complete() jeśli podany — wołane na KAŻDYM wyjściu
    (validate/voices fail, brak all_items, błąd fut, po commicie CollectionOp)
    tak by łańcuchujący caller (np. ai_generator full pipeline) zawsze szedł dalej
  → config = get_tts_config(); validate_config(config)
  → voices = unique(config.get("voices", []))
  → precollect (główny wątek): dla każdego nid:
      note = mw.col.get_note(nid)
      build_note_work_items(note, tasks, voices)  →  (work_items, split_contexts)
      all_items.extend(items)   # wszystkie zadania razem, jeden pool na notatkę
  → QProgressDialog(maximum = len(all_items))
  → run_in_background(bg_task)
      → generate_for_items(all_items, config,
            key_fn=lambda item: (item["nid"], item["task_i"], item["seg_i"]),
            cancel_flag, on_progress)
          → ThreadPoolExecutor(max_workers=config.get("max_workers", 12))
              → generate_audio(text, config, voice)  # dispatcher → Kokoro / OpenRouter
          → mw.col.media.write_data(unique_filename(), bytes)
          → results[(nid, task_i, seg_i)] = filename
  → on_done (główny wątek):
      → progress.close()
      → grouped per nid → fresh note = mw.col.get_note(nid)
      → apply_results_to_note(note, items, split_contexts, per_note)
      → CollectionOp(parent=browser, op=lambda col: col.update_notes(changed_notes))
            .success(tooltip z podsumowaniem).run_in_background()
      → brak mw.reset() — CollectionOp sam odświeża kolekcję (jeden krok undo)

Przycisk edytora (toolbar)
  → _on_tts_editor(editor)
      → jeśli editor_id w _GENERATING: tooltip i return
      → editor.saveNow(start) synchronizuje webview → note przed odczytem pól
      → _start_tts_editor(editor, editor_id)
          → validate_config(config), get_tasks(config), unique(voices)
          → build_note_work_items(note, tasks, voices)
          → run_in_background(bg_task):
              → generate_for_items(work_items, config)   # default key = (task_i, seg_i)
              → mw.col.media.write_data(unique_filename(), bytes)
              → results[(task_i, seg_i)] = filename
          → on_done: editor.saveNow(apply), zastosuj wyniki do notatki złapanej na starcie
              → apply_results_to_note(note, work_items, split_contexts, results)
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
       — te pola nie są w _DEFAULTS; fallback czyta je
         tylko ze starych zapisanych configów użytkownika
```

### Dispatcher providera

`generate_audio()` (`api.py:14`) sprawdza `config["tts_provider"]`:
- `"kokoro"` (domyślnie) → `_generate_kokoro()` — POST do `config["api_url"]`
- `"openrouter"` → `_generate_openrouter()` — POST do `https://openrouter.ai/api/v1/audio/speech` z `Authorization: Bearer`

Retry (HTTP 429/5xx, timeouty) dzieje się w `common.http.post_json()` — `_generate_*` tylko interpretują wynik `(bytes|None, err|None)` i rzucają `Exception` gdy `err` niepuste.

### Proces przykładów (tryb split)

```
Pole: "He ran fast.<br><br>She walked slowly.<br><br>They jumped high."
  → split_separator_regex("<br><br>")  (common/text.py:38)
      → kompiluje (?:<br><br>){1,}  (\s* między tokenami, dowolna ilość whitespace)
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

W UI (settings/tts_tab.py) przycisk **Pobierz** wywołuje tę funkcję (import z `tts.api`) i wypełnia QComboBox. Po wybraniu modelu, QTableWidget z checkboxami i przyciskami ▶ podglądu pokazuje dostępne głosy, synchronizowane dwukierunkowo z polem tekstowym "Głosy".

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
- `max_retries` i `timeout` — retry logic w `common.http.post_json()` (HTTP 429/5xx; timeouty zgłaszane jako błąd); przekazywane przez `_generate_*` do `post_json()`
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
- Anki API: `mw.col.get_note`, `mw.col.update_note`, `mw.col.update_notes` (przez `CollectionOp`), `mw.col.media.write_data`, `mw.taskman`, `CollectionOp`
- Własne: `common.config` (get_module_config), `common.text` (normalize_float, unique_filename, unique, split_separator_regex), `common.html` (clean_html), `common.http` (post_json — POST z retry; używany przez `_generate_kokoro`/`_generate_openrouter`)
- Kokoro: wymaga lokalnego serwera Kokoro TTS (Docker)
- OpenRouter: tylko klucz API, żadnych lokalnych zależności
- Brak pip packages
