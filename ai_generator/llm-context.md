# LLM Context — ai_generator

## Co robi

Generuje treść pól kart przez AI. Każde pole karty może mieć własnego dostawcę i prompt. Działa w edytorze (główny przycisk workflow + pomocniczy przycisk AI) i przeglądarce (batch dla zaznaczonych notatek). Pomija pola, które już mają treść.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Re-eksport hooków — importuje z `editor_ui`, `browser_ui`, `_generator` |
| `_generator.py` | Zarządzanie stanem generatora — `get_generator()`, `reset_generator()`, config-aware cache; używa `common.ADDON_NAME` |
| `editor_ui.py` | UI edytora — najpierw przycisk workflow (jeśli włączony), potem przycisk AI; `_GENERATING` guard zapobiega podwójnemu kliknięciu AI; `saveNow(start)` zapewnia świeży stan note przed zadaniem |
| `browser_ui.py` | UI przeglądarki — batch z QProgressDialog, cancel_flag |
| `field_generator.py` | Logika generowania — niezależna od UI, cache providerów; używa `common.clean_html_normalized()`, `common.safe_str()` |
| `template_engine.py` | Silnik szablonów: `{{pole}}` i `{% if %}...{% endif %}`; `template_structure_problems()` — czysta walidacja struktury bloków używana przez edytor promptów |
| `stats.py` | Lokalne statystyki użycia — liczniki per dzień (requesty, błędy, tokeny wej./wyj., pola, notatki) w `usage_stats.json`; `get_stats(days=None)` agreguje zakres; thread-safe |
| `providers/__init__.py` | Rejestr `PROVIDERS`/`PROVIDER_LABELS` + fabryka `get_provider()`; definiuje też 4 cienkie klasy zgodne z OpenAI (`OpenAIProvider`, `OpenRouterProvider`, `CometAPIProvider`, `MistralProvider`) dziedziczące po `OpenAICompatProvider` — różnią się tylko `API_URL`, `LABEL` i (Mistral) `SUPPORTS_REASONING_EFFORT = False` |
| `providers/base.py` | ABC `BaseProvider` — interfejs + `_request_with_retry()` + `_request_with_reasoning_fallback()` + wspólne parsery odpowiedzi `_parse_chat_completion()` (format OpenAI choices→message→content) i `_parse_messages()` (format Anthropic, pierwszy blok `type=="text"`); klasa `OpenAICompatProvider` z gotowym `call_api()` dla endpointów Bearer-auth Chat Completions; używa `common.http.RETRYABLE_STATUS_CODES` |
| `providers/openai_compat.py` | Helpery dla providerów zgodnych z Chat Completions: wykrywanie modeli OpenAI reasoning, pomijanie `temperature`, parsowanie `message.content` string/list, `is_reasoning_effort_unsupported_error()` |
| `providers/anthropic.py` | Anthropic (Messages API, inny format niż OpenAI); `call_api()` deleguje rozbiór do `BaseProvider._parse_messages()` |
| `providers/google.py` | Google Gemini (generateContent API — własny rozbiór `candidates[0].content.parts`) |
| `providers/opencode_go.py` | OpenCode Go — Chat Completions dla większości modeli (`_parse_chat_completion`), Anthropic Messages dla MiniMax/Qwen3.x (`_parse_messages`); auto-detect na podstawie nazwy modelu; reasoning jako wolny string; `User-Agent` header (Cloudflare) |
| `providers/model_discovery.py` | Pobieranie dostępnych modeli z API każdego providera + dispatcher `fetch_models()`; bliźniacze endpointy `{"data":[{"id":...}]}` (openai/mistral/anthropic/cometapi/opencode_go) idą przez wspólny `_fetch_simple()` z predykatem `keep`; Google i OpenRouter mają własne fetchery |
| `workflow.py` | Workflow "Generuj fiszkę" — sekwencyjne uruchamianie AI → Dict → TTS na pojedynczej notatce w edytorze; guard `_RUNNING` blokuje podwójne odpalenie; używa `common.ADDON_NAME` |

## Przepływ danych

