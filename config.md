# Anki Toolkit — konfiguracja

## Sekcja `modules` — włączanie modułów

Każdy moduł można wyłączyć ustawiając `false`. Wyłączony moduł nie jest ładowany i nie pojawia się w menu. Zmiana wymaga restartu Anki.

```json
"modules": {
    "dictionary":        true,
    "ai_generator":      true,
    "tts":               true,
    "filtered_deck":     true,
    "audio_normalizer":  true,
    "nbsp_remover":      true,
    "field_splitter":    true
}
```

---

## Sekcja `dictionary` — pobieranie audio i IPA

**`source_field`** — nazwa pola karty zawierającego angielskie słowo (np. `"ang"`).

**`target_field`** — nazwa pola, do którego trafia audio `[sound:...]` (np. `"audio"`).

**`ipa_field`** — nazwa pola dla transkrypcji IPA. Pozostaw pusty string `""` aby wyłączyć.

**`wiktionary_ipa_fallback`** — `true` (domyślnie) = gdy Oxford/Cambridge nie znajdzie IPA dla słowa, automatycznie odpyta Wiktionary API. `false` = wyłącza fallback, pole IPA zostaje puste gdy primary source nie zwróci wyników. Wiktionary dostarcza tylko IPA — nie ma audio.

**`diki_ipa_fallback`** — `true` = przy pobieraniu audio z Diki (które nie ma natywnego IPA), moduł pobiera IPA z osobnego źródła określonego przez `diki_ipa_fallback_source`. Domyślnie `false`.

**`diki_ipa_fallback_source`** — źródło IPA dla Diki: `"wiktionary"` (domyślnie), `"oxford"` albo `"cambridge"`. Jeśli wybrane źródło inne niż Wiktionary zwróci `None`, może zadziałać dalszy fallback przez `wiktionary_ipa_fallback`.

**`ipa_format`** — format zapisu IPA:
- `"compact"` — `/θɔːt/` (jeśli UK=US) lub `UK: /θɔːt/ • US: /θɑːt/`
- `"both"` — `UK: /.../ • US: /.../` gdy różne; `/{phon}/` gdy UK==US
- `"uk_only"` — tylko wymowa brytyjska
- `"us_only"` — tylko wymowa amerykańska

**`max_retries`** — liczba prób przy błędach sieci (429, 5xx). Domyślnie `3`. Dotyczy pobierania strony słownika i MP3.

**`page_timeout`** — timeout pobierania strony słownika w sekundach. Domyślnie `10`.

**`mp3_timeout`** — timeout pobierania pliku MP3 w sekundach. Domyślnie `10`.

**`buttons`** — lista przycisków w edytorze. Każdy wpis:
- `"dictionaries"` — lista słowników do użycia, np. `["oxford_uk", "oxford_us"]`.
  Dostępne wartości: `oxford_uk`, `oxford_us`, `cambridge_uk`, `cambridge_us`,
  `diki_uk`, `diki_us`, `longman_uk`, `longman_us`
- `"label"` — tekst wyświetlany na przycisku
- `"enabled"` — `true` / `false`

---

## Sekcja `tts` — generowanie audio przez TTS

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka TTS** lub edycję `config.json`. Akcje TTS dostępne przez **prawy klik w przeglądarce → Anki Toolkit → TTS** oraz **PPM na polu docelowym w edytorze**.

**`tts_provider`** — `"kokoro"` (domyślnie) lub `"openrouter"`. Wybiera silnik TTS.

**`button_label`** — etykieta przycisku TTS w toolbarze edytora (domyślnie `"TTS"`).

**`api_url`** — adres lokalnego serwera Kokoro (domyślnie `http://localhost:8880/v1/audio/speech`). Tylko dla `tts_provider: "kokoro"`.

**`model`** — nazwa modelu Kokoro (domyślnie `"kokoro"`). Tylko dla `tts_provider: "kokoro"`.

**`openrouter_api_key`** — klucz API z https://openrouter.ai/keys. Tylko dla `tts_provider: "openrouter"`.

**`use_ai_openrouter_key`** — `true` = użyj klucza OpenRouter z `ai_generator.providers.openrouter.api_key` (jeden klucz dla AI i TTS). Domyślnie `false`.

**`openrouter_model`** — ID modelu TTS z OpenRouter (domyślnie `"openai/gpt-4o-mini-tts-2025-12-15"`).

**`voices`** — lista głosów biorących udział w losowaniu. Każda notatka/zdanie dostaje losowo wybrany głos z tej listy.

**`speed`** — tempo mowy (0.1–3.0, domyślnie 0.9). Walidowane w UI; backend nie wymusza zakresu.

