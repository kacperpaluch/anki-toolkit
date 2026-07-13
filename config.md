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
    "field_splitter":    true,
    "sibling_manager":   true,
    "sentence_unlocker": true,
    "deck_router":       true,
    "field_hider":       true,
    "web_bridge":        true,
    "word_queue":        true
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

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Wymowa → TTS** lub edycję `config.json`. Akcje TTS dostępne przez **prawy klik w przeglądarce → Anki Toolkit → TTS** oraz **PPM na polu docelowym w edytorze**.

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

Limity tempa (RPM) i jednoczesności są ustawiane **per provider** — patrz `providers.<nazwa>.rpm` / `max_concurrent` / `rate_limit_free_only` poniżej.

---

### Providerzy (`providers`)

Każdy provider wymaga:
- `"api_key"` — klucz API
- `"model"` — nazwa modelu
- `"temperature"` — **temperatura domyślna** providera (0.0–2.0, zalecane 0.2); używana przez prompty, które nie mają własnej `"temperature"` (patrz sekcja `note_types` niżej)
- `"fallback_model"` — model zapasowy uruchamiany gdy główny model zawiedzie (błąd API, rate limit, brak środków, brak treści); puste `""` = brak fallbacku na poziomie providera; używa tego samego providera i klucza API; prompt może nadpisać własnym `fallback_provider` + `fallback_model`
- `"cached_models"` — lista modeli pobranych przez przycisk **Pobierz**; zapisywana automatycznie przy OK w ustawieniach; przeżywa restart Anki — nie trzeba ponownie pobierać listy po restarcie; odświeżenie przyciskiem **Pobierz** nadpisuje tę listę

Limity API (opcjonalne, per provider — pola **Limit RPM** i **Maks. równoległych** na karcie dostawcy):
- `"rpm"` — maks. żądań na minutę; żądania rozkładane równomiernie (`60/rpm` s odstępu między startami, anti-burst); `0`/brak = bez limitu. Jeśli dostawca podaje limit jako RPS, pomnóż ×60 (Mistral free 0.83 RPS → ~50; domyślnie `40` z marginesem, OpenRouter `20`)
- `"max_concurrent"` — maks. równoległych żądań do dostawcy (semafor); `0`/brak = bez limitu; darmowe tiery zwykle wymagają `1`
- `"rate_limit_free_only"` — **tylko OpenRouter**: `true` (domyślnie) = limit dotyczy wyłącznie modeli z `:free` w nazwie (płatne lecą bez dławienia); `false` = wszystkich żądań. Inni dostawcy zawsze dławią wszystkie żądania (darmowy klucz API limituje cały klucz). Stare globalne `free_model_rate_limit`/`free_model_max_concurrent` (usunięte z szablonu config.json) są nadal czytane jako back-compat dla OpenRoutera, gdy w zapisanej konfiguracji brak per-provider `rpm`. Limit (RPM/TPM nieliczony — TPM łapie retry 429) jest per proces, współdzielony między wątkami batcha

OpenAI obsługuje dodatkowe pole:
- `"reasoning_effort"` — poziom reasoning dla modeli, które go obsługują: `"none"`, `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`; domyślnie `"medium"`. Przy modelach bez obsługi reasoning parametr nie jest wysyłany do API. Przy modelach reasoning OpenAI parametr `"temperature"` również nie jest wysyłany, bo część tych modeli nie obsługuje niestandardowej temperatury.