```
Kliknięcie przycisku (edytor)
  → editor_ui._on_generate_editor()
  → sprawdź _GENERATING — jeśli ten edytor już generuje: tooltip "Generowanie już trwa..." i return
  → dodaj editor_id do _GENERATING
  → _generator.get_generator()                   # config-aware: porównuje z _cached_config, tworzy nowy gdy config się zmienił
  → editor.saveNow(start)                        # synchronizuje webview → editor.note PRZED zadaniem
      → start() (callback na głównym wątku po saveNow):
          → note = editor.note                   # świeży stan po synchronizacji
          → mw.taskman.run_in_background(task)   # nie blokuje UI — API calls w tle
              → FieldGenerator.process_note(note) → dict[str, str]
                  → dla każdego pola w config note_types:
                      → pomiń jeśli pole niepuste
                      → _resolve_provider(provider_name)   # cache, tworzy raz; wczytuje max_retries i request_timeout z config
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

Batch w przeglądarce (menu kontekstowe → Generuj pola):
  → browser_ui._on_generate_browser()
  → QProgressDialog z przyciskiem Anuluj
  → mw.taskman.run_in_background(task)         # nie blokuje UI
      → dla każdej notatki:
          → jeśli i % batch_limit == 0: sleep(batch_sleep)  # pauza między grupami
          → FieldGenerator.process_note(note)
          → mw.col.update_note(note)
  → on_done (główny wątek): progress.close(), mw.reset(), tooltip z podsumowaniem i ostatnim błędem API jeśli wystąpił

Przycisk workflow w edytorze:
  → editor_ui.on_editor_buttons_init() dodaje go przed przyciskiem AI, jeśli `workflow.enabled=true` i `workflow.steps` nie jest puste
  → workflow.run_workflow_editor(editor)
      → jeśli editor_id jest w `_RUNNING`: tooltip "Workflow już trwa..." i return
      → saveNow → notatka jest łapana RAZ na starcie — wszystkie kroki działają na niej,
        więc przełączenie karty w edytorze w trakcie nie miesza danych między notatkami
      → sekwencyjnie wykonuje kroki z configu: AI, dictionary, TTS (każdy w tle; update_note pomijany dla note.id == 0);
        wewnątrz kroku TTS pliki audio są generowane równolegle (tts.processor.process_single_note → ThreadPoolExecutor)
      → po ostatnim kroku usuwa editor_id z `_RUNNING`, wywołuje `editor.loadNote()` (tylko gdy edytor nadal pokazuje tę notatkę) i pokazuje jedno podsumowanie
```

## Konfiguracja

