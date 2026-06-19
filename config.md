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
    "nbsp_remover":      true
}
```

---

## Sekcja `dictionary` — pobieranie audio i IPA

**`source_field`** — nazwa pola karty zawierającego angielskie słowo (np. `"ang"`).

**`target_field`** — nazwa pola, do którego trafia audio `[sound:...]` (np. `"audio"`).

**`ipa_field`** — nazwa pola dla transkrypcji IPA. Pozostaw pusty string `""` aby wyłączyć.

**`wiktionary_ipa_fallback`** — `true` (domyślnie) = gdy Oxford/Cambridge nie znajdzie IPA dla słowa, automatycznie odpyta Wiktionary API. `false` = wyłącza fallback, pole IPA zostaje puste gdy primary source nie zwróci wyników. Wiktionary dostarcza tylko IPA — nie ma audio.

**`ipa_format`** — format zapisu IPA:
- `"compact"` — `/θɔːt/` (jeśli UK=US) lub `UK: /θɔːt/ • US: /θɑːt/`
- `"both"` — zawsze `UK: /.../ • US: /.../`
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

## Sekcja `tts` — generowanie audio przez Kokoro TTS

Konfiguracja wyłącznie przez edycję `config.json`. Akcje TTS dostępne przez **prawy klik w przeglądarce → TTS: ...**.

**`api_url`** — adres lokalnego serwera Kokoro (domyślnie `http://localhost:8880/v1/audio/speech`).

**`model`** — nazwa modelu Kokoro (domyślnie `"kokoro"`).

**`voices`** — lista głosów biorących udział w losowaniu. Każda notatka/zdanie dostaje losowo wybrany głos z tej listy.

**`speed`** — tempo mowy (0.1–3.0, domyślnie 0.9).

**`ang_source_field`** / **`ang_target_field`** / **`przyklad_target_field`** — *legacy.* Czytane z zapisanego configu **tylko** gdy klucz `tasks` w ogóle nie istnieje — służą do zbudowania domyślnej listy zadań dla starych instalacji. Nie są już w domyślnym configu (`_DEFAULTS`) ani w UI; nowe instalacje używają wyłącznie listy `tasks`. Wystarczy raz zapisać ustawienia w UI, by `tasks` stało się jedynym źródłem.

**`max_workers`** — liczba równoległych wątków generowania audio. Domyślnie `12`. Zmniejsz przy problemach z wydajnością lub przy słabszym serwerze Kokoro.

**`max_retries`** — liczba prób przy błędach API (429, 5xx). Domyślnie `3`.

**`timeout`** — timeout pojedynczego żądania TTS w sekundach. Domyślnie `60`.

---

## Sekcja `ai_generator` — generowanie pól przez AI

**`button_label`** — etykieta przycisku AI w edytorze kart.

**`batch_limit`** — liczba kart w jednej grupie w trybie batch. Co `batch_limit` kart następuje przerwa `batch_sleep` sekund. Wszystkie zaznaczone karty są zawsze przetwarzane — ten parametr kontroluje tylko rytm pauz.

**`batch_sleep`** — pauza w sekundach między grupami kart w trybie batch (zapobiega limitom API).

**`parallel_requests`** — liczba notatek przetwarzanych równolegle w batchu przeglądarki. Domyślnie `3`. Wyższe wartości przyspieszają batch, ale zwiększają ryzyko limitów API (429).

**`max_retries`** — liczba prób przy błędach API (429, 5xx). Domyślnie `3`. Dotyczy wszystkich providerów.

**`request_timeout`** — timeout pojedynczego żądania do API AI w sekundach. Domyślnie `30`.

---

### Providerzy (`providers`)

Każdy provider wymaga:
- `"api_key"` — klucz API
- `"model"` — nazwa modelu
- `"temperature"` — losowość odpowiedzi (0.0–1.0, zalecane 0.2)

OpenAI obsługuje dodatkowe pole:
- `"reasoning_effort"` — poziom reasoning dla modeli, które go obsługują: `"none"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`; domyślnie `"medium"`. Przy modelach bez obsługi reasoning parametr nie jest wysyłany do API. Przy modelach reasoning OpenAI parametr `"temperature"` również nie jest wysyłany, bo część tych modeli nie obsługuje niestandardowej temperatury.

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

Klucz API dla `google` uzyskasz na [Google AI Studio](https://aistudio.google.com/apikey).

---

### Typy notatek (`note_types`)

Klucz to nazwa typu notatki (dokładnie jak w Anki). Każde pole to obiekt z:
- `"target"` — nazwa pola karty do wypełnienia
- `"provider"` — provider AI dla tego pola (wymagany)
- `"prompt"` — treść prompta

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

```json
"audio_normalizer": {
    "ffmpeg_path": "",
    "loudnorm_opts": "loudnorm=I=-14:TP=-1.5:LRA=8",
    "max_workers": 4
}
```