Providerzy zgodni z OpenAI Chat Completions (`cometapi`, `openrouter`, `mistral`, `nvidia`) również pomijają `"temperature"`, jeśli nazwa modelu wskazuje na OpenAI reasoning (`gpt-5...`, `o3...`, także z prefiksem typu `openai/gpt-5.4`). Dla natywnych modeli, np. `mistral-small-latest`, temperatura nadal jest wysyłana.

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
| `nvidia` | `meta/llama-3.3-70b-instruct`, `nvidia/llama-3.1-nemotron-70b-instruct` |
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
- `"temperature"` (opcjonalne) — temperatura tylko dla tego promptu (0.0–2.0); brak klucza = temperatura domyślna dostawcy. Niska (0.0–0.3) dla definicji i faktów, wyższa (0.7–1.0) dla przykładowych zdań. Fallback tego promptu również jej używa. W UI: Ustawienia → Generowanie AI → Prompty → pole „Temperatura" („— domyślna dostawcy" = brak nadpisania)
- `"manual_only"` (opcjonalne, `true`/`false`, domyślnie `false`) — pole wykluczone z batcha "Wszystkie puste", workflow oraz głównego przycisku AI w edytorze. Dostępne tylko przez jawne wskazanie: submenu "Generuj zablokowane ▸" w przeglądarce lub PPM na polu w edytorze.

W promptach dostępne są:
- `{{nazwa_pola}}` — wstawi wartość pola karty
- `{% if pole %} ... {% else %} ... {% endif %}` — warunek

Pola które już mają zawartość są automatycznie pomijane.

---

---

## Sekcja `audio_normalizer` — normalizacja audio

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Konserwacja → Normalizacja audio**.

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

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Reguły kart → Presety powtórek**.

**`deck_name`** — nazwa **bazowa** talii filtrowanej; wybrany preset dokleja do niej swoją etykietę (np. `... — Uczone w ostatnich 7 dniach`). Domyślnie `"Angielski - Powtórka z wyprzedzeniem"`.

Akcja: **Narzędzia → Anki Toolkit → Utwórz talię filtrowaną (preset)...** — otwiera dialog z listą predefiniowanych presetów (7/30 dni, wszystkie uczone, trudne karty `rated:30:1`, losowe) oraz polem **Limit kart** (podpowiada domyślny limit presetu, `0` = bez limitu). Tworzy/rebuduje talię (`col.sched.rebuild_filtered_deck`). Presety obejmują całą kolekcję (brak filtra `deck:`), zawsze z kolejnością losową i `reschedule=false`.

```json
"filtered_deck": {
    "deck_name": "Angielski - Powtórka z wyprzedzeniem"
}
```

---

## Sekcja `nbsp_remover` — czyszczenie HTML w kolekcji

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Konserwacja → Czyszczenie HTML**.

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

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Workflowy → Rozdzielanie pól**.

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

## Sekcja `sibling_manager` — dynamiczne zawieszanie siblingów

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Reguły kart → Odblokowywanie**.

**`interval`** — próg dojrzałości w dniach (domyślnie `30`). Karta z interval poniżej progu jest uznawana za immature — jej NEW siblingi są zawieszone. Gdy interval osiągnie próg, wszystkie zawieszone siblingi są uwalniane na raz.

**`tag`** — tag dodawany do notatki gdy ma zawieszone siblingi (domyślnie `"tk-sib-suspended"`). Używany do szybkiego wyszukiwania notatek z zawieszonymi siblingami i do batch scan po syncu. Tag jest usuwany gdy wszystkie siblingi zostaną uwolnione.

**`ignore_tag`** — notatki z tym tagiem są pomijane przez moduł (domyślnie `"tk-sib-ignored"`). Przydatne gdy masz notatki których siblingi chcesz widzieć wszystkie naraz (np. karty z minimalnymi różnicami).

**`show_tooltip`** — `true` (domyślnie) = po sync catch-up pokazuje tooltip "Sibling Manager: zawieszono X, odwieszono Y" (gdy coś zrobiono). `false` = wyłącza tooltip, ale logi z licznikami nadal trafiają do bufora (**Ustawienia → Diagnostyka → Logi**).

```json
"sibling_manager": {
    "interval": 30,
    "tag": "tk-sib-suspended",
    "ignore_tag": "tk-sib-ignored",
    "show_tooltip": true
}
```

Akcje:
- **Narzędzia → Anki Toolkit → Uwolnij karty zawieszone przez Sibling Manager...** — reset wszystkich zawieszeń + usuwa tagi (jeden krok undo)
- **Narzędzia → Anki Toolkit → Sibling Manager: przeskanuj całą kolekcję (zawieś/uwolnij siblingi)...** — ręczny batch scan (ten sam co auto po syncu)