**`tasks`** — lista zadań TTS. Każde zadanie to obiekt:
- `"label"` — etykieta w menu i na tooltipie
- `"source_field"` — pole czytane (tekst do syntezy)
- `"target_field"` — pole zapisywane (`[sound:...mp3]`)
- `"mode"` — `"single"` (jedno audio na notatkę) lub `"split"` (osobne audio na segment)
- `"split_separator"` — separator trybu split (domyślnie `"<br><br>"`; tylko dla `mode: "split"`)

Jawnie zapisana **pusta lista** = brak zadań. Brak klucza = backward compat (legacy pola poniżej).

**`ang_source_field`** / **`ang_target_field`** / **`przyklad_target_field`** — *legacy.* Czytane z zapisanego configu **tylko** gdy klucz `tasks` w ogóle nie istnieje — służą do zbudowania domyślnej listy zadań dla starych instalacji. Nie są już w `_DEFAULTS` ani w UI; nowe instalacje używają wyłącznie listy `tasks`. Wystarczy raz zapisać ustawienia w UI, by `tasks` stało się jedynym źródłem.

**`max_workers`** — liczba równoległych wątków generowania audio. Domyślnie `12`. Zmniejsz przy problemach z wydajnością lub przy słabszym serwerze Kokoro.

**`max_retries`** — liczba prób przy błędach API (429, 5xx). Domyślnie `3`. Retry w `common.http.post_json()`.

**`timeout`** — timeout pojedynczego żądania TTS w sekundach. Domyślnie `60`.

---

## Sekcja `ai_generator` — generowanie pól przez AI

**`button_label`** — etykieta przycisku AI w edytorze kart.

**`batch_limit`** — liczba kart w jednej grupie w trybie batch. Co `batch_limit` kart następuje przerwa `batch_sleep` sekund. Wszystkie zaznaczone karty są zawsze przetwarzane — ten parametr kontroluje tylko rytm pauz.

**`batch_sleep`** — pauza w sekundach między grupami kart w trybie batch (zapobiega limitom API).

**`parallel_requests`** — liczba notatek przetwarzanych równolegle w batchu przeglądarki. Domyślnie `3`. Wyższe wartości przyspieszają batch, ale zwiększają ryzyko limitów API (429).

**`max_retries`** — liczba prób przy błędach API (429, 5xx). Domyślnie `3`. Dotyczy wszystkich providerów.

**`request_timeout`** — timeout pojedynczego żądania do API AI w sekundach. Domyślnie `30`.

**`free_model_rate_limit`** — limit żądań na minutę (RPM) dla modeli darmowych OpenRouter (model ID z sufiksem `:free`, np. `meta-llama/llama-3.2-3b:free`). Domyślnie `15`. OpenRouter zezwala na maks. 20 RPM dla modeli `:free` — 15 zostawia margines bezpieczeństwa. Gdy limit jest osiągnięty, wtyczka czeka do zwolnienia miejsca w oknie 60-sekundowym. Dotyczy tylko modeli z `:free` w nazwie; płatne modele nie są ograniczane. Limit jest globalny (per proces), współdzielony między wątkami batcha.

---

### Providerzy (`providers`)

Każdy provider wymaga:
- `"api_key"` — klucz API
- `"model"` — nazwa modelu
- `"temperature"` — losowość odpowiedzi (0.0–1.0, zalecane 0.2)
- `"fallback_model"` — model zapasowy uruchamiany gdy główny model zawiedzie (błąd API, rate limit, brak środków, brak treści); puste `""` = brak fallbacku na poziomie providera; używa tego samego providera i klucza API; prompt może nadpisać własnym `fallback_provider` + `fallback_model`
- `"cached_models"` — lista modeli pobranych przez przycisk **Pobierz**; zapisywana automatycznie przy OK w ustawieniach; przeżywa restart Anki — nie trzeba ponownie pobierać listy po restarcie; odświeżenie przyciskiem **Pobierz** nadpisuje tę listę

OpenAI obsługuje dodatkowe pole:
- `"reasoning_effort"` — poziom reasoning dla modeli, które go obsługują: `"none"`, `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`; domyślnie `"medium"`. Przy modelach bez obsługi reasoning parametr nie jest wysyłany do API. Przy modelach reasoning OpenAI parametr `"temperature"` również nie jest wysyłany, bo część tych modeli nie obsługuje niestandardowej temperatury.

Providerzy zgodni z OpenAI Chat Completions (`cometapi`, `openrouter`, `mistral`) również pomijają `"temperature"`, jeśli nazwa modelu wskazuje na OpenAI reasoning (`gpt-5...`, `o3...`, także z prefiksem typu `openai/gpt-5.4`). Dla natywnych modeli, np. `mistral-small-latest`, temperatura nadal jest wysyłana.

Tylko Anthropic obsługuje dodatkowe pole:
- `"max_tokens"` — maksymalna długość odpowiedzi (wymagane przez Anthropic API, domyślnie `2048`). Zwiększ przy generowaniu długich tekstów.

