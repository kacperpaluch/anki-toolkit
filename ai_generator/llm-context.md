# LLM Context — ai_generator

## Co robi

Generuje treść pól kart przez AI. Każde pole karty może mieć własnego dostawcę, model i prompt. Działa w edytorze (przyciski workflowów + pomocniczy przycisk AI) i przeglądarce (równoległy batch dla zaznaczonych notatek). Pomija pola, które już mają treść (poza PPM „Regeneruj”), a w trybie automatycznym także pola `manual_only` („Tylko na żądanie”).

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Re-eksport hooków — importuje z `editor_ui` i `browser_ui` |
| `_generator.py` | Tylko `get_config()` — czyta sekcję `ai_generator` z configu wtyczki. Bez singletona: każde uruchomienie (przycisk, PPM, workflow, batch) tworzy własny `FieldGenerator(get_config())`, więc równoległe generowania nie współdzielą stanu błędów providerów, a zmiany ustawień działają od razu |
| `editor_ui.py` | UI edytora — przyciski workflow (per workflow z `editor_button`), potem przycisk AI (wszystkie puste pola); wspólny `common.editor_operation` blokuje równoległe AI/TTS/słownik/workflow na tej samej instancji edytora; świeży `FieldGenerator(get_config())` per uruchomienie; `saveNow(start)` zapewnia świeży stan note przed zadaniem; rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na polu dodaje „Wygeneruj/Regeneruj `pole` przez AI" (tylko pola ze skonfigurowanym promptem); `_on_generate_field_editor` woła `process_note(note, only_fields={field}, overwrite=True)` |
| `browser_ui.py` | UI przeglądarki — workflowy, generowanie wybranych pól i Batch API. Notatki są wczytywane na głównym wątku, workery mutują je wyłącznie w pamięci, a wynik jest zapisywany jednym `CollectionOp`. |
| `batch_backfill.py` | Orkiestracja Batch API bez szczegółów HTTP: budowanie pustych pól, grupowanie modeli, budżet tokenów i `_openai_blocked_until`, persistence `user_files/ai_batches.json`, joby, dispatch przez modułowe seamy `_submit_*`/`_poll_*`, polling oraz idempotentne `apply_results()`. Seamy są celowo wywoływane niekwalifikowanie, aby testy mogły patchować namespace `batch_backfill`. **Własność kolekcji:** store jest wspólny dla profili, więc rekordy i joby noszą `col` (= `mw.col.path`, czytane przez `current_col_id()`); `pending_batches()`/`active_jobs()` filtrują po nim (`_mine()`, rekordy bez `col` są wstrzymane do ręcznego przypisania), a `_all_pending()` celowo tego nie robi — limit kolejki tokenów OpenAI jest per organizacja. |
| `batch_openai.py` | Mechanika sieciowa OpenAI Batch API: JSONL, multipart Files API, create/poll, pobranie wyników i cleanup plików. Budżet, backoff i persistence pozostają w `batch_backfill.py`. |
| `batch_openrouter.py` | Mechanika sieciowa OpenRouter Batch API: inline JSON (bez uploadu plików), jeden model na batch, wyniki inline w obiekcie batcha. `endpoint`+`model` muszą być serializowane przed `requests` (stream-parse). Model batch jest wyprowadzany z skonfigurowanego przez `_batch_model()` (sufiks `:batch`), więc nie ma osobnego pola konfiguracji. |
| `batch_anthropic.py` | Mechanika sieciowa Anthropic Batch API: inline requests, submit/poll i normalizacja odpowiedzi. |
| `field_generator.py` | Logika generowania — `process_note(note, only_fields=None, overwrite=False)`; `only_fields` filtruje scope, `overwrite=True` nadpisuje pełne pola; selekcja pól wydzielona do modułowego `iter_note_fields(note, config, only_fields, overwrite)` (współdzielona z `batch_backfill`); niezależna od UI, rozwiązuje model promptu z fallbackiem do modelu domyślnego i cache'uje providery per `(provider, model, temperature)`; per-prompt `temperature` nadpisuje domyślną dostawcy (przekazywana też do fallbacku); **fallback modeli**: gdy `call_api()` zwróci `None`, sprawdza per-prompt `fallback_provider`+`fallback_model` (wyższy priorytet), potem per-dostawca `fallback_model`; fallback używa tego samego promptu, ale może użyć innego dostawcy; używa `common.clean_html_normalized()`, `common.safe_str()` |
| `template_engine.py` | Silnik szablonów: `{{pole}}` i `{% if %}...{% endif %}`; `template_structure_problems()` — czysta walidacja struktury bloków używana przez edytor promptów |
| `providers/__init__.py` | Rejestr `PROVIDERS`/`PROVIDER_LABELS` + fabryka `get_provider()`; definiuje też 2 cienkie klasy zgodne z OpenAI (`OpenAIProvider`, `OpenRouterProvider`) dziedziczące po `OpenAICompatProvider` — różnią się tylko `API_URL`, `LABEL` i (OpenRouter) `EXTRA_HEADERS` z atrybucją aplikacji (`HTTP-Referer`/`X-Title`) |
| `providers/base.py` | ABC `BaseProvider` — flaga klasowa `REQUIRES_API_KEY` (False dla dostawców lokalnych; `field_generator` pomija dla nich wymóg klucza) + `self.options` z pełną sekcją configu dostawcy (ustawienia spoza wspólnego zestawu, np. `binary_path`) + interfejs + `_post(url, data, headers)` (POST z retry, deleguje do `common.http.post_json`) + `_post_with_reasoning_fallback()` (ponowna próba bez `reasoning_effort` gdy API zwróci błąd wspominający ten parametr) + wspólne parsery odpowiedzi `_parse_chat_completion()` (format OpenAI choices→message→content) i `_parse_messages()` (format Anthropic, pierwszy blok `type=="text"`); klasa `OpenAICompatProvider` z gotowym `call_api()` dla endpointów Bearer-auth Chat Completions |
| `providers/openai_compat.py` | Helpery dla providerów zgodnych z Chat Completions: wykrywanie modeli OpenAI reasoning, pomijanie `temperature`, parsowanie `message.content` string/list, `is_reasoning_effort_unsupported_error()` |
| `providers/anthropic.py` | Anthropic (Messages API, inny format niż OpenAI); `call_api()` deleguje rozbiór do `BaseProvider._parse_messages()` |
| `providers/local_cli.py` | Wspólna warstwa dostawców lokalnych: `search_path()` (PATH rozszerzony o `/opt/homebrew/bin`, `/usr/local/bin`, `/opt/local/bin`, `~/.local/bin`, `~/.bun/bin`, `~/.npm-global/bin`, `~/bin` — aplikacja GUI na macOS nie dziedziczy PATH-u z powłoki, Anki z Findera dostaje z launchd tylko `/usr/bin:/bin:/usr/sbin:/sbin`), `find_executable(name, configured, extra_candidates)` (podana ścieżka jest wiążąca — brak binarki pod nią zwraca None zamiast cichej podmiany) i `clean_env(extra)` (PATH/HOME/USER/LOGNAME + zmienne regionalne; **`USER`/`LOGNAME` są konieczne**, bez nich odczyt keychaina na macOS zawodzi i zalogowane CLI raportuje brak logowania) |
| `providers/claude_cli.py` | Claude CLI — dostawca **lokalny**, `REQUIRES_API_KEY = False`; `call_api()` uruchamia `claude -p` (prompt przez stdin, wynik z pola `result` w `--output-format json`) w pustym katalogu tymczasowym; izolacja przez **odebranie zdolności**, nie sandboks: `--tools ""` usuwa wszystkie narzędzia, do tego `--strict-mcp-config`, `--disable-slash-commands`, `--no-session-persistence`; **nigdy `--bare`** (wymusza `ANTHROPIC_API_KEY`, nie czyta OAuth/keychaina → rozwaliłoby subskrypcję); `--system-prompt` zastępuje prompt Claude Code, obcinając wejście z ~2500 do ~280 tokenów na wywołanie; `find_binary()` (PATH → `~/.claude/local/claude`), `login_status()` (z `claude auth status --json`, które **nie zwraca tokenu**; logowanie kluczem API jest odrzucane — do tego jest dostawca `anthropic`), `fetch_models()` (aliasy rodzin — CLI nie wystawia listy) |
| `providers/codex_cli.py` | Codex CLI — dostawca **lokalny**, `REQUIRES_API_KEY = False`; `call_api()` uruchamia `codex exec` (prompt przez stdin, odpowiedź przez `-o <plik>`) z nienegocjowalnym utwardzeniem: `--sandbox read-only`, `-C <pusty katalog tymczasowy>`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, wycięte środowisko (`local_cli.clean_env` + przypięty `CODEX_HOME`); `find_binary()` (przez `local_cli.find_executable`, kandydat: ChatGPT.app), `codex_home()`, `login_status()` (czyta **wyłącznie** `auth_mode`, nigdy tokenu), `app_server_call()` — jednorazowa sesja `codex app-server --listen stdio://` po JSON-RPC (stdio, więc dziecko kończy się po zamknięciu stdin — bez osieroconych procesów) używana przez `fetch_models()` (`model/list`) i `fetch_rate_limits()` (`account/rateLimits/read`); własna pętla retry (`_is_retryable`) — błędy trwałe (zły model, brak logowania) nie są ponawiane |
| `providers/model_discovery.py` | Pobieranie dostępnych modeli z API każdego providera + dispatcher `fetch_models()`; bliźniacze endpointy `{"data":[{"id":...}]}` (openai/anthropic) idą przez wspólny `_fetch_simple()` z predykatem `keep`; OpenRouter ma własny fetcher, a dostawcy CLI pytają lokalną binarkę |
| `workflow.py` | Nazwane workflowy (`config["workflows"]`, lista `{name, editor_button, steps}`) — `execute_step()` mutuje notatkę w pamięci; `run_workflow_editor()` wykonuje sekwencyjne kroki z jednym `FieldGenerator` i wspólnym guardem edytora — kroki lecą na kopii z `detach_note()`, a po każdym kroku `merge_editor_note()` (kontrola profilu, zapis i odświeżenie webview po każdym kroku) na głównym wątku. |