Konfiguracja edytowalna przez **Narzędzia → Anki Toolkit → Ustawienia...**:
- Zakładka **AI Generator → Workflow** — kolejność kroków i etykieta przycisku edytora (`Generuj fiszkę`)
- Zakładka **AI Generator → Prompty** — dwupanelowy edytor: lista typ notatki/zadanie po lewej, edytor (nazwa zadania, target, dostawca, prompt) po prawej; typ notatki i pole docelowe to edytowalne comboboxy z danymi z kolekcji, przycisk „Wstaw pole ▾" wstawia `{{pole}}` w pozycji kursora, przycisk „Wstaw warunek ▾" wstawia szkielet `{% if pole %}…{% else %}…{% endif %}` (zaznaczony tekst trafia do gałęzi „if"), a walidacja na żywo ostrzega o nieistniejącym typie notatki, polu docelowym i nieznanych `{{polach}}` w prompcie (targety wcześniejszych zadań tego typu notatki są uznawane za znane) oraz o błędach struktury bloków `{% if %}` (niedomknięty/osierocony/podwójny else/zagnieżdżony — `template_engine.template_structure_problems()`, czysta funkcja działająca bez kolekcji)
- Zakładka **AI Generator → Dostawcy** — karty dostawców AI, klucze API, modele, temperatura, reasoning/max tokens; sekcja **Zaawansowane** zawiera batch/retry/request timeout/skip tags

Zmiana kluczy API i promptów **nie wymaga restartu Anki** — po zapisaniu ustawień generator jest resetowany i przy kolejnym użyciu pobiera świeżą konfigurację.

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
    "openai":     {"api_key": "...", "model": "gpt-4o", "temperature": 0.2, "reasoning_effort": "medium"},
    "google":     {"api_key": "...", "model": "gemini-2.0-flash", "temperature": 0.2},
    "anthropic":  {"api_key": "...", "model": "claude-3-5-haiku-20241022", "temperature": 0.2, "max_tokens": 2048},
    "openrouter": {"api_key": "...", "model": "anthropic/claude-3.5-haiku", "temperature": 0.2, "reasoning_effort": "medium"},
    "cometapi":   {"api_key": "...", "model": "grok-4-1-fast-non-reasoning", "temperature": 0.2, "reasoning_effort": "medium"},
    "mistral":    {"api_key": "...", "model": "mistral-small-latest", "temperature": 0.2},
    "opencode_go": {"api_key": "...", "model": "deepseek-v4-pro", "temperature": 0.6, "reasoning_effort": "max"}
  },
  "note_types": {
    "NazwaTypuNotatki": {
      "klucz": {
        "target": "nazwa_pola_w_karcie",
        "provider": "openai",
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
- `request_timeout` — timeout urlopen w `BaseProvider._request_with_retry()`; domyślnie `30` sekund
- `providers.openai.reasoning_effort` / `providers.cometapi.reasoning_effort` / `providers.openrouter.reasoning_effort` — dropdown z wartościami `none/minimal/low/medium/high/xhigh`; wysyłany tylko dla modeli OpenAI reasoning (`o1/o3/o4`, `gpt-5+`); dla tych modeli nie wysyłane `temperature`; fallback automatyczny przy HTTP 400
- `providers.opencode_go.reasoning_effort` — wolny tekst (QLineEdit w UI); wartości per model: `max` dla DeepSeek V4 Pro, inne modele mają inne wartości lub nie obsługują; puste = nie wysyłane; fallback automatyczny przy HTTP 400; `opencode_go` wymaga `User-Agent` header (Cloudflare blokuje brak UA); auto-detect formatu API: Chat Completions dla GLM/Kimi/DeepSeek/MiMo, Anthropic Messages dla MiniMax M2.5/M2.7/Qwen3.5/3.6 Plus
- Generator jest config-aware: porównuje bieżący config z `_cached_config` — jeśli config się zmienił, tworzy nowy generator z nowymi providerami; reset też wywoływany jawnie przez `settings/_reload_module_configs()` po zapisaniu ustawień
- Pola generowane są w kolejności kluczy w `note_types`; pole może referencjonować wynik poprzedniego pola przez `{{nazwa}}` w prompcie

## Silnik szablonów

```
{{ang}}                          → wartość pola "ang" z karty
{% if def %}...{% endif %}       → renderuje blok tylko gdy pole "def" niepuste
{% if def %}...{% else %}...{% endif %}  → z fallbackiem
```

**Ograniczenie:** zagnieżdżone `{% if %}` wewnątrz `{% if %}` nie są obsługiwane — regex dopasowuje pierwszy napotkany `{% endif %}`. Rekurencja z limitem `MAX_DEPTH = 50` dotyczy tylko renderowania zawartości bloków.

## Dodanie nowego dostawcy AI

1. Provider zgodny z OpenAI Chat Completions: dziedzicz po `OpenAICompatProvider` w `providers/__init__.py`, ustaw tylko `API_URL` i `LABEL` (opcjonalnie `SUPPORTS_REASONING_EFFORT`). Provider o innym formacie: utwórz `providers/moj_provider.py`, dziedzicz po `BaseProvider` i zaimplementuj `call_api()` (możesz wykorzystać `_parse_chat_completion()` / `_parse_messages()` z bazy)
2. Dodaj klasę do `PROVIDERS` w `providers/__init__.py`
3. Dodaj sekcję w `config.json` → `ai_generator.providers.moj_provider`
4. Dodaj nazwę do listy `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` i `settings/prompts_tab.py`

### Format odpowiedzi API

| Provider | Format żądania | Pole z odpowiedzią |
|---|---|---|
| OpenAI / CometAPI / OpenRouter | `{"messages": [...], "reasoning_effort": opcjonalnie}` | `choices[0].message.content` |
| Mistral | `{"messages": [...]}` | `choices[0].message.content` |
| Anthropic | `{"messages": [...], "max_tokens": self.max_tokens or 2048}` | `content[0].text` |
| Google | `{"contents": [{"parts": [{"text": ...}]}]}` | `candidates[0].content.parts[0].text` |
| OpenCode Go (chat) | `{"messages": [...], "temperature": ..., "reasoning_effort": opcjonalnie}` | `choices[0].message.content` |
| OpenCode Go (messages) | `{"messages": [...], "max_tokens": ..., "temperature": ...}` | `content[0].text` |

`max_tokens` dla Anthropic i OpenCode Go Messages (wymagany przez API) pochodzi z `provider_cfg.get("max_tokens")` → `BaseProvider.max_tokens`. Domyślnie `2048`. Konfigurowalny per-provider w `config.json`.

Providery zgodne z OpenAI Chat Completions współdzielą `OpenAICompatProvider.call_api()` (w `base.py`) i helpery z `providers/openai_compat.py`. Jeśli nazwa modelu wygląda jak OpenAI reasoning, `temperature` nie jest wysyłane. `reasoning_effort` jest wysyłane przez `openai`, `cometapi` i `openrouter` (tylko dla rozpoznanych modeli reasoning); `mistral` go nie wysyła (`SUPPORTS_REASONING_EFFORT = False`); `opencode_go` wysyła `reasoning_effort` bezpośrednio jako wolny string jeśli ustawiony (bez sprawdzania nazwy modelu). Jeśli model nie obsługuje `reasoning_effort` (HTTP 400 wspominający ten parametr), `_request_with_reasoning_fallback()` automatycznie ponawia żądanie bez niego.

Rozbiór odpowiedzi jest wspólny: `BaseProvider._parse_chat_completion()` dla formatu OpenAI (`choices[0].message.content`, z `extract_message_content` dla string/list) i `_parse_messages()` dla formatu Anthropic (pierwszy blok `type=="text"`); Google ma własny rozbiór `candidates`. Wszystkie walidują strukturę odpowiedzi przed dostępem — sprawdzają niepustość tablic i istnienie kluczy. Błędy parsowania są logowane przez `self.logger` i zapisywane do `self.last_error`. `BaseProvider._request_with_retry()` implementuje retry (3 próby, exponential backoff) dla HTTP 429/5xx oraz błędów połączenia/timeoutów. Klucz API Google jest wysyłany w nagłówku `x-goog-api-key` (nie w URL-u — URL-e trafiają do logów).

## Zależności

- Stdlib: `urllib.request`, `json`, `re`, `time`, `logging`
- Anki API: `mw.addonManager.getConfig`, `mw.col.get_note`, `mw.col.update_note`, `mw.taskman.run_in_background`, `mw.taskman.run_on_main`
- Własne: `common.ADDON_NAME`, `common.clean_html_normalized`, `common.safe_str`, `common.http.RETRYABLE_STATUS_CODES`
- Qt: `QProgressDialog` (pasek postępu z przyciskiem Anuluj w trybie batch)
- Brak pip packages

## Uwagi implementacyjne

- `BaseProvider.__init__` przyjmuje `max_retries`, `timeout`, `max_tokens`, `reasoning_effort` — przekazywane przez `get_provider()` z wartości czytanych przez `_resolve_provider()` z `self._config` oraz z `provider_cfg`
- `openai_compat.add_temperature_if_supported()` jest używany przez `openai`, `cometapi`, `openrouter`, `mistral`
- `openai_compat.add_reasoning_effort_if_supported()` jest używany przez `openai`, `cometapi`, `openrouter`; `mistral` go nie używa; `opencode_go` nie używa — wysyła `reasoning_effort` bezpośrednio jako wolny string
- `BaseProvider._request_with_retry()` używa `self.max_retries` i `self.timeout` zamiast stałych modułowych
- `BaseProvider._request_with_reasoning_fallback()` opakowuje `_request_with_retry()`: jeśli żądanie zwróci błąd zawierający `"reasoning_effort"`, usuwa ten parametr z body i ponawia; używany też przez `opencode_go`
- Wszystkie `showWarning` w `field_generator.py` są wywoływane przez `mw.taskman.run_on_main` — bezpieczne wywołanie Qt z wątku w tle
- Przycisk AI w edytorze działa asynchronicznie (`run_in_background`) — UI nie zamarza podczas wywołania API; sekwencja: `saveNow(start)` → `start()` czyta `editor.note` → `run_in_background(task)` → `on_done` → `saveNow(apply)` → `loadNote()`
- `_GENERATING: set[int]` w `editor_ui` — zbiór ID aktywnych edytorów dla przycisku AI; zapobiega wyścigowi podwójnego kliknięcia (drugie kliknięcie podczas trwającego generowania pokazuje tooltip i jest ignorowane); ID jest usuwany w `on_done` niezależnie od wyniku
- `_RUNNING: set[int]` w `workflow.py` — analogiczna ochrona dla przycisku workflow
- `editor.saveNow(start)` na początku `_on_generate_editor` — synchronizuje webview → `editor.note` PRZED startem zadania tła; `note = editor.note` jest czytany wewnątrz callbacku `start()`, dzięki czemu sprawdzenie pustości pól widzi rzeczywisty stan widoczny użytkownikowi
- `fields_map` budowany przez `common.clean_html_normalized()` — pola notatki ze znacznikami HTML (`<div>`, `<br>`, `&nbsp;`) są oczyszczane przed wstawieniem do promptu; wyniki AI trafiają do karty surowo (bez strippowania HTML — AI powinno zwracać czysty tekst)
- `process_note` zwraca `dict[str, str]` (nie `bool`) — editor_ui używa tego dict do bezwarunkowego nadpisania pól AI po `saveNow`; browser_ui używa go jako truthy check przed `mw.col.update_note`
- `FieldGenerator.last_error` przechowuje ostatni błąd providera/API; editor_ui pokazuje go zamiast mylącego "Brak pól do wygenerowania.", a browser_ui dolicza błędy w podsumowaniu batcha
- `editor.saveNow(apply)` w `on_done` synchronizuje stan webview → `editor.note` przed aplikowaniem wyników AI; zachowuje edycje pól których AI nie dotknęło. `apply()` pisze do notatki złapanej na starcie i sprawdza tożsamość (`editor.note is note`) — jeśli użytkownik przełączył kartę w trakcie generowania, wynik jest zapisywany do kolekcji przez `mw.col.update_note()` zamiast do aktualnie wyświetlanej notatki
- `opencode_go` auto-wykrywa format API: modele w `_MESSAGES_FORMAT_MODELS` (minimax-m2.5, minimax-m2.7, qwen3.5-plus, qwen3.6-plus) używają endpointu `/messages`; pozostałe `/chat/completions`; auth zawsze `Bearer`; `User-Agent` header wymagany przez Cloudflare
- Pola konfiguracyjne note-type (`target`, `provider`, `prompt`) są normalizowane przez `safe_str()` z `common.text` przed użyciem; wartości liczbowe (`batch_sleep`, `temperature`) pochodzą z widgetów Qt (zakresy wymuszone w UI) lub z `.get()` z wartością domyślną
- Throttling jest wyłącznie na poziomie przeglądarki (sleep co `batch_limit` notatek) — `field_generator` nie ma własnych sleep'ów między polami
- **Statystyki użycia**: każdy `call_api()` wywołuje `self._capture_usage(res_data)` (BaseProvider) — wyciąga tokeny z `usage.prompt/completion_tokens` (OpenAI-compat), `usage.input/output_tokens` (Anthropic) lub `usageMetadata` (Gemini) do `provider.last_usage`; `field_generator.process_note()` rejestruje przez `stats.record_request()` (per provider/model) i `stats.record_note()`; dashboard w **Ustawienia → Statystyki** z wyborem zakresu (dziś/7/30/365 dni/wszystko/własny zakres dat od–do — `get_stats(start=..., end=...)`, granice inclusive)