---

## Sekcja `sentence_unlocker` — stopniowe odblokowywanie zdań

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Reguły kart → Odblokowywanie** — całość edytowalna z UI, w tym `main_templates` (przecinkami) i `chain` (pary `pole-nauka:pole-tak`).

Gdy karty główne notatki dojrzeją, moduł wpisuje znacznik do pola `pX-tak`, co powoduje wygenerowanie karty-ćwiczenia „Uzupełnij" (szablon `pX-nauka` renderuje się tylko przy `{{#pX-tak}}{{#pX-nauka}}`). Odblokowywanie jest **stopniowe**: kolejne zdanie czeka, aż karta poprzedniego dojrzeje.

**`model`** — typ notatki, którego dotyczy moduł (domyślnie `"angielski"`). Karty innych modeli są ignorowane.

**`threshold`** — próg dojrzałości karty w dniach (domyślnie `21`, `ivl ≥ threshold`).

**`marker`** — wartość wpisywana do pola `-tak` (domyślnie `"tak"`; wystarczy cokolwiek niepustego).

**`main_templates`** — nazwy kart głównych, których dojrzałość odblokowuje pierwsze zdanie (domyślnie `["ang-pol", "pol-ang"]` — muszą dojrzeć **oba**).

**`chain`** — lista zdań w kolejności odblokowywania; każde to `{"nauka_field", "tak_field"}`. `nauka_field` musi być jednocześnie nazwą szablonu karty tego zdania (w modelu `angielski` się pokrywają) — po niej moduł sprawdza dojrzałość karty bramkującej następne zdanie.

**`ignore_tag`** — notatki z tym tagiem są pomijane (domyślnie `"tk-unlock-ignored"`).

**`done_tag`** — tag dodawany do notatek w pełni odblokowanych (i tych bez żadnego zdania), aby batch scan je pomijał (domyślnie `"tk-unlock-done"`).

**`show_tooltip`** — `true` (domyślnie) = tooltip z liczbą odblokowanych zdań po skanowaniu.

> ⚠️ Jednokierunkowo: znacznik **nigdy nie jest usuwany**. Wyczyszczenie `pX-tak` skasowałoby już wygenerowaną kartę razem z jej historią powtórek.

```json
"sentence_unlocker": {
    "model": "angielski",
    "threshold": 21,
    "marker": "tak",
    "main_templates": ["ang-pol", "pol-ang"],
    "chain": [
        {"nauka_field": "p1-nauka", "tak_field": "p1-tak"},
        {"nauka_field": "p2-nauka", "tak_field": "p2-tak"},
        {"nauka_field": "p3-nauka", "tak_field": "p3-tak"}
    ],
    "ignore_tag": "tk-unlock-ignored",
    "done_tag": "tk-unlock-done",
    "show_tooltip": true
}
```

Akcja: **Narzędzia → Anki Toolkit → Sentence Unlocker: przeskanuj kolekcję (odblokuj zdania)...** — ręczny batch scan (ten sam co auto po syncu). Reactive po każdej odpowiedzi na desktopie + auto po `sync_did_finish`.

---

## Sekcja `deck_router` — kierowanie kart do talii wg tagu

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Reguły kart → Kierowanie do talii** — reguły dodajesz/usuwasz w tabeli (szablon i talia z list rozwijanych), bez ręcznej edycji JSON.

Natywny Deck Override w Anki działa tylko per-szablon karty — nie da się nim rozdzielić kart z tego samego szablonu na różne talie w zależności od tagu. Ten moduł dokłada kierowanie **per-tag**: gdy notatka ma skonfigurowany tag, jej pasujące karty są przenoszone do talii z reguły (nadpisując natywny override dla tych kart). Notatki bez pasującej reguły nie są ruszane.

**`rules`** — lista reguł. Każda reguła:

- **`tag`** — tag, który musi być na notatce, żeby reguła zadziałała.
- **`deck`** — nazwa talii docelowej (tworzona automatycznie, jeśli nie istnieje). Zagnieżdżenie przez `::`, np. `"Angielski::Osobne"`.
- **`template`** *(opcjonalne)* — nazwa szablonu karty (np. `"pol-ang"`). Pominięty, pusty lub `"*"` = wszystkie karty notatki. Podany = tylko karty z tego szablonu — reszta kart notatki zostaje wg natywnego override.

Reguły są sprawdzane po kolei — **pierwsza pasująca wygrywa** dla danej karty. Reguły węższe (z `template`) umieszczaj przed szerszymi (bez `template`).

```json
"deck_router": {
    "rules": [
        {"tag": "abc123", "template": "pol-ang", "deck": "Angielski::Osobne::pol-ang"},
        {"tag": "abc123", "deck": "Angielski::Osobne"}
    ]
}
```

Kiedy się odpala:
- przy dodawaniu karty w oknie **Dodaj**,
- po AI-batchu/workflow w przeglądarce (dla zmienionych notatek),
- ręcznie: **Narzędzia → Anki Toolkit → Deck Router: uporządkuj istniejące karty...** albo przycisk **Uporządkuj istniejące karty…** w zakładce Deck Router (działa na regułach z tabeli, także niezapisanych) — przechodzi po wszystkich notatkach z tagami z reguł i przenosi ich karty.

---

## Sekcja `workflows` — nazwane workflowy

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Workflowy**. Każdy workflow to jedna pozycja w menu PPM (przeglądarka) i opcjonalnie przycisk w edytorze.

Lista nazwanych workflowów. Każdy:

**`name`** — nazwa pokazywana w menu PPM i na przycisku edytora (np. `"Generuj fiszkę"`).