## Przepływ danych

```
Kliknięcie przycisku (edytor)
  → editor_ui._on_generate_editor()
  → begin_editor_operation(editor, "generowanie AI") — jeśli dowolna akcja Toolkit już trwa na tym edytorze: tooltip i return
  → gen = FieldGenerator(get_config())           # świeża instancja per uruchomienie — brak współdzielonego stanu między oknami edytora
  → editor.saveNow(start)                        # synchronizuje webview → editor.note PRZED zadaniem
      → start() (callback na głównym wątku po saveNow):
          → note = editor.note                   # świeży stan po synchronizacji
          → clone, before = detach_note(note)    # worker pracuje na kopii, nie na editor.note
          → mw.taskman.run_in_background(task)   # nie blokuje UI — API calls w tle
              → FieldGenerator.process_note(clone) → dict[str, str]   # only_fields=None, overwrite=False
                  → dla każdego pola w config note_types:
                      → pomiń jeśli pole niepuste (overwrite=False) albo `manual_only` przy only_fields=None
                      → _resolve_provider(provider_name, model, temperature)   # cache per (provider, model, temperature)
                      → render_template(prompt, fields_map) # podstawia {{pola}}, max depth=50; pola są oczyszczone z HTML przez common.clean_html_normalized
                      → provider.call_api(prompt)           # HTTP do API, timeout=self.timeout, retry self.max_retries z backoff
                      → note[field] = wynik; changed[field] = wynik
                  → zwraca dict {field: wynik} (pusty = nic nie wygenerowano)
              → on_done (główny wątek):
                  → finish_editor_operation(editor, token) dopiero po zastosowaniu wyniku
                  → jeśli edytor nadal pokazuje tę samą notatkę: editor.saveNow(apply)
                  → apply():
                      → merge_editor_note(editor, note, clone, before)
                          → kontrola profilu i schematu; po przełączeniu świeża notatka z kolekcji
                          → zmiana dowolnego pola wejściowego pomija wyniki kroku
                          → zapis istniejącej notatki + OpChanges + odświeżenie aktualnego edytora
                  → tooltip: błąd providera ZAWSZE gdy `gen.last_error` (także przy częściowym sukcesie) + lista pól pominiętych przez merge; "Brak pól do wygenerowania." tylko gdy ai_results pusty

PPM na polu w edytorze (gui_hooks.editor_will_show_context_menu → _on_editor_context_menu):
  → opcja pojawia się TYLKO gdy pole pod kursorem (editor.currentField → note.keys()[idx]) ma skonfigurowany prompt dla bieżącego typu notatki
  → label: "Wygeneruj „pole" przez AI" (pole puste) lub "Regeneruj „pole" przez AI" (pole pełne)
  → _on_generate_field_editor(editor, field_name)
      → ten sam wspólny guard edytora + saveNow + editor.note is note co główny przycisk
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
          → gen = FieldGenerator(config)                # NOWA instancja per notatka — provider trzyma last_error
          → gen.process_note(note, only_fields=..., overwrite=False)   # mutuje notatkę tylko w pamięci, BEZ dostępu do mw.col; batch zawsze pomija wypełnione
          → changed_notes.append(note) jeśli gen zmienił pola
      → zbiera changed_notes w liście (pod lockiem)
  → on_done (główny wątek):
      → mw.progress.finish()                     # zamknąć nasz pasek PRZED CollectionOp (inaczej "already busy")
      → save_detached_notes(browser, col, changed_notes, before, summary)   # common.editor_operation
          → CollectionOp: notatki czytane na świeżo, zapis tylko pól zmienionych przez workery;
            notatka zmieniona w trakcie batcha jest pomijana (jej pola mogły być wejściem),
            inny profil niż przy starcie → nic nie zapisuje
      → brak mw.reset() — CollectionOp sam odświeża kolekcję (jeden krok undo)

Batch workflow w przeglądarce (menu kontekstowe → <nazwa workflowu>):
  → _on_workflow_browser(browser, workflow) — notatki preładowane na głównym wątku, jak w _run_batch
  → ThreadPoolExecutor(parallel_requests), chunki po batch_limit; per notatka:
      → gen = FieldGenerator(config)             # kroki w obrębie notatki sekwencyjne, notatki równolegle
      → dla każdego kroku: execute_step(note, step, ai_generator=gen)
  → notatki dostają `_toolkit_collection`, więc kroki TTS/słownika zapisują media tylko do profilu ze startu
  → zapis i routing jak wyżej (save_detached_notes)

Przyciski workflowów w edytorze:
  → editor_ui.on_editor_buttons_init() dodaje po jednym przycisku na każdy workflow z `editor_button=true` i niepustymi `steps` (przed przyciskiem AI)
  → workflow.run_workflow_editor(editor, workflow)
      → wspólny guard zatrzymuje przebieg, jeśli AI/TTS/słownik/workflow już działa na tym edytorze
      → saveNow → notatka jest łapana RAZ na starcie — wszystkie kroki działają na niej,
        więc przełączenie karty w edytorze w trakcie nie miesza danych między notatkami
      → jeden FieldGenerator per przebieg (cache providerów między krokami AI, brak współdzielenia między oknami)
      → sekwencyjnie wykonuje kroki: execute_step(note, step, ai_generator=gen) (każdy w tle; update_note pomijany dla note.id == 0);
        wewnątrz kroku TTS pliki audio są generowane równolegle (tts.processor.process_single_note → ThreadPoolExecutor)
      → po KAŻDYM kroku scala i odświeża edytor przed kolejnym saveNow; po ostatnim tylko zwalnia guard i pokazuje podsumowanie
```

