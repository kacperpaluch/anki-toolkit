# AI Generator — generowanie pól kart przez AI

Automatycznie wypełnia pola kart Anki przez API modeli językowych. Obsługuje wielu dostawców AI — każde pole karty może korzystać z innego modelu.

## Jak używać

### Edytor kart
Główna akcja w toolbarze to zwykle **Generuj fiszkę** z workflow AI → Słownik → TTS. Przycisk **AI** zostaje jako akcja pomocnicza: generuje wszystkie skonfigurowane puste pola AI dla aktualnie otwartej karty.

Dodatkowo: **PPM na polu w edytorze** → „Wygeneruj `pole` przez AI" (pole puste) lub „Regeneruj `pole` przez AI" (pole pełne — nadpisuje). Opcja pojawia się tylko na polach które mają skonfigurowany prompt dla bieżącego typu notatki.

Działa asynchronicznie — Anki nie zamarza podczas oczekiwania na API. W międzyczasie możesz swobodnie edytować inne pola. Po zakończeniu:
- Edytor odświeża się automatycznie po zakończeniu generowania
- **Pola docelowe AI** są zawsze nadpisywane wynikiem — kliknięcie przycisku AI to wyraźna intencja wypełnienia tych pól
- **Pola których AI nie dotyka** (np. wpisujesz coś w polu `pol` podczas gdy AI generuje `def`) są zachowane — `saveNow` synchronizuje je przed odświeżeniem
- Pojawia się tooltip z błędem API, jeśli dostawca zwróci błąd; **"Brak pól do wygenerowania."** oznacza brak pustych/skonfigurowanych pól do uzupełnienia
- Gdy na tej samej notatce trwa już AI, TTS, pobieranie wymowy albo workflow, kolejna akcja Anki Toolkit jest ignorowana z krótkim komunikatem. Inne okno edytora może pracować równolegle.
- Jeśli w trakcie generowania przełączysz się na inną kartę, wynik trafia do **właściwej notatki** (zapis bezpośrednio do kolekcji) — nie do aktualnie wyświetlanej

### Workflowy

Workflow to nazwana sekwencja kroków (AI / Słownik / TTS / Rozdziel pole). Każdy workflow jest pozycją w menu PPM przeglądarki, a z flagą **„Pokaż jako przycisk w edytorze”** — także przyciskiem w toolbarze edytora. Konfiguracja w **Ustawienia → Workflowy**:
- Dodawaj kroki przyciskami **+ AI**, **+ Słownik**, **+ TTS**, **+ Rozdziel**
- Przy **+ Słownik** otwiera się okno wyboru słowników (checkboxy Diki, Oxford, Cambridge, Longman); krok AI ma wybór pól (wszystkie puste / zablokowane / konkretne)
- Zmieniaj kolejność ▲▼, usuwaj kroki

Przed startem workflow sprawdza, czy wszystkie wymagane moduły są włączone; brakujący moduł zatrzymuje cały przebieg zamiast wykonywać tylko część kroków. W edytorze kroki wykonują się sekwencyjnie w tle; notatka jest łapana raz na starcie workflow — przełączenie karty w trakcie nie miesza danych między notatkami. W przeglądarce workflow przetwarza zaznaczone notatki **równolegle** (kroki w obrębie jednej notatki pozostają sekwencyjne).

Dawny wbudowany pipeline **„Generuj wszystko: puste → TTS → rozdziel → zablokowane”** jest teraz zwykłym, edytowalnym workflowem seedowanym przy migracji starszej konfiguracji.

### Przeglądarka (batch)
Zaznacz notatki → **menu kontekstowe → Anki Toolkit → Generuj pola ▸**.

Submenu zawiera:
- **Wszystkie puste** — generuje wszystkie skonfigurowane puste pola (obecne zachowanie)
- **AI: `def`**, **AI: `cz_mowy`** itd. — generuje tylko wybrane pole docelowe, pomija wypełnione

Pozycje per-pole są spłaszczone po nazwie pola docelowego — notatki różnych typów notatek dostają swój prompt (każdy typ ma osobną konfigurację `note_types`), a notatki bez skonfigurowanego pola są pomijane.

- Pola które już mają treść są **zawsze pomijane** w batchu — generator uzupełnia tylko puste pola.
- Jeśli nie zaznaczysz żadnych notatek, pojawi się krótki tooltip z informacją.
- Praca AI dzieje się w tle. Batch pokazuje **natywny pasek postępu Anki** z licznikiem i przyciskiem **Anuluj** — na czas przetwarzania okno Anki jest zablokowane, dzięki czemu automatyczna kopia zapasowa / synchronizacja nie wyskakuje w środku batcha i nie zasłania przycisku Anuluj.
- Po zakończeniu jeden tooltip z podsumowaniem, np. `"Zaktualizowano: 12"`, `"Zaktualizowano: 8 · przerwano"` albo licznik błędów z ostatnim błędem API.

