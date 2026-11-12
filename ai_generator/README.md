# Prompty AI (`ai_generator/`)

Wypełnia pola kart przez modele językowe. Każde pole ma własny prompt,
dostawcę i model. Prompty ustawiasz w **Ustawienia → Prompty AI**, a klucze,
modele domyślne i limity dostawców w **Ustawienia → Konta i klucze**.

## Gdzie to jest

**Edytor → Toolkit ▾**
- **Uzupełnij puste pola AI** wypełnia puste pola, które mają prompt. Pomija pola „Tylko na żądanie”.
- Prawy klik na polu z promptem → **Wygeneruj `pole` przez AI** (puste) albo **Wygeneruj ponownie** (nadpisuje).
- Sekwencje pasujące do notatki. Własny przycisk dostają przez **Toolkit ▾ → Przypnij do paska**.

Generowanie działa w tle na kopii notatki. Jeśli w tym czasie zmienisz jakieś
pole, wynik jest pomijany (mógł powstać ze starych danych), a dymek mówi, które pola
pominięto. Przełączenie na inną kartę nie miesza wyników między notatkami.

**Przeglądarka → prawy klik → Anki Toolkit → Wygeneruj pola AI…** otwiera okno
z listą pól. Pola automatyczne są zaznaczone, pola „tylko na żądanie” zaznaczasz
sam. **Nadpisz pola, które mają już treść** pyta o potwierdzenie, a błąd
generowania zostawia starą treść. Praca idzie w tle z paskiem postępu Anki, a wynik
to jeden krok cofania. Na końcu dostajesz raport: zapisane notatki, błędy,
pominięcia i konflikty (notatka zmieniona w trakcie). Raport trafia też do
**Ustawienia → Diagnostyka**, gdzie przycisk **Ponów nieudane** powtarza tylko
notatki z błędem.

## Sekwencje

Sekwencja to nazwany ciąg kroków: **AI**, **Wymowa**, **Nagranie**, **Rozdziel**.
Ustawiasz ją w **Ustawienia → Sekwencje**. Tam też włączasz i wyłączasz sekcje
menu prawego kliku. W edytorze kroki idą po kolei. W przeglądarce notatki są
przetwarzane równolegle, a kroki jednej notatki po kolei. Sekwencja jest widoczna
w menu, gdy przynajmniej jeden jej krok pasuje do notatki.

## Prompty

```json
"note_types": {
    "angielski": {
        "def": {
            "target": "def",
            "provider": "claude_cli",
            "model": "opus",
            "prompt": "Write a definition for: {{ang}}"
        }
    }
}
```

| Klucz | Znaczenie |
|---|---|
| klucz zewnętrzny | Nazwa typu notatki, dokładnie jak w Anki |
| klucz wewnętrzny | Nazwa promptu; kolejność promptów = kolejność generowania |
| `target` | Pole do wypełnienia |
| `provider`, `model` | Dostawca i model; pusty model = model domyślny dostawcy |
| `fallback_provider`, `fallback_model` | Model zapasowy (opcjonalnie) |
| `temperature` | Temperatura tylko dla tego promptu; brak = domyślna dostawcy. CLI ją pomija |
| `manual_only` | „Tylko na żądanie”: pomijane przy uzupełnianiu wszystkich pól i w sekwencjach |
| `prompt` | Treść promptu |

Składnia promptu:

| Składnia | Działanie |
|---|---|
| `{{ang}}` | Wartość pola `ang` (bez HTML) |
| `{% if def %}…{% endif %}` | Blok tylko gdy pole `def` nie jest puste |
| `{% if def %}…{% else %}…{% endif %}` | Wariant z alternatywą |

Prompt może użyć wyniku wcześniejszego zadania (`{{def}}`). Pole czeka tylko na
pola, których używa; pozostałe generują się równolegle. Zagnieżdżone `{% if %}`
nie są obsługiwane.

Edytor promptów ma przyciski **Wstaw pole ▾** i **Wstaw warunek ▾** oraz
ostrzega przed nieistniejącym typem notatki lub polem, nieznanymi `{{polami}}`
i błędną strukturą `{% if %}`. **Ustaw te modele we wszystkich promptach…**
kopiuje dostawcę i model (główne i zapasowe) do promptów widocznych na liście.

## Dostawcy