## Konfiguracja

Konfiguracja edytowalna przez **Narzędzia → Anki Toolkit → Ustawienia…** (grupa „Tworzenie kart”):
- Strona **Workflowy** (osobna pozycja paska bocznego) — lista nazwanych workflowów (nazwa, flaga przycisku edytora, kroki z parametrami) + widoczność wbudowanych sekcji menu PPM (`context_menu`)
- Zakładka **AI Generator → Prompty** — dwupanelowy edytor: lista typ notatki/zadanie po lewej, edytor (nazwa zadania, target, dostawca, model, temperatura, prompt) po prawej; temperatura per prompt z wartością specjalną „— domyślna dostawcy" (dziedziczenie z karty dostawcy); model jest edytowalnym comboboxem z pobieraniem listy z API i filtrowaniem po dowolnym fragmencie nazwy; typ notatki i pole docelowe to edytowalne comboboxy z danymi z kolekcji, przycisk „Wstaw pole ▾" wstawia `{{pole}}` w pozycji kursora, przycisk „Wstaw warunek ▾" wstawia szkielet `{% if pole %}…{% else %}…{% endif %}` (zaznaczony tekst trafia do gałęzi „if"), a walidacja na żywo ostrzega o nieistniejącym typie notatki, polu docelowym i nieznanych `{{polach}}` w prompcie (targety wcześniejszych zadań tego typu notatki są uznawane za znane) oraz o błędach struktury bloków `{% if %}` (niedomknięty/osierocony/podwójny else/zagnieżdżony — `template_engine.template_structure_problems()`, czysta funkcja działająca bez kolekcji)
- Zakładka **AI Generator → Dostawcy** — sekcja Podstawowe zawiera etykietę przycisku i `skip_tags`; lista dostawców (✓ = gotowy) z formularzem: klucz API, model domyślny, fallback, temperatura, limity RPM/równoległości; reasoning dla OpenAI, OpenRouter i Codex CLI; ścieżka binarki, limit czasu i status logowania dla dostawców CLI. `max_tokens` ustawia się tylko w `config.json`. Sekcja Zaawansowane zawiera limity batcha, równoległość, retry, timeout i budżet OpenAI Batch.