Dostępni providerzy i przykładowe modele:

| Provider | Przykładowe modele |
|---|---|
| `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-5`, `gpt-5.1` |
| `cometapi` | `grok-4-1-fast-non-reasoning` |
| `openrouter` | `anthropic/claude-3.5-haiku`, `google/gemini-flash-1.5` |
| `anthropic` | `claude-3-5-haiku-20241022`, `claude-3-5-sonnet-20241022` |
| `google` | `gemini-2.0-flash`, `gemini-1.5-pro` |
| `mistral` | `mistral-small-latest`, `mistral-medium-latest` |
| `opencode_go` | `deepseek-v4-pro`, `deepseek-v4-flash`, `kimi-k2.6`, `glm-5.1` |

Klucz API dla `google` uzyskasz na [Google AI Studio](https://aistudio.google.com/apikey).

---

### Typy notatek (`note_types`)

Klucz to nazwa typu notatki (dokładnie jak w Anki). Każde pole to obiekt z:
- `"target"` — nazwa pola karty do wypełnienia
- `"provider"` — provider AI dla tego pola (wymagany)
- `"model"` — model AI dla tego pola; brak wartości używa modelu domyślnego providera
- `"prompt"` — treść prompta
- `"fallback_provider"` (opcjonalne) — dostawca zapasowy uruchamiany gdy główny model zawiedzie; puste/brak = użyj tego samego dostawcy co główny model
- `"fallback_model"` (opcjonalne) — model zapasowy uruchamiany gdy główny model zawiedzie (błąd API, rate limit, brak środków, brak treści); puste/brak = brak fallbacku per-prompt (wtedy używany jest `fallback_model` z konfiguracji dostawcy, jeśli ustawiony)
- `"manual_only"` (opcjonalne, `true`/`false`, domyślnie `false`) — pole wykluczone z batcha "Wszystkie puste", workflow oraz głównego przycisku AI w edytorze. Dostępne tylko przez jawne wskazanie: submenu "Generuj zablokowane ▸" w przeglądarce lub PPM na polu w edytorze.

W promptach dostępne są:
- `{{nazwa_pola}}` — wstawi wartość pola karty
- `{% if pole %} ... {% else %} ... {% endif %}` — warunek

Pola które już mają zawartość są automatycznie pomijane.

---

---

## Sekcja `audio_normalizer` — normalizacja audio

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Normalizacja**.

**`ffmpeg_path`** — ścieżka do pliku wykonywalnego ffmpeg. Puste `""` = automatyczne wykrycie (PATH, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`).

**`loudnorm_opts`** — parametry filtra ffmpeg loudnorm. Domyślnie `"loudnorm=I=-14:TP=-1.5:LRA=8"` (standard EBU R128).
- `I` — głośność zintegrowana w LUFS (np. `-14` to standard dla serwisów streamingowych)
- `TP` — maksymalny true peak w dBTP (np. `-1.5`)
- `LRA` — zakres głośności w LU (np. `8`)

**`max_workers`** — liczba równoległych procesów ffmpeg. Domyślnie `4`. Zmniejsz przy problemach z wydajnością.

**`auto_normalize`** — `true` = włącza watcher na katalogu mediów Anki; nowe/zmienione pliki audio są automatycznie normalizowane ~3s po dodaniu (debounce). Obejmuje wszystkie źródła: TTS, słownik, AI workflow, ręczne dodanie, AnkiWeb sync. Pomija pliki już przetworzone (historia `mtime`). Domyślnie `false` (opt-in). **Wymaga restartu Anki po zmianie.**

```json
"audio_normalizer": {
    "ffmpeg_path": "",
    "loudnorm_opts": "loudnorm=I=-14:TP=-1.5:LRA=8",
    "max_workers": 4,
    "auto_normalize": false
}
```

---

## Sekcja `filtered_deck` — talia filtrowana

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia**.

**`deck_name`** — nazwa talii filtrowanej do utworzenia/odświeżenia. Domyślnie `"Angielski - Powtórka z wyprzedzeniem"`.

**`search_deck`** — nazwa talii źródłowej, z której pobierane są karty. Domyślnie `"angielski"`.

Akcja: **Narzędzia → Anki Toolkit → Utwórz talię filtrowaną: {search_deck}...** — otwiera dialog z opcjami (dni do przodu, limit kart, kolejność) i tworzy/rebuduje istniejącą talię filtrowaną (`col.sched.rebuild_filtered_deck`).

```json
"filtered_deck": {
    "deck_name": "Angielski - Powtórka z wyprzedzeniem",
    "search_deck": "angielski"
}
```

---

## Sekcja `nbsp_remover` — czyszczenie HTML w kolekcji

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja NBSP Remover).

**`show_tooltip`** — `true` (domyślnie) = pokazuje tooltip z licznikiem oczyszczonych pól przy automatycznym czyszczeniu.

**`auto_run_startup`** — `true` = automatyczne czyszczenie kolekcji przy otwarciu profilu (`gui_hooks.profile_did_open`). Domyślnie `false` (manualne uruchomienie przez menu).

**`skip_field`** — nazwa pola, w którym tagi `<div>` są usuwane całkowicie zamiast zamieniane na `<br>`. Domyślnie `"ang"` (pole angielskiego słowa — bez złamań wiersza).

```json
"nbsp_remover": {
    "show_tooltip": true,
    "auto_run_startup": false,
    "skip_field": "ang"
}
```

Akcje:
- **Narzędzia → Anki Toolkit → Wyczyść HTML w kolekcji...** — batchowe czyszczenie wszystkich notatek (jeden krok undo przez `CollectionOp`)
- Automatyczne oczyszczanie każdej nowo dodanej notatki (`add_cards_did_add_note` hook) — `clean_field()` dzieli `<div>` na `<br>`, usuwa `&nbsp;`

---

## Sekcja `field_splitter` — rozdzielanie pól

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja Rozdzielanie pól).

**`source_field`** — nazwa pola zawierającego dane do rozdzielenia (np. `"przyklad"`). Pole to nie jest modyfikowane — operacja jest kopią, nie przeniesieniem.

**`separator`** — tekst rozdzielający kolejne części w polu źródłowym (domyślnie `"<br><br>"`). Whitespace w separatorze dopasowuje dowolny ciąg whitespace w treści, więc `"<br> <br>"` i `"<br><br>"` są traktowane tak samo gdy separator zawiera spację.

**`target_fields`** — lista pól docelowych oddzielona przecinkami (np. `"p1, p2, p3, p4, p5"`). Pierwsza część trafia do `p1`, druga do `p2`, itd. Pola nieistniejące w typie notatki są pomijane. Nadmiarowe części (więcej części niż pól) są pomijane.

**`overwrite`** — `true` (domyślnie) = nadpisuje pole docelowe nową treścią zawsze. `false` = wypełnia tylko puste pola docelowe; pola z istniejącą treścią są pomijane (bezpieczne gdy uzupełniasz brakujące pola bez ryzyka nadpisania ręcznych poprawek).

```json
"field_splitter": {
    "source_field": "przyklad",
    "separator": "<br><br>",
    "target_fields": "p1, p2, p3, p4, p5",
    "overwrite": true
}
```

Akcje:
- **PPM w przeglądarce → Anki Toolkit → Rozdziel pole przyklad → p1, p2, p3...** — batch na zaznaczonych notatkach (jeden krok undo)
- **Narzędzia → Anki Toolkit → Rozdziel pola w kolekcji...** — wszystkie notatki (z potwierdzeniem)

---

## Sekcja `workflow` — workflow "Generuj fiszkę"

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka AI Generator → Workflow**.

**`enabled`** — `true` (domyślnie) = przycisk workflow w toolbarze edytora + pozycja w menu kontekstowym przeglądarki.

**`editor_label`** — etykieta przycisku w edytorze. Domyślnie `"Generuj fiszkę"`.

**`steps`** — lista kroków wykonywanych sekwencyjnie na pojedynczej notatce. Każdy krok:
- `"module"` — `"ai"`, `"dictionary"` albo `"tts"`
- `"action"` — `"generate"` (dla AI/TTS) albo `"fetch"` (dla dictionary)
- `"dicts"` — opcjonalnie, lista słowników dla kroku dictionary (np. `["oxford_uk", "oxford_us"]`)

```json
"workflow": {
    "enabled": true,
    "editor_label": "Generuj fiszkę",
    "steps": [
        {"module": "ai",         "action": "generate"},
        {"module": "dictionary", "action": "fetch", "dicts": ["oxford_uk", "oxford_us"]},
        {"module": "tts",        "action": "generate"}
    ]
}
```

Kroki wykonują się w tle; notatka jest łapana raz na starcie (przełączenie karty w edytorze w trakcie nie miesza danych). W kroku TTS pliki audio są generowane równolegle przez `ThreadPoolExecutor`.

---

## Sekcja `debug` — logowanie wtyczki

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Logi**.

**`enabled`** — `true` = włącza logowanie na poziomie DEBUG (szczegółowe logi HTTP, parsery, statystyki); `false` (domyślnie) = tylko WARNING i wyżej. Może być przełączane live w UI bez restartu Anki (`common.debug_log.set_debug()`).

```json
"debug": {
    "enabled": false
}
```

Logi są buforowane w pamięci (deque 2000 wpisów) — dostępne w zakładce Logi z przyciskami Odśwież i Wyczyść.
