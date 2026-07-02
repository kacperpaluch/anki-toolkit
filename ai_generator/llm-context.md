# LLM Context — ai_generator

## Co robi

Generuje treść pól kart przez AI. Każde pole karty może mieć własnego dostawcę, model i prompt. Działa w edytorze (przyciski workflowów + pomocniczy przycisk AI) i przeglądarce (równoległy batch dla zaznaczonych notatek). Pomija pola, które już mają treść.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Re-eksport hooków — importuje z `editor_ui`, `browser_ui`, `workflow` (`migrate_workflows`) |
| `_generator.py` | Tylko `get_config()` — czyta sekcję `ai_generator` z configu wtyczki. Bez singletona: każde uruchomienie (przycisk, PPM, workflow, batch) tworzy własny `FieldGenerator(get_config())`, więc równoległe generowania nie współdzielą stanu providerów (`last_error`/`last_usage`), a zmiany ustawień działają od razu |
| `editor_ui.py` | UI edytora — przyciski workflow (per workflow z `editor_button`), potem przycisk AI (wszystkie puste pola); `_GENERATING` guard zapobiega podwójnemu kliknięciu; świeży `FieldGenerator(get_config())` per uruchomienie; `saveNow(start)` zapewnia świeży stan note przed zadaniem; rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na polu dodaje „Wygeneruj/Regeneruj `pole` przez AI" (tylko pola ze skonfigurowanym promptem); `_on_generate_field_editor` woła `process_note(note, only_fields={field}, overwrite=True)` |
| `browser_ui.py` | UI przeglądarki — najpierw pozycje workflowów (po jednej na workflow z `config["workflows"]` → `_on_workflow_browser`), potem submenu `Generuj pola ▸` („Wszystkie puste" + per-pole „AI: def" spłaszczone po nazwie pola docelowego) i `Generuj zablokowane ▸` (pola `manual_only`); batch z natywnym paskiem `mw.progress` przez wspólny helper `common.progress` (`start_progress`/`update_progress`/`finish_progress`, `want_cancel()`) zamiast własnego QProgressDialog — trzyma Anki „busy", więc automatyczny backup/sync się odkłada i nie zasłania przycisku Anuluj; po zapisie `_save_changed_notes(browser, changed_notes, summary)` woła `deck_router.route_after_edit` (soft-import); cancel_flag; `_run_batch(only_fields=...)` i `_on_workflow_browser` — notatki wczytywane na głównym wątku (kolekcja Anki jest jednowątkowa), workery (`ThreadPoolExecutor(parallel_requests)`, chunki po `batch_limit`) tylko mutują je w pamięci, per-notatka własny `FieldGenerator`; batch pól zawsze `overwrite=False` (pomija wypełnione); dawne hardcodowane pipeline'y („Generuj wszystko…", „Rozdziel + generuj naukę…") są teraz zwykłymi workflowami seedowanymi przez `migrate_workflows()` |
| `field_generator.py` | Logika generowania — `process_note(note, only_fields=None, overwrite=False)`; `only_fields` filtruje scope, `overwrite=True` nadpisuje pełne pola; niezależna od UI, rozwiązuje model promptu z fallbackiem do modelu domyślnego i cache'uje providery per `(provider, model)`; **fallback modeli**: gdy `call_api()` zwróci `None`, sprawdza per-prompt `fallback_provider`+`fallback_model` (wyższy priorytet), potem per-dostawca `fallback_model`; fallback używa tego samego promptu, ale może użyć innego dostawcy; używa `common.clean_html_normalized()`, `common.safe_str()` |
| `template_engine.py` | Silnik szablonów: `{{pole}}` i `{% if %}...{% endif %}`; `template_structure_problems()` — czysta walidacja struktury bloków używana przez edytor promptów |
| `stats.py` | Lokalne statystyki użycia — liczniki per dzień (requesty, błędy, tokeny wej./wyj., pola, notatki) w `user_files/usage_stats.json` (legacy `ai_generator/usage_stats.json` migrowany przy pierwszym uruchomieniu); `get_stats(days=None, start=None, end=None)` agreguje zakres (`start`/`end` inclusive "YYYY-MM-DD"); thread-safe |
| `providers/__init__.py` | Rejestr `PROVIDERS`/`PROVIDER_LABELS` + fabryka `get_provider()`; definiuje też 5 cienkich klas zgodnych z OpenAI (`OpenAIProvider`, `OpenRouterProvider`, `CometAPIProvider`, `MistralProvider`, `NvidiaProvider`) dziedziczących po `OpenAICompatProvider` — różnią się tylko `API_URL`, `LABEL`, (Mistral, NVIDIA) `SUPPORTS_REASONING_EFFORT = False` i (OpenRouter) `EXTRA_HEADERS` z atrybucją aplikacji (`HTTP-Referer`/`X-Title`) |
| `providers/base.py` | ABC `BaseProvider` — interfejs + `_post(url, data, headers)` (POST z retry, deleguje do `common.http.post_json`) + `_post_with_reasoning_fallback()` (ponowna próba bez `reasoning_effort` gdy API zwróci błąd wspominający ten parametr) + wspólne parsery odpowiedzi `_parse_chat_completion()` (format OpenAI choices→message→content) i `_parse_messages()` (format Anthropic, pierwszy blok `type=="text"`); klasa `OpenAICompatProvider` z gotowym `call_api()` dla endpointów Bearer-auth Chat Completions |
| `providers/openai_compat.py` | Helpery dla providerów zgodnych z Chat Completions: wykrywanie modeli OpenAI reasoning, pomijanie `temperature`, parsowanie `message.content` string/list, `is_reasoning_effort_unsupported_error()` |
| `providers/anthropic.py` | Anthropic (Messages API, inny format niż OpenAI); `call_api()` deleguje rozbiór do `BaseProvider._parse_messages()` |
| `providers/google.py` | Google Gemini (generateContent API — własny rozbiór `candidates[0].content.parts`) |
| `providers/opencode_go.py` | OpenCode Go — Chat Completions dla większości modeli (`_parse_chat_completion`), Anthropic Messages dla MiniMax/Qwen3.x (`_parse_messages`); auto-detect na podstawie nazwy modelu; reasoning jako wolny string; `User-Agent` header (Cloudflare) |
| `providers/model_discovery.py` | Pobieranie dostępnych modeli z API każdego providera + dispatcher `fetch_models()`; bliźniacze endpointy `{"data":[{"id":...}]}` (openai/mistral/anthropic/cometapi/nvidia/opencode_go) idą przez wspólny `_fetch_simple()` z predykatem `keep`; Google i OpenRouter mają własne fetchery |
| `workflow.py` | Nazwane workflowy (`config["workflows"]`, lista `{name, editor_button, steps}`) — `get_workflows()`, `migrate_workflows()` (legacy pojedynczy `workflow` → lista + seed dwóch dawnych pipeline'ów + `context_menu`), `get_context_menu()`; `execute_step(note, step, ai_generator=None)` — wspólny wykonawca kroku (AI/dictionary/TTS/field_splitter), mutuje notatkę w pamięci; `run_workflow_editor()` — sekwencyjne kroki na jednej notatce w edytorze, jeden `FieldGenerator` per przebieg, guard `_RUNNING` blokuje podwójne odpalenie |

## Przepływ danych

```
Kliknięcie przycisku (edytor)
  → editor_ui._on_generate_editor()
  → sprawdź _GENERATING — jeśli ten edytor już generuje: tooltip "Generowanie już trwa..." i return
  → dodaj editor_id do _GENERATING
  → gen = FieldGenerator(get_config())           # świeża instancja per uruchomienie — brak współdzielonego stanu między oknami edytora
  → editor.saveNow(start)                        # synchronizuje webview → editor.note PRZED zadaniem
      → start() (callback na głównym wątku po saveNow):
          → note = editor.note                   # świeży stan po synchronizacji
          → mw.taskman.run_in_background(task)   # nie blokuje UI — API calls w tle
              → FieldGenerator.process_note(note) → dict[str, str]   # only_fields=None, overwrite=False
                  → dla każdego pola w config note_types:
                      → pomiń jeśli pole niepuste (overwrite=False)
                      → _resolve_provider(provider_name, model)   # cache per (provider, model); brak modelu używa domyślnego dostawcy
                      → render_template(prompt, fields_map) # podstawia {{pola}}, max depth=50; pola są oczyszczone z HTML przez common.clean_html_normalized
                      → provider.call_api(prompt)           # HTTP do API, timeout=self.timeout, retry self.max_retries z backoff
                      → note[field] = wynik; changed[field] = wynik
                  → zwraca dict {field: wynik} (pusty = nic nie wygenerowano)
              → on_done (główny wątek):
                  → usuń editor_id z _GENERATING
                  → jeśli edytor nadal pokazuje tę samą notatkę: editor.saveNow(apply)
                  → apply():
                      → dla każdego field w ai_results: note[field] = wynik_AI  # zapis do notatki złapanej na starcie
                      → jeśli editor.note is note: editor.loadNote()
                      → w przeciwnym razie (użytkownik przełączył kartę): mw.col.update_note(note)  # wynik nie ginie i nie trafia do cudzej karty
                  → tooltip z błędem providera jeśli API zwróciło błąd; inaczej "Brak pól do wygenerowania." jeśli ai_results pusty

PPM na polu w edytorze (gui_hooks.editor_will_show_context_menu → _on_editor_context_menu):
  → opcja pojawia się TYLKO gdy pole pod kursorem (editor.currentField → note.keys()[idx]) ma skonfigurowany prompt dla bieżącego typu notatki
  → label: "Wygeneruj „pole" przez AI" (pole puste) lub "Regeneruj „pole" przez AI" (pole pełne)
  → _on_generate_field_editor(editor, field_name)
      → ten sam guard _GENERATING + saveNow + editor.note is note co główny przycisk
      → process_note(note, only_fields={field_name}, overwrite=True)   # nadpisuje nawet pełne

Batch w przeglądarce (menu kontekstowe → Generuj pola ▸):
  → submenu zbudowane z _all_configured_target_fields(config) — spłaszczone po nazwie pola docelowego (wszystkie typy notatek)
  → "Wszystkie puste" → _on_generate_browser() → _run_batch(only_fields=None)
  → "AI: def" itp.   → _on_generate_field_browser(field) → _run_batch(only_fields={field})
  → notatki wczytywane z mw.col.get_note(nid) NA GŁÓWNYM WĄTKU (kolekcja Anki jest jednowątkowa); note.note_type() rozgrzewa cache modeli — workery robią na nim już tylko odczyt z pamięci
  → start_progress() (common/progress.py) = natywny pasek mw.progress.start(max=total, immediate=True) (NIE własny QProgressDialog)
      → celowo: trzyma Anki w stanie "busy", więc timer automatycznego backupu/synchronizacji odkłada się zamiast wyskakiwać własnym modalem NAD paskiem batcha i blokować Anuluj
      → anulowanie: update_progress() na głównym wątku czyta mw.progress.want_cancel() → ustawia cancel_flag; workery przerywają między chunkami
  → mw.taskman.run_in_background(task)         # praca w tle; pasek mw.progress blokuje całe okno Anki na czas batcha
      → ThreadPoolExecutor(max_workers=parallel_requests)
      → chunk po batch_limit notatek (sleep batch_sleep między chunkami)
      → dla każdej (wczytanej wcześniej) notatki w chunku (równolegle w puli):
          → gen = FieldGenerator(config)                # NOWA instancja per notatka — provider trzyma last_error/last_usage
          → gen.process_note(note, only_fields=..., overwrite=False)   # mutuje notatkę tylko w pamięci, BEZ dostępu do mw.col; batch zawsze pomija wypełnione
          → changed_notes.append(note) jeśli gen zmienił pola
      → zbiera changed_notes w liście (pod lockiem)
  → on_done (główny wątek):
      → mw.progress.finish()                     # zamknąć nasz pasek PRZED CollectionOp (inaczej "already busy")
      → _save_changed_notes(browser, changed_notes, summary)
          → CollectionOp(parent=browser, op=lambda col: col.update_notes(changed_notes))
          → po zapisie: deck_router.route_after_edit(browser, [n.id for n in changed_notes]) (soft-import, no-op gdy moduł wyłączony/brak reguł)
      → brak mw.reset() — CollectionOp sam odświeża kolekcję (jeden krok undo)

Batch workflow w przeglądarce (menu kontekstowe → <nazwa workflowu>):
  → _on_workflow_browser(browser, workflow) — notatki preładowane na głównym wątku, jak w _run_batch
  → ThreadPoolExecutor(parallel_requests), chunki po batch_limit; per notatka:
      → gen = FieldGenerator(config)             # kroki w obrębie notatki sekwencyjne, notatki równolegle
      → dla każdego kroku: execute_step(note, step, ai_generator=gen)
  → zapis i routing jak wyżej (_save_changed_notes)

Przyciski workflowów w edytorze:
  → editor_ui.on_editor_buttons_init() dodaje po jednym przycisku na każdy workflow z `editor_button=true` i niepustymi `steps` (przed przyciskiem AI)
  → workflow.run_workflow_editor(editor, workflow)
      → jeśli editor_id jest w `_RUNNING`: tooltip "Workflow już trwa..." i return
      → saveNow → notatka jest łapana RAZ na starcie — wszystkie kroki działają na niej,
        więc przełączenie karty w edytorze w trakcie nie miesza danych między notatkami
      → jeden FieldGenerator per przebieg (cache providerów między krokami AI, brak współdzielenia między oknami)
      → sekwencyjnie wykonuje kroki: execute_step(note, step, ai_generator=gen) (każdy w tle; update_note pomijany dla note.id == 0);
        wewnątrz kroku TTS pliki audio są generowane równolegle (tts.processor.process_single_note → ThreadPoolExecutor)
      → po ostatnim kroku usuwa editor_id z `_RUNNING`, wywołuje `editor.loadNote()` (tylko gdy edytor nadal pokazuje tę notatkę) i pokazuje jedno podsumowanie
```

## Konfiguracja

Konfiguracja edytowalna przez **Narzędzia → Anki Toolkit → Ustawienia...**:
- Zakładka **Workflowy** (osobna, top-level) — lista nazwanych workflowów (nazwa, flaga przycisku edytora, kroki z parametrami) + widoczność wbudowanych sekcji menu PPM (`context_menu`)
- Zakładka **AI Generator → Prompty** — dwupanelowy edytor: lista typ notatki/zadanie po lewej, edytor (nazwa zadania, target, dostawca, model, prompt) po prawej; model jest edytowalnym comboboxem z pobieraniem listy z API i filtrowaniem po dowolnym fragmencie nazwy; typ notatki i pole docelowe to edytowalne comboboxy z danymi z kolekcji, przycisk „Wstaw pole ▾" wstawia `{{pole}}` w pozycji kursora, przycisk „Wstaw warunek ▾" wstawia szkielet `{% if pole %}…{% else %}…{% endif %}` (zaznaczony tekst trafia do gałęzi „if"), a walidacja na żywo ostrzega o nieistniejącym typie notatki, polu docelowym i nieznanych `{{polach}}` w prompcie (targety wcześniejszych zadań tego typu notatki są uznawane za znane) oraz o błędach struktury bloków `{% if %}` (niedomknięty/osierocony/podwójny else/zagnieżdżony — `template_engine.template_structure_problems()`, czysta funkcja działająca bez kolekcji)
- Zakładka **AI Generator → Dostawcy** — karty dostawców AI, klucze API, modele (combo z cache `cached_models` zapisywanym w configu — przeżywa restart), model zapasowy (fallback_model), temperatura, reasoning/max tokens, **limit RPM + maks. równoległych per dostawca** (OpenRouter dodatkowo checkbox „tylko :free"); sekcja **Zaawansowane** zawiera batch/retry/request timeout/skip tags

Zmiana kluczy API i promptów **nie wymaga restartu Anki** — każde uruchomienie generowania tworzy świeży `FieldGenerator(get_config())`, więc kolejne użycie czyta aktualną konfigurację.

### Sekcja `ai_generator` w config.json (szablon domyślny)

```json
{
  "button_label": "AI",
  "skip_tags": ["skip-ai"],
  "batch_limit": 3,
  "batch_sleep": 1.0,
  "max_retries": 3,
  "request_timeout": 30,
  "providers": {
    "openai":     {"api_key": "...", "model": "gpt-4o", "temperature": 0.2, "reasoning_effort": "medium", "fallback_model": "", "cached_models": []},
    "google":     {"api_key": "...", "model": "gemini-2.0-flash", "temperature": 0.2, "fallback_model": "", "cached_models": []},
    "anthropic":  {"api_key": "...", "model": "claude-3-5-haiku-20241022", "temperature": 0.2, "max_tokens": 2048, "fallback_model": "", "cached_models": []},
    "openrouter": {"api_key": "...", "model": "anthropic/claude-3.5-haiku", "temperature": 0.2, "reasoning_effort": "medium", "fallback_model": "", "cached_models": [], "rpm": 20, "max_concurrent": 1, "rate_limit_free_only": true},
    "cometapi":   {"api_key": "...", "model": "grok-4-1-fast-non-reasoning", "temperature": 0.2, "reasoning_effort": "medium", "fallback_model": "", "cached_models": []},
    "mistral":    {"api_key": "...", "model": "mistral-small-latest", "temperature": 0.2, "fallback_model": "", "cached_models": [], "rpm": 40, "max_concurrent": 1},
    "nvidia":     {"api_key": "...", "model": "meta/llama-3.3-70b-instruct", "temperature": 0.2, "fallback_model": "", "cached_models": []},
    "opencode_go": {"api_key": "...", "model": "deepseek-v4-pro", "temperature": 0.6, "reasoning_effort": "max", "fallback_model": "", "cached_models": []}
  },
  "note_types": {
    "NazwaTypuNotatki": {
      "klucz": {
        "target": "nazwa_pola_w_karcie",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "fallback_provider": "openrouter",
        "fallback_model": "anthropic/claude-3.5-haiku",
        "prompt": "Prompt z {{ang}} i {{pol}}"
      }
    }
  }
}
```

- `skip_tags` — lista tagów wykluczających (tablica stringów); notatka z dowolnym z tych tagów jest pomijana w całości przez `process_note` (zwraca `{}`), bez żadnych wywołań API ani aktualizacji; obsługuje też stary format string `"skip_tag"` (backward compat); konfigurowalny przez UI jako pole tekstowe z tagami oddzielonymi przecinkami
- `batch_limit` — liczba kart w jednej grupie; po każdej grupie następuje przerwa `batch_sleep` sekund; przetwarzane są **wszystkie** zaznaczone karty
- `batch_sleep` — pauza między grupami kart (unikanie rate limitów API)
- `max_retries` — liczba prób przy HTTP 429/5xx oraz błędach połączenia/timeoutach, przekazywana do `BaseProvider` przez `get_provider()` i `field_generator._resolve_provider()`; domyślnie `3`
- `request_timeout` — timeout urlopen w `common.http.post_json()` (delegowane z `BaseProvider._post()`); domyślnie `30` sekund
- `providers.<name>.rpm` — limit żądań na minutę dla dostawcy; żądania rozkładane równomiernie (`60/rpm` s odstępu), więc batch nie burstuje; `0`/brak = bez limitu. OpenRouter domyślnie `20`, Mistral `40` (≈0.83 req/s free tier z marginesem)
- `providers.<name>.max_concurrent` — maks. równoległych żądań do dostawcy (semafor); `0`/brak = bez limitu; darmowe API zwykle wymagają `1`
- `providers.openrouter.rate_limit_free_only` — gdy `true` (domyślnie dla OpenRoutera), limit dotyczy tylko modeli z `:free` w nazwie; gdy `false`, wszystkich żądań. Pole istnieje tylko dla OpenRoutera; inni dostawcy zawsze dławią wszystko. Stare globalne `free_model_rate_limit`/`free_model_max_concurrent` (usunięte z szablonu config.json) są nadal czytane jako back-compat dla OpenRoutera, gdy w zapisanej konfiguracji brak per-provider `rpm`
- `providers.openai.reasoning_effort` / `providers.cometapi.reasoning_effort` / `providers.openrouter.reasoning_effort` — dropdown z wartościami `none/minimal/low/medium/high/xhigh`; wysyłany tylko dla modeli OpenAI reasoning (`o1/o3/o4`, `gpt-5+`); dla tych modeli nie wysyłane `temperature`; fallback automatyczny przy HTTP 400
- `providers.opencode_go.reasoning_effort` — wolny tekst (QLineEdit w UI); wartości per model: `max` dla DeepSeek V4 Pro, inne modele mają inne wartości lub nie obsługują; puste = nie wysyłane; fallback automatyczny przy HTTP 400; `opencode_go` wymaga `User-Agent` header (Cloudflare blokuje brak UA); auto-detect formatu API: Chat Completions dla GLM/Kimi/DeepSeek/MiMo, Anthropic Messages dla MiniMax M2.5/M2.7/Qwen3.5/3.6 Plus
- Bez globalnego cache generatora: każde uruchomienie tworzy świeży `FieldGenerator(get_config())` (edytor per klik, workflow per przebieg, batch per notatka) — konfiguracja działa od razu po zapisie ustawień, bez resetu
- Każdy prompt zapisuje `provider` i `model`; starsze wpisy bez `model` używają `providers.<provider>.model`. Instancje providerów są cache'owane per `(provider, model)` w obrębie jednej instancji `FieldGenerator`.
- Pola generowane są w kolejności kluczy w `note_types`; pole może referencjonować wynik poprzedniego pola przez `{{nazwa}}` w prompcie

## Silnik szablonów

```
{{ang}}                          → wartość pola "ang" z karty
{% if def %}...{% endif %}       → renderuje blok tylko gdy pole "def" niepuste
{% if def %}...{% else %}...{% endif %}  → z fallbackiem
```

**Ograniczenie:** zagnieżdżone `{% if %}` wewnątrz `{% if %}` nie są obsługiwane — regex dopasowuje pierwszy napotkany `{% endif %}`. Rekurencja z limitem `MAX_DEPTH = 50` dotyczy tylko renderowania zawartości bloków.

## Fallback modeli

Gdy `provider.call_api(prompt)` zwróci `None` (błąd API, rate limit, brak środków, brak treści), `field_generator.process_note()` sprawdza fallback w dwóch poziomach priorytetu:

1. **Per-prompt** (wyższy): `field_cfg.get("fallback_provider")` + `field_cfg.get("fallback_model")`. Jeśli `fallback_provider` jest pusty, używa tego samego dostawcy co model główny. Jeśli `fallback_model` jest pusty, przejdź do poziomu 2.
2. **Per-dostawca** (niższy): `providers.<provider>.get("fallback_model")`. Używa tego samego dostawcy i klucza API.

Logika w `process_note()`:
```python
result = provider.call_api(prompt)
if result:
    # sukces — zapisz pole
else:
    # sprawdź per-prompt fallback
    fallback_provider_name = field_cfg.get("fallback_provider", "")
    fallback_model = field_cfg.get("fallback_model", "")
    if not fallback_model:
        # brak per-prompt — sprawdź per-dostawca
        p_cfg = config["providers"].get(provider_name, {})
        fallback_model = p_cfg.get("fallback_model", "")
        fallback_provider_name = ""  # ten sam dostawca
    if not fallback_model:
        # brak fallbacku — zaloguj błąd
        continue
    # uruchom fallback
    fb_provider = self._resolve_provider(fb_name, fallback_model)
    result = fb_provider.call_api(prompt)
    # statystyki fallbacku zliczane osobno per (fb_name, fb_model)
```

Fallback używa tego samego promptu (już wyrenderowanego), ale nowa instancja providera z innym modelem/kluczem. `stats.record_request()` jest wołane osobno dla głównego i fallbackowego wywołania.

## Rate limiter per dostawca (`RateLimiter`)

Klasa `RateLimiter` w `field_generator.py` — singleton z **jednym kubełkiem (bucket) per dostawca**. Kubełek wymusza:

- **Równomierne tempo (RPM)** — odstęp `60/rpm` sekund między *startami* żądań, więc batch nie burstuje (kluczowe dla darmowego tieru API typu Mistral: 0.83 req/s). `rpm<=0` = bez limitu tempa.
- **Limit jednoczesności** — semafor `max_concurrent`; `max_concurrent<=0` = bez limitu.
- **Zakres `free_only`** — gdy `True`, kubełek dotyczy **tylko** modeli z `:free` w nazwie (warianty darmowe OpenRoutera); płatne modele tego dostawcy przechodzą bez dławienia. Gdy `False`, limit obejmuje **wszystkie** żądania dostawcy (darmowy klucz API dławi cały klucz, nie pojedyncze modele).

Szczegóły:
- **Singleton** — jeden per proces; limity są per API key, więc bucket per nazwa dostawcy
- `configure(provider, rpm, max_concurrent, free_only)` — wołane w `FieldGenerator._configure_rate_limit()` podczas rozwiązywania dostawcy; czyta per-provider `rpm`/`max_concurrent`/`rate_limit_free_only`. **Back-compat**: jeśli `openrouter` nie ma per-provider `rpm`, bierze stare globalne `free_model_rate_limit`/`free_model_max_concurrent` (z `free_only=True`)
- `slot(provider, model)` — context manager owijający każde `provider.call_api()` (główne + fallback); no-op gdy brak limitu dla danego dostawcy/modelu
- Pacing trzyma lock kubełka przez `time.sleep`, więc starty pozostają równomiernie rozłożone nawet przy wielu wątkach batcha
- **TPM (tokeny/min) nie jest egzekwowane** — liczba tokenów znana dopiero po odpowiedzi; sporadyczne przekroczenia łapie backoff 429 w `common/http.post_json`

UI: pola **Limit RPM** i **Maks. równoległych** są na karcie każdego dostawcy (`settings/ai_generator_tab.py`); checkbox **„Limit tylko dla modeli :free"** tylko dla OpenRoutera.

## Dodanie nowego dostawcy AI

1. Provider zgodny z OpenAI Chat Completions: dziedzicz po `OpenAICompatProvider` w `providers/__init__.py`, ustaw tylko `API_URL` i `LABEL` (opcjonalnie `SUPPORTS_REASONING_EFFORT`). Provider o innym formacie: utwórz `providers/moj_provider.py`, dziedzicz po `BaseProvider` i zaimplementuj `call_api()` (możesz wykorzystać `_parse_chat_completion()` / `_parse_messages()` z bazy)
2. Dodaj klasę do `PROVIDERS` w `providers/__init__.py` — `PROVIDER_LABELS` i `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` są auto-derivowane z `PROVIDERS`; `settings/prompts_tab.py` iteruje po `PROVIDER_LABELS` bez manualnej listy

### Format odpowiedzi API

| Provider | Format żądania | Pole z odpowiedzią |
|---|---|---|
| OpenAI / CometAPI / OpenRouter | `{"messages": [...], "reasoning_effort": opcjonalnie}` | `choices[0].message.content` |
| Mistral / NVIDIA NIM | `{"messages": [...]}` | `choices[0].message.content` |
| Anthropic | `{"messages": [...], "max_tokens": self.max_tokens or 2048}` | `content[0].text` |
| Google | `{"contents": [{"parts": [{"text": ...}]}]}` | `candidates[0].content.parts[0].text` |
| OpenCode Go (chat) | `{"messages": [...], "temperature": ..., "reasoning_effort": opcjonalnie}` | `choices[0].message.content` |
| OpenCode Go (messages) | `{"messages": [...], "max_tokens": ..., "temperature": ...}` | `content[0].text` |

`max_tokens` dla Anthropic i OpenCode Go Messages (wymagany przez API) pochodzi z `provider_cfg.get("max_tokens")` → `BaseProvider.max_tokens`. Domyślnie `2048`. Konfigurowalny per-provider w `config.json`.

Providery zgodne z OpenAI Chat Completions współdzielą `OpenAICompatProvider.call_api()` (w `base.py`) i helpery z `providers/openai_compat.py`. Jeśli nazwa modelu wygląda jak OpenAI reasoning, `temperature` nie jest wysyłane. `reasoning_effort` jest wysyłane przez `openai`, `cometapi` i `openrouter` (tylko dla rozpoznanych modeli reasoning); `mistral` i `nvidia` go nie wysyłają (`SUPPORTS_REASONING_EFFORT = False`); `opencode_go` wysyła `reasoning_effort` bezpośrednio jako wolny string jeśli ustawiony (bez sprawdzania nazwy modelu). Jeśli model nie obsługuje `reasoning_effort` (HTTP 400 wspominający ten parametr), `_post_with_reasoning_fallback()` automatycznie ponawia żądanie bez niego.

Rozbiór odpowiedzi jest wspólny: `BaseProvider._parse_chat_completion()` dla formatu OpenAI (`choices[0].message.content`, z `extract_message_content` dla string/list) i `_parse_messages()` dla formatu Anthropic (pierwszy blok `type=="text"`); Google ma własny rozbiór `candidates`. Wszystkie walidują strukturę odpowiedzi przed dostępem — sprawdzają niepustość tablic i istnienie kluczy. Błędy parsowania są logowane przez `self.logger` i zapisywane do `self.last_error`. Retry (3 próby, exponential backoff dla HTTP 429/5xx oraz błędów połączenia/timeoutów) jest zaimplementowany w `common.http.post_json()` — `BaseProvider._post(url, data, headers)` serializuje `data` do JSON i deleguje; `self.last_error` jest ustawiane z zwróconego stringa błędu. Klucz API Google jest wysyłany w nagłówku `x-goog-api-key` (nie w URL-u — URL-e trafiają do logów).

## Zależności

- Stdlib: `json`, `re`, `logging`
- Anki API: `mw.addonManager.getConfig`, `mw.col.get_note`, `mw.col.update_note`, `mw.taskman.run_in_background`, `mw.taskman.run_on_main`, `mw.progress.start/update/finish/want_cancel` (natywny pasek batcha)
- Własne: `common.ADDON_NAME`, `common.clean_html_normalized`, `common.safe_str`, `common.http.post_json` (POST z retry)
- Batch używa natywnego paska `mw.progress` (nie `QProgressDialog`) — trzyma Anki „busy", więc automatyczny backup/sync się odkłada i nie zasłania przycisku Anuluj
- Brak pip packages

## Uwagi implementacyjne

- `BaseProvider.__init__` przyjmuje `max_retries`, `timeout`, `max_tokens`, `reasoning_effort` — przekazywane przez `get_provider()` z wartości czytanych przez `_resolve_provider()` z `self._config` oraz z `provider_cfg`
- `openai_compat.add_temperature_if_supported()` jest używany przez `openai`, `cometapi`, `openrouter`, `mistral`, `nvidia`
- `openai_compat.add_reasoning_effort_if_supported()` jest używany przez `openai`, `cometapi`, `openrouter`; `mistral` i `nvidia` go nie używają; `opencode_go` nie używa — wysyła `reasoning_effort` bezpośrednio jako wolny string
- `BaseProvider._post(url, data, headers)` serializuje `data` do JSON i deleguje do `common.http.post_json()` z `self.max_retries` i `self.timeout`; ustawia `self.last_error` z zwróconego stringa błędu (lub `None` przy sukcesie)
- `BaseProvider._post_with_reasoning_fallback()` opakowuje `_post()`: jeśli żądanie zwróci błąd zawierający `"reasoning_effort"`, usuwa ten parametr z body i ponawia; używany też przez `opencode_go`
- `field_generator.py` nie zawiera żadnych wywołań `showWarning` ani Qt UI — błędy są logowane przez `logger` i ustawiane w `self.last_error`; ewentualne ostrzeżenia Qt są wywoływane przez `editor_ui`/`browser_ui` w głównym wątku
- Przycisk AI w edytorze działa asynchronicznie (`run_in_background`) — UI nie zamarza podczas wywołania API; sekwencja: `saveNow(start)` → `start()` czyta `editor.note` → `run_in_background(task)` → `on_done` → `saveNow(apply)` → `loadNote()`
- `_GENERATING: set[int]` w `editor_ui` — zbiór ID aktywnych edytorów dla przycisku AI; zapobiega wyścigowi podwójnego kliknięcia (drugie kliknięcie podczas trwającego generowania pokazuje tooltip i jest ignorowane); ID jest usuwany w `on_done` niezależnie od wyniku
- `_RUNNING: set[int]` w `workflow.py` — analogiczna ochrona dla przycisku workflow
- `editor.saveNow(start)` na początku `_on_generate_editor` — synchronizuje webview → `editor.note` PRZED startem zadania tła; `note = editor.note` jest czytany wewnątrz callbacku `start()`, dzięki czemu sprawdzenie pustości pól widzi rzeczywisty stan widoczny użytkownikowi
- `fields_map` budowany przez `common.clean_html_normalized()` — pola notatki ze znacznikami HTML (`<div>`, `<br>`, `&nbsp;`) są oczyszczane przed wstawieniem do promptu; wyniki AI trafiają do karty surowo (bez strippowania HTML — AI powinno zwracać czysty tekst)
- `process_note` zwraca `dict[str, str]` (nie `bool`) — editor_ui używa tego dict do bezwarunkowego nadpisania pól AI po `saveNow`; browser_ui używa go jako truthy check, a notatki zmienione w batchu są zapisywane atomowo przez `CollectionOp(parent=browser, op=lambda col: col.update_notes(changed_notes))` (jeden krok undo), a nie per-note `mw.col.update_note`
- `FieldGenerator.last_error` przechowuje ostatni błąd providera/API; editor_ui pokazuje go zamiast mylącego "Brak pól do wygenerowania.", a browser_ui dolicza błędy w podsumowaniu batcha
- `editor.saveNow(apply)` w `on_done` synchronizuje stan webview → `editor.note` przed aplikowaniem wyników AI; zachowuje edycje pól których AI nie dotknęło. `apply()` pisze do notatki złapanej na starcie i sprawdza tożsamość (`editor.note is note`) — jeśli użytkownik przełączył kartę w trakcie generowania, wynik jest zapisywany do kolekcji przez `mw.col.update_note()` zamiast do aktualnie wyświetlanej notatki
- `opencode_go` auto-wykrywa format API: modele w `_MESSAGES_FORMAT_MODELS` (minimax-m2.5, minimax-m2.7, qwen3.5-plus, qwen3.6-plus) używają endpointu `/messages`; pozostałe `/chat/completions`; auth zawsze `Bearer`; `User-Agent` header wymagany przez Cloudflare
- Pola konfiguracyjne note-type (`target`, `provider`, `prompt`) są normalizowane przez `safe_str()` z `common.text` przed użyciem; wartości liczbowe (`batch_sleep`, `temperature`) pochodzą z widgetów Qt (zakresy wymuszone w UI) lub z `.get()` z wartością domyślną
- Throttling: paczki na poziomie przeglądarki (sleep co `batch_limit` notatek) + per-dostawca tempo/jednoczesność przez `RateLimiter.slot()` w `field_generator` (patrz „Rate limiter per dostawca")
- **Statystyki użycia**: każdy `call_api()` wywołuje `self._capture_usage(res_data)` (BaseProvider) — wyciąga tokeny z `usage.prompt/completion_tokens` (OpenAI-compat), `usage.input/output_tokens` (Anthropic) lub `usageMetadata` (Gemini) do `provider.last_usage`; `field_generator.process_note()` rejestruje przez `stats.record_request()` (per provider/model) i `stats.record_note()`; dashboard w **Ustawienia → Statystyki** z wyborem zakresu (dziś/7/30/365 dni/wszystko/własny zakres dat od–do — `get_stats(start=..., end=...)`, granice inclusive)