Zmiana kluczy API i promptów **nie wymaga restartu Anki** — każde uruchomienie generowania tworzy świeży `FieldGenerator(get_config())`, więc kolejne użycie czyta aktualną konfigurację.

### Sekcja `ai_generator` w config.json (szablon domyślny)

```json
{
  "button_label": "AI",
  "skip_tags": ["skip-ai"],
  "batch_limit": 3,
  "batch_sleep": 1.0,
  "parallel_requests": 3,
  "max_retries": 3,
  "request_timeout": 30,
  "openai_batch_token_budget": 1500000,
  "providers": {
    "openai":     {"api_key": "...", "model": "gpt-4o", "temperature": 0.2, "reasoning_effort": "medium", "fallback_model": "", "cached_models": []},
    "anthropic":  {"api_key": "...", "model": "claude-haiku-4-5-20251001", "temperature": 0.2, "max_tokens": 2048, "fallback_model": "", "cached_models": []},
    "openrouter": {"api_key": "...", "model": "openai/gpt-oss-120b:free", "temperature": 0.2, "reasoning_effort": "medium", "fallback_model": "", "cached_models": [], "rpm": 20, "max_concurrent": 1, "rate_limit_free_only": true},
    "codex_cli": {"api_key": "", "binary_path": "", "codex_home": "", "model": "gpt-5.4-mini", "reasoning_effort": "low", "cli_timeout": 180, "fallback_model": "", "cached_models": []},
    "claude_cli": {"api_key": "", "binary_path": "", "system_prompt": "", "model": "haiku", "cli_timeout": 180, "fallback_model": "", "cached_models": []}
  },
  "note_types": {
    "NazwaTypuNotatki": {
      "klucz": {
        "target": "nazwa_pola_w_karcie",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "fallback_provider": "openrouter",
        "fallback_model": "openai/gpt-oss-120b:free",
        "prompt": "Prompt z {{ang}} i {{pol}}"
      }
    }
  }
}
```