| Dostawca | Klucz | Uwagi |
|---|---|---|
| `openai` | platform.openai.com | `reasoning_effort` tylko dla modeli reasoning |
| `anthropic` | console.anthropic.com | `max_tokens` (domyślnie 2048) tylko w `config.json` |
| `openrouter` | openrouter.ai/keys | modele `:free` mają limit 20 RPM |
| `codex_cli` | bez klucza — `codex login` | subskrypcja ChatGPT |
| `claude_cli` | bez klucza — `claude auth login` | subskrypcja Claude (Pro/Max) |

Przy każdym dostawcy ustawiasz model domyślny i **poziom rozumowania**. Poziom
dotyczy wszystkich promptów tego dostawcy, a model zapasowy używa poziomu swojego
dostawcy. W sekcji **Zaawansowane** są temperatura, model zapasowy dostawcy,
limity RPM i równoległości oraz (dla CLI) ścieżka binarki i limit czasu.
Przycisk **Pobierz** ściąga listę modeli; lista jest zapamiętywana w konfiguracji.

### Dostawcy CLI

`codex_cli` i `claude_cli` uruchamiają zalogowanego klienta `codex` albo `claude`
i zużywają limity subskrypcji. Dodatek nie widzi tokenu logowania.

- Pusta ścieżka binarki = autodetekcja w `PATH` i typowych katalogach (`/opt/homebrew/bin`,
  `~/.local/bin` itd.), bo Anki z Findera nie dziedziczy `PATH` z powłoki.
- Proces dostaje tylko `PATH`, `HOME`, `USER`/`LOGNAME` i ustawienia regionalne,
  więc klucze API dodatku nie trafiają do CLI.
- Treść notatek to dane niezaufane. Claude CLI działa z `--tools ""` (bez narzędzi,
  plików i sieci), bez MCP, bez zapisu sesji i w pustym katalogu. Codex CLI działa
  w sandboksie `read-only`, w pustym katalogu, bez konfiguracji użytkownika i bez zapisu sesji.
- `claude_cli` przyjmuje alias (`haiku`, `sonnet`, `opus`, `fable`) albo pełne ID modelu.
  `system_prompt` zastępuje prompt Claude Code, co obniża narzut do ok. 280 tokenów na fiszkę.
- `codex_cli` dodaje do każdego wywołania kilka tysięcy tokenów preambuły, a konto
  ChatGPT zwykle odrzuca modele `*-codex-*`.

### Model zapasowy

Gdy model główny zawiedzie (błąd API, limit, pusta odpowiedź), dodatek uruchamia
model zapasowy z tym samym promptem i temperaturą:

1. `fallback_model` promptu (z `fallback_provider` albo tym samym dostawcą),
2. w przeciwnym razie `fallback_model` dostawcy,
3. bez obu — błąd.

### Limity tempa

`rpm` rozkłada żądania równo (`60/rpm` s odstępu), `max_concurrent` ogranicza
liczbę jednoczesnych żądań, a `rate_limit_free_only` (OpenRouter) dotyczy tylko
modeli `:free`. Limity obejmują model główny i zapasowy.

## Ustawienia ogólne (`ai_generator`)

| Klucz | Znaczenie |
|---|---|
| `skip_tags` | Notatki z tymi tagami są pomijane w całości |
| `batch_limit`, `batch_sleep` | Przeglądarka: przerwa `batch_sleep` s co `batch_limit` notatek |
| `parallel_requests` | Równoległe notatki w przeglądarce i pola jednej notatki (1–16) |
| `max_retries` | Próby przy 429 i braku połączenia. Timeout i 5xx nie są ponawiane, bo zapytanie mogło już zostać policzone |
| `request_timeout` | Limit czasu żądania HTTP; CLI ma własny `cli_timeout` |

W UI: **Prompty AI → Ogólne** (tagi i sekcja **Zaawansowane**).

## Nowy dostawca (dla deweloperów)

API zgodne z OpenAI Chat Completions wymaga tylko klasy w `providers/__init__.py`:

```python
class MojProvider(OpenAICompatProvider):
    API_URL = "https://api.example.com/v1/chat/completions"
    LABEL = "Moj Provider"
```

Inny format: dziedzicz po `BaseProvider` i zaimplementuj `call_api()`
(`self._post()` ponawia 429 i niewysłane żądania, gotowe parsery to `_parse_chat_completion()` i `_parse_messages()`).
Potem dopisz klasę do `PROVIDERS` i `PROVIDER_LABELS`, sekcję dostawcy do `config.json`
i, dla przycisku **Pobierz**, gałąź w `providers/model_discovery.py`.

Batch API (tryb tańszy) usunięto; kod jest w tagu Git `archive/batch-api`.