**`editor_button`** — `true` = workflow dostaje własny przycisk w toolbarze edytora. `false` (domyślnie dla pipeline'ów) = dostępny tylko z PPM w przeglądarce.

**`steps`** — lista kroków wykonywanych sekwencyjnie na pojedynczej notatce. Każdy krok:
- `"module"` — `"ai"`, `"dictionary"`, `"tts"` albo `"field_splitter"`
- `"action"` — `"generate"` (AI/TTS), `"fetch"` (dictionary) albo `"split"` (field_splitter)
- `"dicts"` — dla kroku dictionary: lista słowników (np. `["oxford_uk", "oxford_us"]`)
- `"fields"` — dla kroku AI: `"empty"` (domyślnie — wszystkie puste pola, pomija `manual_only`), `"manual"` (pola `manual_only`) albo lista konkretnych pól (np. `["p1-nauka", "p2-nauka"]`)

```json
"workflows": [
    {
        "name": "Generuj fiszkę",
        "editor_button": true,
        "steps": [
            {"module": "ai",         "action": "generate", "fields": "empty"},
            {"module": "dictionary", "action": "fetch", "dicts": ["oxford_uk", "oxford_us"]},
            {"module": "tts",        "action": "generate"}
        ]
    },
    {
        "name": "Generuj wszystko: puste → TTS → rozdziel → zablokowane",
        "editor_button": false,
        "steps": [
            {"module": "ai",             "action": "generate", "fields": "empty"},
            {"module": "tts",            "action": "generate"},
            {"module": "field_splitter", "action": "split"},
            {"module": "ai",             "action": "generate", "fields": "manual"}
        ]
    }
]
```

Kroki wykonują się w tle; notatka jest łapana raz na starcie (przełączenie karty w edytorze w trakcie nie miesza danych). W kroku TTS pliki audio są generowane równolegle przez `ThreadPoolExecutor`.

**Migracja:** stara, pojedyncza sekcja `workflow` jest automatycznie konwertowana na `workflows` przy starcie (`migrate_workflows()`) — z dosadzeniem dwóch domyślnych pipeline'ów, więc menu nic nie traci.

---

## Sekcja `context_menu` — widoczność wbudowanych sekcji PPM

Konfiguracja przez **Ustawienia → zakładka Workflowy** (checkboxy na dole). Steruje tylko auto-generowanymi sekcjami menu PPM — workflowy są zawsze widoczne. Każdy klucz `true`/`false` (domyślnie `true`):

- `"dictionary"` — sekcja „Pobierz wymowę"
- `"tts"` — sekcja „TTS"
- `"ai_fields"` — submenu „Generuj pola"
- `"ai_blocked"` — submenu „Generuj zablokowane"
- `"field_splitter"` — pozycja „Rozdziel pole"

```json
"context_menu": {
    "dictionary": true,
    "tts": true,
    "ai_fields": true,
    "ai_blocked": true,
    "field_splitter": true
}
```

Odczytywane świeżo przy każdym kliknięciu PPM — zmiana działa bez restartu Anki.

---

## Sekcja `word_queue` — kolejka słówek z n8n DataTable

Konfiguracja przez **Ustawienia → Integracje → Kolejka słówek**. Klucz API zapisywany jest w `meta.json` w profilu Anki — `config.json` w repo trzyma puste wartości domyślne.

```json
"word_queue": {
    "n8n_url": "",
    "fallback_url": "",
    "api_key": "",
    "table_id": "",
    "word_field": "ang",
    "word_column": "Slowko",
    "flag_column": "Anki",
    "link_columns": {"diki": "URL", "Longman": "Longman", "Oxford": "Oxford"},
    "page_size": 250,
    "max_rows": 5000,
    "random_order": false
}
```

- **`n8n_url`** — adres n8n w sieci domowej, próbowany jako pierwszy (np. `http://192.168.1.50:5678`).
- **`fallback_url`** — adres zapasowy, używany gdy domowy nie odpowiada (np. Tailscale MagicDNS `https://n8n.twoj-tailnet.ts.net`, bez portu). Kolejność prób: ostatni działający → domowy → zapasowy; zwycięzca jest zapamiętywany do końca sesji.
- **`api_key`** — klucz z n8n → **Settings → API → Create API Key**.
- **`table_id`** — identyfikator tabeli (**nie** nazwa). Wybierasz z rozwijanki po kliknięciu „Pobierz listę".
- **`word_field`** — pole notatki, do którego wpisywane jest hasło (domyślnie `ang`; to samo, co `FIELDS.headword` w userscripcie `web_bridge`).
- **`word_column`** — kolumna tabeli z hasłem. Musi być unikatowa, jeśli korzystasz z odhaczania przy zamkniętym panelu (`filter eq` odhaczyłby wszystkie duplikaty).
- **`flag_column`** — kolumna typu `boolean`; `false` = do zrobienia. Panel ustawia ją na `true` po dodaniu karty i z powrotem na `false` po odznaczeniu ptaszka.
- **`link_columns`** — mapa: etykieta zakładki → kolumna z URL-em. Kolejność kluczy wyznacza kolejność zakładek. Wiersz z pustą kolumną → zakładka wyszarzona.
- **`page_size`** — rozmiar strony przy pobieraniu. **Maksimum akceptowane przez n8n to 250** (większe → `HTTP 400`).
- **`max_rows`** — bezpiecznik pętli stronicowania po kursorze.
- **`random_order`** — startowy stan checkboxa „Losowo" w panelu (tasowanie kolejności listy).

---

## Sekcja `debug` — logowanie wtyczki

Konfiguracja przez **Narzędzia → Anki Toolkit → Ustawienia... → Diagnostyka → Logi**.

**`enabled`** — `true` = włącza logowanie na poziomie DEBUG (szczegółowe logi HTTP, parsery, statystyki); `false` (domyślnie) = tylko WARNING i wyżej. Może być przełączane live w UI bez restartu Anki (`common.debug_log.set_debug()`).

```json
"debug": {
    "enabled": false
}
```

Logi są buforowane w pamięci (deque 2000 wpisów) — dostępne w zakładce Logi z przyciskami Odśwież i Wyczyść.