- `skip_tags` — lista tagów wykluczających (tablica stringów); notatka z dowolnym z tych tagów jest pomijana w całości przez `process_note` (zwraca `{}`), bez żadnych wywołań API ani aktualizacji; konfigurowalny przez UI jako pole tekstowe z tagami oddzielonymi przecinkami
- `batch_limit` — liczba kart w jednej grupie; po każdej grupie następuje przerwa `batch_sleep` sekund; przetwarzane są **wszystkie** zaznaczone karty
- `batch_sleep` — pauza między grupami kart (unikanie rate limitów API)
- `parallel_requests` — liczba notatek przetwarzanych równolegle w batchu przeglądarki; domyślnie `3`
- `max_retries` — liczba prób przy HTTP 429/5xx oraz błędach połączenia/timeoutach, przekazywana do `BaseProvider` przez `get_provider()` i `field_generator._resolve_provider()`; domyślnie `3`
- `request_timeout` — timeout urlopen w `common.http.post_json()` (delegowane z `BaseProvider._post()`); domyślnie `30` sekund
- `openai_batch_token_budget` — maksymalny szacowany budżet tokenów batcha OpenAI i własnych batchy w locie; domyślnie `1_500_000`
- `providers.<name>.rpm` — limit żądań na minutę dla dostawcy; żądania rozkładane równomiernie (`60/rpm` s odstępu), więc batch nie burstuje; `0`/brak = bez limitu. OpenRouter domyślnie `20`
- `providers.<name>.max_concurrent` — maks. równoległych żądań do dostawcy (semafor); `0`/brak = bez limitu; darmowe API zwykle wymagają `1`
- `providers.openrouter.rate_limit_free_only` — gdy `true` (domyślnie dla OpenRoutera), limit dotyczy tylko modeli z `:free` w nazwie; gdy `false`, wszystkich żądań. Pole istnieje tylko dla OpenRoutera; inni dostawcy zawsze dławią wszystko.
- `providers.openai.reasoning_effort` / `providers.openrouter.reasoning_effort` — dropdown z wartościami `none/minimal/low/medium/high/xhigh`; wysyłany tylko dla modeli OpenAI reasoning (`o1/o3/o4`, `gpt-5+`); dla tych modeli nie wysyłane `temperature`; fallback automatyczny przy HTTP 400
- Bez globalnego cache generatora: każde uruchomienie tworzy świeży `FieldGenerator(get_config())` (edytor per klik, workflow per przebieg, batch per notatka) — konfiguracja działa od razu po zapisie ustawień, bez resetu
- Każdy prompt zapisuje `provider` i `model`; starsze wpisy bez `model` używają `providers.<provider>.model`. Instancje providerów są cache'owane per `(provider, model, temperature)` w obrębie jednej instancji `FieldGenerator`.
- `note_types.<nt>.<klucz>.temperature` (opcjonalne) — temperatura per prompt; brak klucza = `providers.<provider>.temperature` (temperatura domyślna dostawcy). Fallback promptu używa tej samej per-prompt temperatury (własność zadania, nie modelu). UI: Prompty → QDoubleSpinBox „Temperatura" z wartością specjalną „— domyślna dostawcy" (minimum -0.05; wartość ujemna = dziedzicz, klucz nie jest zapisywany)
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
```

Fallback używa tego samego promptu (już wyrenderowanego), ale nowa instancja providera z innym modelem/kluczem.

## Rate limiter per dostawca (`RateLimiter`)

Klasa `RateLimiter` w `field_generator.py` — singleton z **jednym kubełkiem (bucket) per dostawca**. Kubełek wymusza:

- **Równomierne tempo (RPM)** — odstęp `60/rpm` sekund między *startami* żądań, więc batch nie burstuje (kluczowe dla modeli `:free` OpenRoutera: 20 RPM). `rpm<=0` = bez limitu tempa.
- **Limit jednoczesności** — semafor `max_concurrent`; `max_concurrent<=0` = bez limitu.
- **Zakres `free_only`** — gdy `True`, kubełek dotyczy **tylko** modeli z `:free` w nazwie (warianty darmowe OpenRoutera); płatne modele tego dostawcy przechodzą bez dławienia. Gdy `False`, limit obejmuje **wszystkie** żądania dostawcy (darmowy klucz API dławi cały klucz, nie pojedyncze modele).

Szczegóły:
- **Singleton** — jeden per proces; limity są per API key, więc bucket per nazwa dostawcy
- `configure(provider, rpm, max_concurrent, free_only)` — wołane w `FieldGenerator._configure_rate_limit()` podczas rozwiązywania dostawcy; czyta per-provider `rpm`/`max_concurrent`/`rate_limit_free_only`.
- `slot(provider, model)` — context manager owijający każde `provider.call_api()` (główne + fallback); no-op gdy brak limitu dla danego dostawcy/modelu
- Pacing trzyma lock kubełka przez `time.sleep`, więc starty pozostają równomiernie rozłożone nawet przy wielu wątkach batcha
- **TPM (tokeny/min) nie jest egzekwowane** — liczba tokenów znana dopiero po odpowiedzi; sporadyczne przekroczenia łapie backoff 429 w `common/http.post_json`

UI: pola **Limit RPM** i **Maks. równoległych** są na karcie każdego dostawcy (`settings/ai_generator_tab.py`); checkbox **„Limit tylko dla modeli :free"** tylko dla OpenRoutera.

## Dodanie nowego dostawcy AI

1. Provider zgodny z OpenAI Chat Completions: dziedzicz po `OpenAICompatProvider` w `providers/__init__.py`, ustaw tylko `API_URL` i `LABEL`. Provider o innym formacie: utwórz `providers/moj_provider.py`, dziedzicz po `BaseProvider` i zaimplementuj `call_api()` (możesz wykorzystać `_parse_chat_completion()` / `_parse_messages()` z bazy)
2. Dodaj klasę do `PROVIDERS` i etykietę do `PROVIDER_LABELS` w `providers/__init__.py` — `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` jest wyliczane z `PROVIDERS`, a `settings/prompts_tab.py` iteruje po `PROVIDER_LABELS`
3. Dla przycisku **Pobierz** dodaj gałąź w `model_discovery.fetch_models()`, a sekcję dostawcy w szablonie `config.json`

### Format odpowiedzi API

| Provider | Format żądania | Pole z odpowiedzią |
|---|---|---|
| OpenAI / OpenRouter | `{"messages": [...], "reasoning_effort": opcjonalnie}` | `choices[0].message.content` |
| Anthropic | `{"messages": [...], "max_tokens": self.max_tokens or 2048}` | `content[0].text` |
| Codex CLI / Claude CLI | prompt przez stdin lokalnej binarki | plik `-o` / pole `result` JSON-a |

`max_tokens` dla Anthropic (wymagany przez API) pochodzi z `provider_cfg.get("max_tokens")` → `BaseProvider.max_tokens`. Domyślnie `2048`. Konfigurowalny per-provider w `config.json`.

Providery zgodne z OpenAI Chat Completions współdzielą `OpenAICompatProvider.call_api()` (w `base.py`) i helpery z `providers/openai_compat.py`. Jeśli nazwa modelu wygląda jak OpenAI reasoning, `temperature` nie jest wysyłane. `reasoning_effort` jest wysyłane przez `openai` i `openrouter` (tylko dla rozpoznanych modeli reasoning). Jeśli model nie obsługuje `reasoning_effort` (HTTP 400 wspominający ten parametr), `_post_with_reasoning_fallback()` automatycznie ponawia żądanie bez niego.

Rozbiór odpowiedzi jest wspólny: `BaseProvider._parse_chat_completion()` dla formatu OpenAI (`choices[0].message.content`, z `extract_message_content` dla string/list) i `_parse_messages()` dla formatu Anthropic (pierwszy blok `type=="text"`). Wszystkie walidują strukturę odpowiedzi przed dostępem — sprawdzają niepustość tablic i istnienie kluczy. Błędy parsowania są logowane przez `self.logger` i zapisywane do `self.last_error`. Retry (3 próby, exponential backoff dla HTTP 429/5xx oraz błędów połączenia/timeoutów) jest zaimplementowany w `common.http.post_json()` — `BaseProvider._post(url, data, headers)` serializuje `data` do JSON i deleguje; `self.last_error` jest ustawiane z zwróconego stringa błędu.

## Zależności

- Stdlib: `json`, `re`, `logging`
- Anki API: `mw.addonManager.getConfig`, `mw.col.get_note`, `mw.col.update_note`, `mw.taskman.run_in_background`, `mw.taskman.run_on_main`, `mw.progress.start/update/finish/want_cancel` (natywny pasek batcha)
- Własne: `common.ADDON_NAME`, `common.clean_html_normalized`, `common.safe_str`, `common.http.post_json` (POST z retry)
- Batch używa natywnego paska `mw.progress` (nie `QProgressDialog`) — trzyma Anki „busy", więc automatyczny backup/sync się odkłada i nie zasłania przycisku Anuluj
- Brak pip packages

## Uwagi implementacyjne

- `BaseProvider.__init__` przyjmuje `max_retries`, `timeout`, `max_tokens`, `reasoning_effort` — przekazywane przez `get_provider()` z wartości czytanych przez `_resolve_provider()` z `self._config` oraz z `provider_cfg`
- `openai_compat.add_temperature_if_supported()` i `add_reasoning_effort_if_supported()` są używane przez `openai` i `openrouter` (`OpenAICompatProvider.call_api()`)
- `BaseProvider._post(url, data, headers)` serializuje `data` do JSON i deleguje do `common.http.post_json()` z `self.max_retries` i `self.timeout`; ustawia `self.last_error` z zwróconego stringa błędu (lub `None` przy sukcesie)
- `BaseProvider._post_with_reasoning_fallback()` opakowuje `_post()`: jeśli żądanie zwróci błąd zawierający `"reasoning_effort"`, usuwa ten parametr z body i ponawia
- `field_generator.py` nie zawiera żadnych wywołań `showWarning` ani Qt UI — błędy są logowane przez `logger` i ustawiane w `self.last_error`; ewentualne ostrzeżenia Qt są wywoływane przez `editor_ui`/`browser_ui` w głównym wątku
- Przycisk AI w edytorze działa asynchronicznie (`run_in_background`) — UI nie zamarza podczas wywołania API; sekwencja: `saveNow(start)` → `start()` czyta `editor.note` → `run_in_background(task)` → `on_done` → `saveNow(apply)` → `loadNote()`
- `common.editor_operation` zapisuje `(token, label)` na instancji edytora. AI, TTS, słownik i workflow współdzielą ten sam guard; inne okno edytora ma niezależny stan. Guard jest zwalniany tokenem dopiero po zastosowaniu wyniku, a nie po samym zakończeniu workera.
- `editor.saveNow(start)` na początku `_on_generate_editor` — synchronizuje webview → `editor.note` PRZED startem zadania tła; `note = editor.note` jest czytany wewnątrz callbacku `start()`, dzięki czemu sprawdzenie pustości pól widzi rzeczywisty stan widoczny użytkownikowi
- `fields_map` budowany przez `common.clean_html_normalized()` — pola notatki ze znacznikami HTML (`<div>`, `<br>`, `&nbsp;`) są oczyszczane przed wstawieniem do promptu; wyniki AI trafiają do karty surowo (bez strippowania HTML — AI powinno zwracać czysty tekst)
- `process_note` zwraca `dict[str, str]` (nie `bool`) — pisze też wprost do notatki, którą dostała, dlatego edytor podaje jej kopię z `detach_note()`; browser_ui używa go jako truthy check, a notatki zmienione w batchu są zapisywane atomowo przez `CollectionOp(parent=browser, op=lambda col: col.update_notes(changed_notes))` (jeden krok undo), a nie per-note `mw.col.update_note`
- `FieldGenerator.last_error` przechowuje ostatni błąd providera/API; editor_ui pokazuje go także wtedy, gdy część pól się udała (wcześniej częściowa awaria wyglądała na czysty sukces), a browser_ui liczy błąd niezależnie od tego, czy notatka się zmieniła
- `editor.saveNow(apply)` synchronizuje webview przed `merge_editor_note()`. Zmiana dowolnego pola unieważnia wyniki bieżącego kroku (pola mogą być wejściami promptu), a nazwy pominiętych pól wynikowych trafiają do tooltipa. Helper kontroluje tożsamość kolekcji i schemat; po przełączeniu edytora wczytuje świeżą notatkę. Zapis istniejącej notatki powiadamia Anki przez `on_op_finished`; webview odświeża się po każdym kroku. Nie wolno scalać po błędzie saveNow ani kontynuować workflow po błędzie zapisu.
- Edytorowe ścieżki AI/TTS/słownika/workflow dzielą jeden wzorzec: `detach_note()` przed startem workera, `merge_editor_note()` po `saveNow`. Worker nigdy nie mutuje `editor.note` — `FieldGenerator.process_note`, `process_single_note` i `process_note_group` piszą do notatki, którą dostaną
- Pola konfiguracyjne note-type (`target`, `provider`, `prompt`) są normalizowane przez `safe_str()` z `common.text` przed użyciem; wartości liczbowe (`batch_sleep`, `temperature`) pochodzą z widgetów Qt (zakresy wymuszone w UI) lub z `.get()` z wartością domyślną
- Throttling: paczki na poziomie przeglądarki (sleep co `batch_limit` notatek) + per-dostawca tempo/jednoczesność przez `RateLimiter.slot()` w `field_generator` (patrz „Rate limiter per dostawca")