### Batch API (masowy backfill, ~50% taniej — Anthropic, OpenAI i OpenRouter)

Do jednorazowego lub okresowego wypełniania dużej liczby notatek jest **osobny, tańszy tryb** oparty na Batch API [Anthropic](https://platform.claude.com/docs/en/build-with-claude/batch-processing) i [OpenAI](https://developers.openai.com/api/docs/guides/batch) i [OpenRouter](https://openrouter.ai/docs/batch-quickstart): asynchroniczny (wynik zwykle < 1h, do 24h), **~50% tańszy**. Menu kontekstowe → **Anki Toolkit → Batch API (Anthropic/OpenAI/OpenRouter, tańszy) ▸**:

- **Wyślij zaznaczone — wszystkie pola** / **Batch: `<pole>`** — wysyła puste pola (wszystkie albo wybrane) do Batch API właściwego dostawcy. **Pola już wypełnione są pomijane** (na etapie wysyłki, nie tylko zapisu), więc ponowne uruchomienie na tym samym zaznaczeniu jest bezpieczne — dobierze tylko to, co nadal puste. Pola `anthropic`, `openai` i `openrouter` trafiają każde do swojego batcha; pozostali dostawcy (CometAPI/Mistral/NVIDIA — brak zgodnego endpointu) są pomijani z informacją. Dialog potwierdzenia pokazuje rozbicie zapytań per dostawca/model.
- **Wyślij zaznaczone — wszystkie zablokowane** / **Batch (zablokowane): `<pole>`** — to samo dla pól oflagowanych „Tylko na żądanie" (`manual_only`), które tryb „wszystkie pola" pomija. Pozycje pojawiają się tylko gdy takie pola istnieją w konfiguracji promptów.
- **Sprawdź batche i zastosuj wyniki** — odpytuje gotowe batche i dopisuje wyniki; to samo dzieje się automatycznie i cicho przy każdym otwarciu profilu Anki. Wysyłka, zakończenie batcha i podsumowanie zapisu („Batch: dopisano…") są logowane na INFO — historia w **Ustawienia → Diagnostyka → Logi**, nawet gdy tooltip zdąży zniknąć.

Szczegóły:
- Trafienie wyniku w pole jest **deterministyczne** — mapa `custom_id → (notatka, pole)` zapisywana jest w `user_files/ai_batches.json` (przeżywa restart). Wynik wpisywany jest **tylko do pól nadal pustych** (nie nadpisuje edycji z okresu oczekiwania); usunięta notatka / zmienione pole → wynik pomijany.
- Wspólny rdzeń (wybór pól, mapa, persystencja, zapis) jest niezależny od dostawcy; różnice protokołów są w cienkich backendach: **Anthropic** wysyła zapytania inline i pobiera wynik z `results_url`; **OpenAI** uploaduje plik JSONL (Files API) i pobiera plik wynikowy, a jego batch wymaga jednego modelu, więc zapytania OpenAI są grupowane po modelu (osobny batch na model); **OpenRouter** wysyła zapytania inline (bez uploadu pliku) i zwraca wyniki wewnątrz samego obiektu batcha (jeden model na batch, więc też grupowany). OpenRouter używa **osobnego modelu batch** — wtyczka automatycznie dopisuje sufiks `:batch` do skonfigurowanego modelu (np. `google/gemini-3.7-flash` → `google/gemini-3.7-flash:batch`), więc w konfiguracji podajesz ten sam model co dla zwykłego generowania.
- **Limit kolejki OpenAI (auto, hands-off):** OpenAI zlicza tokeny wszystkich oczekujących batchy względem limitu organizacji (2M na niższych planach). Zapytania OpenAI są więc dzielone na paczki poniżej budżetu tokenów (`openai_batch_token_budget`, domyślnie 1,5M — z uwzględnieniem tokenów naszych batchy już w locie; ustawisz go w **Ustawienia → Generowanie AI → Dostawcy → Zaawansowane → „Budżet kolejki Batch API (OpenAI)"**) i wysyłane tyle, ile się mieści; reszta jest **odłożona jako zadanie**. Zaznaczenie zapisywane jest w `ai_batches.json`, a timer co minutę pobiera wyniki i automatycznie dosyła kolejny plaster pustych pól. Postęp zobaczysz w **Ustawienia → Start → Aktywność**, z przyciskami **Sprawdź batche** i **Odśwież**.
- Ograniczenia: dostawcy `anthropic`/`openai`/`openrouter`, bez fallbacku. Pola zależne używają stanu notatki z chwili wysyłki — batchuj najpierw pola-rodziców, zastosuj, potem dzieci.

## Konfiguracja (`config.json` → sekcja `ai_generator`)

### Podstawowe ustawienia

```json
"ai_generator": {
    "button_label": "AI",
    "skip_tags": ["skip-ai"],
    "batch_limit": 3,
    "batch_sleep": 1.0,
    "parallel_requests": 3,
    "max_retries": 3,
    "request_timeout": 30,
    "openai_batch_token_budget": 1500000,
    "providers": { ... },
    "note_types": { ... }
}
```

| Pole | Opis |
|---|---|
| `button_label` | Etykieta przycisku w edytorze |
| `skip_tags` | Lista tagów wykluczających — notatki z dowolnym z tych tagów są pomijane w całości (brak wywołań API, brak aktualizacji); `[]` wyłącza funkcję |
| `batch_limit` | Liczba kart w jednej grupie — po każdej grupie następuje przerwa `batch_sleep` |
| `batch_sleep` | Pauza (sekundy) między grupami kart — zapobiega limitom API |
| `parallel_requests` | Liczba równoległych żądań API w batchu (1–16, domyślnie `3`) — `ThreadPoolExecutor` w `browser_ui._run_batch` |
| `max_retries` | Liczba prób przy błędach API — HTTP 429/5xx, timeouty, błędy połączenia (domyślnie `3`) |
| `request_timeout` | Timeout pojedynczego żądania do API w sekundach (domyślnie `30`) |
| `openai_batch_token_budget` | Budżet tokenów kolejki OpenAI Batch (domyślnie `1_500_000`) |
| `providers.<nazwa>.rpm` | Limit żądań/min dla dostawcy — równomierny odstęp `60/rpm` s między startami (anti-burst); `0` = bez limitu. OpenRouter `20`, Mistral `40` |
| `providers.<nazwa>.max_concurrent` | Maks. równoległych żądań do dostawcy (semafor); `0` = bez limitu; darmowe API zwykle `1` |
| `providers.openrouter.rate_limit_free_only` | Tylko OpenRouter: `true` = limit dotyczy tylko modeli `:free`, `false` = wszystkich żądań |

### Konfiguracja dostawców

W UI dostawcy są w **Ustawienia → Generowanie AI → Dostawcy**. Każdy dostawca ma własną podzakładkę z kluczem API i modelem domyślnym. Konkretny model wybiera się per prompt; model domyślny jest fallbackiem dla starszej konfiguracji i nowych promptów. Limity paczek, przerwy, ponowienia i timeouty są w sekcji **Zaawansowane**.

```json
"providers": {
    "openai": {
        "api_key": "sk-...",
        "model": "gpt-4o",
        "temperature": 0.2,
        "reasoning_effort": "medium",
        "fallback_model": "gpt-4o-mini"
    },
    "anthropic": {
        "api_key": "sk-ant-...",
        "model": "claude-3-5-haiku-20241022",
        "temperature": 0.2,
        "max_tokens": 2048,
        "fallback_model": ""
    },
    "google": {
        "api_key": "AIza...",
        "model": "gemini-2.0-flash",
        "temperature": 0.2,
        "fallback_model": ""
    },
    "opencode_go": {
        "api_key": "ocg-...",
        "model": "deepseek-v4-pro",
        "temperature": 0.6,
        "reasoning_effort": "max",
        "fallback_model": "deepseek-v4-flash"
    },
    "codex_cli": {
        "api_key": "",
        "binary_path": "",
        "codex_home": "",
        "model": "gpt-5.4-mini",
        "reasoning_effort": "low",
        "cli_timeout": 180,
        "fallback_model": ""
    },
    "claude_cli": {
        "api_key": "",
        "binary_path": "",
        "system_prompt": "",
        "model": "haiku",
        "cli_timeout": 180,
        "fallback_model": ""
    }
}
```

`fallback_model` (puste `""` = brak fallbacku na poziomie providera) — model zapasowy uruchamiany gdy główny model zawiedzie. Używa tego samego providera i klucza API. Prompt może nadpisać ten fallback własnym `fallback_provider` + `fallback_model` (patrz sekcja **Fallback modeli** poniżej).

`temperature` to **temperatura domyślna** providera — używana przez prompty bez własnej wartości. Każdy prompt może ją nadpisać kluczem `temperature` w `note_types` (UI: Prompty → pole „Temperatura"; „— domyślna dostawcy" = dziedzicz).

`reasoning_effort` zachowuje się różnie w zależności od dostawcy:

- **openai / cometapi / openrouter** — dropdown z wartościami `none`, `minimal`, `low`, `medium`, `high`, `xhigh`. Wysyłany tylko dla modeli OpenAI reasoning (`o1/o3/o4`, `gpt-5+`). Modele reasoning nie dostają `temperature`. Fallback automatyczny jeśli model zwróci HTTP 400.
- **opencode_go** — wolny tekst (QLineEdit). Wartości różnią się per model: `max` dla DeepSeek V4 Pro, inne modele mają inne wartości lub nie obsługują reasoning. Puste pole = parametr nie jest wysyłany. Fallback automatyczny jeśli API zwróci błąd.
- **mistral / nvidia** — nie obsługują `reasoning_effort`.
- **anthropic / google** — nie mają pola `reasoning_effort` w UI.

`max_tokens` jest używany przez Anthropic oraz modele OpenCode Go korzystające z formatu Messages. Domyślnie `2048`. Zwiększ, jeśli generujesz długie odpowiedzi.

### Dostępni dostawcy

| Dostawca | Endpoint | Gdzie pobrać klucz API |
|---|---|---|
| `openai` | `api.openai.com` | platform.openai.com |
| `anthropic` | `api.anthropic.com` | console.anthropic.com |
| `google` | `generativelanguage.googleapis.com` | aistudio.google.com |
| `openrouter` | `openrouter.ai` | openrouter.ai/keys |
| `cometapi` | `api.cometapi.com` | cometapi.com |
| `mistral` | `api.mistral.ai` | console.mistral.ai |
| `nvidia` | `integrate.api.nvidia.com` | build.nvidia.com |
| `opencode_go` | `opencode.ai/zen/go/v1` | opencode.ai/auth |
| `codex_cli` | lokalna binarka `codex` | **bez klucza** — `codex login` |
| `claude_cli` | lokalna binarka `claude` | **bez klucza** — `claude auth login` |

### Dostawcy lokalni — generowanie bez klucza API

`codex_cli` i `claude_cli` nie łączą się z żadnym API bezpośrednio. Uruchamiają lokalnie zainstalowaną, zalogowaną binarkę oficjalnego klienta (`codex` albo `claude`). Zużycie idzie na limity Twojej subskrypcji, nie na płatne API — dodatek nigdy nie widzi tokenu.

Obaj dostawcy zachowują się tak samo w tych punktach:

- **Wykrywanie binarki.** Puste `binary_path` = autodetekcja. Przeszukiwany jest `PATH` **rozszerzony** o typowe katalogi instalacji (`/opt/homebrew/bin`, `/usr/local/bin`, `/opt/local/bin`, `~/.local/bin`, `~/.bun/bin`, `~/.npm-global/bin`, `~/bin`), a potem lokalizacje charakterystyczne dla danego klienta. Rozszerzenie jest konieczne, bo aplikacja GUI na macOS nie dziedziczy `PATH`-u z powłoki: Anki uruchomione z Findera dostaje z launchd tylko `/usr/bin:/bin:/usr/sbin:/sbin` i bez tego nie znalazłoby niczego z Homebrew.
- **Środowisko procesu.** Wycięte do `PATH`, `HOME`, `USER`/`LOGNAME` i kilku zmiennych regionalnych — pozostałe klucze API z tej wtyczki nie trafiają w zasięg uruchamianego CLI. `USER`/`LOGNAME` muszą zostać, bo bez nich odczyt keychaina na macOS zawodzi i zalogowane CLI raportuje brak logowania.
- **Status w UI.** Ustawienia → Generowanie AI → Dostawcy pokazują wykrytą ścieżkę i stan logowania (przycisk **Odśwież**); ✓ na liście dostawców oznacza gotowość, nie obecność klucza.
- **Ograniczenia.** `temperature` jest ignorowana (żaden z klientów jej nie wystawia), Batch API nie działa (wymaga klucza), a prompt idzie przez stdin, nie przez `argv`.

#### Codex CLI (subskrypcja ChatGPT)

**Wymagania:** [Codex CLI](https://developers.openai.com/codex) zainstalowany i zalogowany przez `codex login` (tryb ChatGPT).

| Klucz | Znaczenie |
|---|---|
| `binary_path` | Ścieżka do `codex`. Puste = autodetekcja; dodatkowy kandydat: `/Applications/ChatGPT.app/Contents/Resources/codex` |
| `codex_home` | `CODEX_HOME` z logowaniem. Puste = zmienna środowiskowa albo `~/.codex` |
| `cli_timeout` | Limit czasu jednego `codex exec` (domyślnie 180 s). Globalny `request_timeout` jest liczony pod HTTP i bywa za krótki dla rozumowania |
| `reasoning_effort` | `low`/`medium`/`high`/`xhigh`/`max`/`ultra` → `-c model_reasoning_effort=…`. Niższy = mniej zużytego limitu planu |

**Czego ten dostawca nie robi:** nie czyta ani nie kopiuje tokenu z `auth.json` — zagląda tam wyłącznie po `auth_mode`, żeby pokazać status logowania. Nie ma tu żadnego własnego OAuth ani wywołań do `chatgpt.com/backend-api`.

**Utwardzenie.** Treść pól notatki to dane niezaufane (talie bywają pobierane z internetu), a Codex jest agentem z dostępem do powłoki. Shella nie da się wyłączyć, więc agent trafia do sandboksa:

```
--sandbox read-only     brak zapisu i brak sieci dla agenta
-C <pusty katalog>      katalog tymczasowy, nie repozytorium użytkownika
--ephemeral             bez zapisu sesji z treścią fiszek na dysk
--ignore-user-config    bez cudzych hooków i serwerów MCP
--ignore-rules          bez plików .rules z dysku
```

**Dodatkowe ograniczenia:** każde wywołanie niesie preambułę agentową rzędu kilku tysięcy tokenów, a modele są zawężone do tych, które dopuszcza konto ChatGPT — modele `*-codex-*` zwykle są odrzucane komunikatem *„not supported when using Codex with a ChatGPT account"*.

#### Claude CLI (subskrypcja Claude)

**Wymagania:** [Claude Code](https://claude.com/claude-code) zainstalowany i zalogowany przez `claude auth login` na koncie z subskrypcją (Pro/Max). Logowanie samym kluczem API jest odrzucane — do tego służy dostawca `anthropic`.

| Klucz | Znaczenie |
|---|---|
| `binary_path` | Ścieżka do `claude`. Puste = autodetekcja; dodatkowy kandydat: `~/.claude/local/claude` |
| `system_prompt` | Zastępuje systemowy prompt Claude Code. Puste = domyślny prompt generatora fiszek |
| `cli_timeout` | Limit czasu jednego `claude -p` (domyślnie 180 s) |
| `model` | Alias (`haiku`, `sonnet`, `opus`, `fable`) albo pełna nazwa (np. `claude-sonnet-5`) |

**Czego ten dostawca nie robi:** nie dotyka poświadczeń. Token siedzi w keychainie systemu, a status logowania pochodzi z `claude auth status --json`, które tokenu nie zwraca.

**Izolacja.** Mocniejsza niż przy Codeksie, bo nie wymaga sandboksa — `--tools ""` **usuwa wszystkie narzędzia**, więc wstrzyknięta treść fiszki nie ma czego wywołać:

```
--tools ""                  zero narzędzi: brak shella, plików i sieci
--strict-mcp-config         bez serwerów MCP użytkownika
--disable-slash-commands    bez skilli z dysku
--no-session-persistence    bez zapisu treści fiszek na dysk
<pusty katalog roboczy>     bez wciągania CLAUDE.md z katalogu startowego Anki
```

Nigdy nie używamy `--bare`: wymusza `ANTHROPIC_API_KEY` i nie czyta OAuth ani keychaina, więc rozwaliłoby uwierzytelnienie subskrypcją.

**Narzut tokenów.** `--system-prompt` **zastępuje** prompt Claude Code, a nie go rozszerza — to główny powód, dla którego ten dostawca nadaje się do generowania hurtowego:

| Wywołanie | Tokeny wejścia na fiszkę |
|---|---|
| `codex exec` | ~5300 |
| `claude -p` domyślnie | ~2500 |
| `claude -p --system-prompt …` | **~280** |

### Pobieranie dostępnych modeli

Nie musisz wpisywać nazwy modelu ręcznie. W ustawieniach, przy każdym dostawcy jest przycisk **Pobierz** — pobiera listę dostępnych modeli bezpośrednio z API danego dostawcy:

| Dostawca | Źródło listy modeli | Wymaga klucza? |
|---|---|---|
| `openai` | `GET /v1/models` | tak |
| `anthropic` | `GET /v1/models` | tak |
| `google` | `GET /v1beta/models` | tak |
| `openrouter` | `GET /v1/models` | nie (publiczne) |
| `cometapi` | `GET /api/models` | nie (publiczne) |
| `mistral` | `GET /v1/models` | tak |
| `nvidia` | `GET /v1/models` | nie (publiczne) |
| `opencode_go` | `GET /zen/go/v1/models` | tak |
| `codex_cli` | `model/list` przez `codex app-server` | nie (lokalne logowanie) |
| `claude_cli` | aliasy rodzin modeli (CLI nie wystawia listy) | nie (lokalne logowanie) |

Po kliknięciu **Pobierz** pole modelu (edytowalny QComboBox) wypełnia się listą modeli. Nadal możesz wpisać model ręcznie. Wpisywanie filtruje listę po dowolnym fragmencie nazwy, np. `5.5`. Listy modeli są **cachowane w konfiguracji** (`cached_models`) — przeżywają restart Anki, nie trzeba ponownie pobierać po restarcie. Przycisk **Pobierz** zawsze wymusza odświeżenie z API i nadpisuje cache. W edytorze promptów listy modeli są współdzielone między dostawcą głównym a zapasowym — pobranie w jednym miejscu odświeża oba combo.

### Przykładowe modele

| Dostawca | Model | Charakterystyka |
|---|---|---|
| `openai` | `gpt-4o` | Silny, droższy |
| `openai` | `gpt-4o-mini` | Szybki, tani |
| `anthropic` | `claude-3-5-haiku-20241022` | Szybki, tani |
| `anthropic` | `claude-3-5-sonnet-20241022` | Silniejszy |
| `google` | `gemini-2.0-flash` | Szybki, tani |
| `google` | `gemini-1.5-pro` | Silniejszy |
| `openrouter` | `anthropic/claude-3.5-haiku` | Dostęp do wielu modeli |
| `cometapi` | `grok-4-1-fast-non-reasoning` | Alternatywny dostęp |
| `mistral` | `mistral-small-latest` | Szybki, tani |
| `mistral` | `mistral-medium-latest` | Silniejszy |
| `nvidia` | `meta/llama-3.3-70b-instruct` | Darmowe kredyty na start |
| `opencode_go` | `deepseek-v4-pro` | Reasoning, tani w subskrypcji Go |
| `opencode_go` | `deepseek-v4-flash` | Bardzo tani, szybki |
| `opencode_go` | `kimi-k2.6` | Dobry do kodowania |
| `opencode_go` | `glm-5.1` | Alternatywa |
| `codex_cli` | `gpt-5.4-mini` | Najtańszy w limicie planu — dobry do fiszek |
| `codex_cli` | `gpt-5.5` | Silniejszy, szybciej zjada limit |
| `claude_cli` | `haiku` | Najtańszy w limicie planu — dobry do fiszek |
| `claude_cli` | `sonnet` | Silniejszy, szybciej zjada limit |

### Typy notatek

```json
"note_types": {
    "angielski": {
        "cz_mowy": {
            "target": "cz_mowy",
            "provider": "cometapi",
            "model": "grok-4-1-fast-non-reasoning",
            "prompt": "Classify: EN: {{ang}} PL: {{pol}}"
        },
        "def": {
            "target": "def",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "prompt": "Write a definition for: {{ang}}"
        }
    }
}
```

- Klucz zewnętrzny (`"angielski"`) — nazwa typu notatki **dokładnie jak w Anki**
- Klucz wewnętrzny (`"cz_mowy"`) — **nazwa zadania**: dowolny identyfikator, decyduje o kolejności generowania
- `target` — nazwa pola karty do wypełnienia
- `provider` — którego dostawcy użyć dla tego pola
- `model` — model używany przez ten prompt; brak wartości używa modelu domyślnego dostawcy
- `fallback_provider` (opcjonalne) — dostawca zapasowy; puste/brak = ten sam dostawca co główny
- `fallback_model` (opcjonalne) — model zapasowy; puste/brak = brak fallbacku per-prompt (użyty `fallback_model` z dostawcy, jeśli ustawiony)
- `temperature` (opcjonalne) — temperatura tylko dla tego promptu (0.0–2.0); brak = temperatura domyślna dostawcy. Niska (0.0–0.3) dla definicji/faktów, wyższa (0.7–1.0) dla przykładowych zdań; fallback promptu używa tej samej wartości
- `prompt` — treść prompta z opcjonalnymi szablonami

## Fallback modeli

Gdy główny model zawiedzie (błąd API, rate limit, brak środków na koncie, brak treści w odpowiedzi), wtyczka automatycznie uruchamia model zapasowy z tym samym promptem. Fallback jest konfigurowalny na dwóch poziomach:

| Poziom | Pola | Gdzie w UI |
|---|---|---|
| **Per prompt** (wyższy priorytet) | `fallback_provider` + `fallback_model` | Ustawienia → Generowanie AI → Prompty |
| **Per dostawca** (niższy priorytet) | `fallback_model` | Ustawienia → Generowanie AI → Dostawcy |

Priorytetyzacja:
1. Jeśli prompt ma `fallback_model` → użyj go (z `fallback_provider` lub tym samym dostawcą)
2. Jeśli prompt nie ma `fallback_model` → sprawdź `fallback_model` w konfiguracji dostawcy
3. Obie puste = brak fallbacku (błąd jest logowany, zachowanie jak wcześniej)

Przykład per-prompt (cross-provider fallback):
```json
"def": {
    "target": "def",
    "provider": "openai",
    "model": "gpt-4o",
    "fallback_provider": "openrouter",
    "fallback_model": "anthropic/claude-3.5-haiku",
    "prompt": "Write a definition for: {{ang}}"
}
```

Przykład per-dostawca (ten sam provider, tańszy model):
```json
"providers": {
    "openai": {
        "api_key": "sk-...",
        "model": "gpt-4o",
        "fallback_model": "gpt-4o-mini"
    }
}
```

Właściwości:
- Fallback używa tego samego promptu i temperatury zadania (per-prompt `temperature`, a gdy brak — domyślnej dostawcy fallbackowego); reasoning_effort pochodzi z konfiguracji dostawcy fallbackowego
- Jeśli `fallback_provider` jest inny niż główny → używa klucza API dostawcy zapasowego
- Log zawiera ostrzeżenie: `AI: fallback dla pola 'def': openai/gpt-4o → openai/gpt-4o-mini`
- Jeśli fallback też zawiedzie → `last_error` zawiera błąd fallbacku z prefixem „Fallback"

## Rate limiter per dostawca

Darmowe tiery API mają limity łatwe do przekroczenia w batchu (Mistral free: 0.83 req/s + 25k tokenów/min; OpenRouter `:free`: 20 RPM + odrzucanie żądań jednoczesnych). Klasa `RateLimiter` (singleton, kubełek per dostawca) chroni przed tym tempem i burstami. Każdy dostawca konfiguruje limit na swojej karcie w **Ustawienia → Generowanie AI → Dostawcy**:

- **Limit RPM** (`providers.<nazwa>.rpm`) — równomierny odstęp `60/rpm` s między startami żądań (anti-burst, nie odrzuca — pauzuje); `0` = bez limitu. RPS → RPM: pomnóż ×60 (Mistral 0.83 RPS → ~50; domyślnie `40` z marginesem, OpenRouter `20`)
- **Maks. równoległych** (`providers.<nazwa>.max_concurrent`) — semafor ograniczający liczbę jednoczesnych żądań (domyślnie `1` dla darmowych); działa nawet gdy batch leci wielowątkowo (`parallel_requests`)
- **Limit tylko dla modeli `:free`** (`providers.openrouter.rate_limit_free_only`, tylko OpenRouter) — zaznaczone: limit obejmuje wyłącznie modele `:free`, płatne lecą bez dławienia; u innych dostawców limit zawsze obejmuje wszystkie żądania
- Dotyczy modelu głównego i fallbackowego; TPM (tokeny/min) nie jest egzekwowane wprost — łapie je retry przy HTTP 429
- Back-compat: stare `free_model_rate_limit`/`free_model_max_concurrent` (usunięte z szablonu config.json) są nadal czytane dla OpenRoutera, gdy w zapisanej konfiguracji brak per-provider `rpm`

```json
"providers": {
    "openrouter": { "rpm": 20, "max_concurrent": 1, "rate_limit_free_only": true },
    "mistral":    { "rpm": 40, "max_concurrent": 1 }
}
```

## Składnia promptów

| Składnia | Działanie |
|---|---|
| `{{ang}}` | Wstawia wartość pola `ang` z karty |
| `{{pol}}` | Wstawia wartość pola `pol` z karty |
| `{% if def %}...{% endif %}` | Renderuje blok tylko gdy pole `def` jest niepuste |
| `{% if def %}...{% else %}...{% endif %}` | Wariant z fallbackiem |

Pola są generowane w kolejności wpisu w `note_types`. Wynik wcześniejszego pola można użyć w prompcie następnego przez `{{nazwa_pola}}`. Zmiana nazwy zadania w edytorze promptów zachowuje jego pozycję w kolejności.

Edytor promptów (**Ustawienia → Generowanie AI → Prompty**) pomaga uniknąć literówek:
- **+ Dodaj** pyta tylko o typ notatki (przy jednym wybiera go automatycznie), a potem otwiera pusty wpis w głównym edytorze; nazwę zadania, pole docelowe i treść promptu uzupełniasz w jednym miejscu
- **Dostawca AI** i **Model AI** są ustawiane osobno dla każdego promptu; model można pobrać z API (przycisk **Pobierz**), wpisać ręcznie i filtrować po fragmencie nazwy; lista pobranych modeli jest cachowana i współdzielona z zakładką Dostawcy
- **Dostawca zapasowy** i **Model zapasowy** — analogicznie, z własnym przyciskiem **Pobierz**; lista modeli jest współdzielona z dostawcą głównym gdy ten sam dostawca
- **Typ notatki** i **pole docelowe** to edytowalne comboboxy z listami pobranymi z kolekcji Anki
- Przycisk **Wstaw pole ▾** nad edytorem promptu wstawia `{{pole}}` w pozycji kursora (lista zawiera pola typu notatki + targety wcześniejszych zadań)
- Przycisk **Wstaw warunek ▾** wstawia gotowy szkielet `{% if pole %}…{% else %}…{% endif %}` i ustawia kursor w środku; zaznaczony tekst zostaje owinięty warunkiem (trafia do gałęzi „if", a kursor do pustego „else")
- Walidacja na żywo pod edytorem ostrzega gdy: typ notatki nie istnieje w kolekcji, pole docelowe nie istnieje w typie notatki, prompt używa nieznanych `{{pól}}` lub `{% if pól %}`
- Walidacja sprawdza też strukturę bloków: niedomknięty `{% if %}`, osierocony `{% else %}`/`{% endif %}`, podwójny `{% else %}`, `{% if %}` bez nazwy pola oraz zagnieżdżone `{% if %}` (nieobsługiwane przez silnik — patrz Ograniczenie wyżej); ta część działa nawet bez dostępu do kolekcji (`template_engine.template_structure_problems()`)

> **Ograniczenie:** zagnieżdżone `{% if %}` wewnątrz `{% if %}` nie są obsługiwane.

> **Uwaga:** Wartości pól użyte w szablonach są pobierane na początku generowania (przed wywołaniem API). Pola zawierające HTML (`<div>`, `&nbsp;` itp.) są automatycznie oczyszczane przed wstawieniem do promptu — AI otrzymuje czysty tekst.

## Dodanie nowego dostawcy

**Wariant A — API zgodne z OpenAI Chat Completions** (najczęstszy). Wystarczy cienka klasa w `providers/__init__.py`:
```python
class MojProvider(OpenAICompatProvider):
    API_URL = "https://api.example.com/v1/chat/completions"
    LABEL = "Moj Provider"
    # SUPPORTS_REASONING_EFFORT = False  # jeśli API odrzuca reasoning_effort
```
`OpenAICompatProvider` (z `base.py`) dostarcza gotowe `call_api()`: auth Bearer, `temperature`/`reasoning_effort` wg modelu, retry z fallbackiem i rozbiór przez `_parse_chat_completion()`.

**Wariant B — inny format API.** Utwórz `providers/moj_provider.py`, dziedzicz po `BaseProvider` i zaimplementuj `call_api()`:
```python
from .base import BaseProvider
from typing import Optional

class MojProvider(BaseProvider):
    def call_api(self, prompt: str) -> Optional[str]:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        raw = self._post(url, data, headers)  # POST z retry dla 429/5xx
        if raw is None:
            return None
        # gotowe parsery z bazy: _parse_chat_completion() (format OpenAI)
        # lub _parse_messages() (format Anthropic); albo własny rozbiór
        return self._parse_messages(raw, "Moj Provider")
```

2. Zarejestruj klasę w słownikach `PROVIDERS` (i `PROVIDER_LABELS`) w `providers/__init__.py` — `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` jest auto-derivowane z `PROVIDERS`, a `settings/prompts_tab.py` iteruje po `PROVIDER_LABELS` (żadnej manualnej listy do aktualizacji).

3. Dodaj w `config.json`:
```json
"providers": {
    "moj_provider": {
        "api_key": "...",
        "model": "...",
        "temperature": 0.2
    }
}
```

`BaseProvider.__init__` przyjmuje `max_retries`, `timeout`, `max_tokens` i `reasoning_effort` — są przekazywane automatycznie z konfiguracji. `max_tokens` jest opcjonalne i używane przez API w formacie Messages (Anthropic oraz wybrane modele OpenCode Go). `self._post(url, data, headers)` serializuje `data` do JSON i wysyła POST z retry (delegowane do `common.http.post_json`); `self.last_error` jest ustawiane przy błędzie. Jeśli nowy dostawca proxy'uje modele OpenAI, użyj `add_reasoning_effort_if_supported()` i `self._post_with_reasoning_fallback()` zamiast `_post()` — otrzymasz automatyczny fallback gdy model nie obsługuje reasoning (parametr jest usuwany z body i żądanie ponawiane).
