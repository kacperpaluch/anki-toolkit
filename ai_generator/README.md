# AI Generator — generowanie pól kart przez AI

Automatycznie wypełnia pola kart Anki przez API modeli językowych. Obsługuje wielu dostawców AI — każde pole karty może korzystać z innego modelu.

## Jak używać

### Edytor kart
Główna akcja w toolbarze to zwykle **Generuj fiszkę** z workflow AI → Słownik → TTS. Przycisk **AI** zostaje jako akcja pomocnicza: generuje tylko pola AI dla aktualnie otwartej karty.

Działa asynchronicznie — Anki nie zamarza podczas oczekiwania na API. W międzyczasie możesz swobodnie edytować inne pola. Po zakończeniu:
- Edytor odświeża się automatycznie po zakończeniu generowania
- **Pola docelowe AI** są zawsze nadpisywane wynikiem — kliknięcie przycisku AI to wyraźna intencja wypełnienia tych pól
- **Pola których AI nie dotyka** (np. wpisujesz coś w polu `pol` podczas gdy AI generuje `def`) są zachowane — `saveNow` synchronizuje je przed odświeżeniem
- Pojawia się tooltip z błędem API, jeśli dostawca zwróci błąd; **"Brak pól do wygenerowania."** oznacza brak pustych/skonfigurowanych pól do uzupełnienia
- Kliknięcie przycisku podczas trwającej generacji pokazuje tooltip **"Generowanie już trwa..."** — podwójne kliknięcie jest ignorowane
- Jeśli w trakcie generowania przełączysz się na inną kartę, wynik trafia do **właściwej notatki** (zapis bezpośrednio do kolekcji) — nie do aktualnie wyświetlanej

### Workflow "Generuj fiszkę"

Przycisk w toolbarze edytora (pokazuje się gdy workflow ma skonfigurowane kroki). Uruchamia AI → Słownik → TTS sekwencyjnie. Konfiguracja w **Ustawienia → AI Generator → Workflow**:
- Dodawaj kroki przyciskami **+ AI**, **+ Słownik**, **+ TTS**
- Przy **+ Słownik** otwiera się okno wyboru słowników (checkboxy Diki, Oxford, Cambridge, Longman)
- Zmieniaj kolejność ▲▼, usuwaj kroki
- Etykieta przycisku konfigurowalna; domyślnie **Generuj fiszkę**

Kroki wykonują się sekwencyjnie w tle. Każdy krok czeka na poprzedni. Notatka jest łapana raz na starcie workflow — przełączenie karty w edytorze w trakcie nie miesza danych między notatkami.

### Przeglądarka (batch)
Zaznacz notatki → **menu kontekstowe → Anki Toolkit → Generuj pola**.

- Pola które już mają treść są **zawsze pomijane** — generator uzupełnia tylko puste pola.
- Jeśli nie zaznaczysz żadnych notatek, pojawi się krótki tooltip z informacją.
- Anki **nie zamraża się** podczas przetwarzania — batch działa w tle.
- Widoczny pasek postępu z licznikiem i przycisk **Anuluj**.
- Po zakończeniu jeden tooltip z podsumowaniem, np. `"Zaktualizowano: 12"`, `"Zaktualizowano: 8 · przerwano"` albo licznik błędów z ostatnim błędem API.

## Konfiguracja (`config.json` → sekcja `ai_generator`)

### Podstawowe ustawienia

```json
"ai_generator": {
    "button_label": "AI",
    "skip_tags": ["skip-ai"],
    "batch_limit": 3,
    "batch_sleep": 1.0,
    "max_retries": 3,
    "request_timeout": 30,
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
| `max_retries` | Liczba prób przy błędach API — HTTP 429/5xx, timeouty, błędy połączenia (domyślnie `3`) |
| `request_timeout` | Timeout pojedynczego żądania do API w sekundach (domyślnie `30`) |

### Konfiguracja dostawców

W UI dostawcy są w **Ustawienia → AI Generator → Dostawcy**. Każdy dostawca ma własną podzakładkę, żeby nie pokazywać wszystkich kluczy i modeli naraz. Limity paczek, przerwy, ponowienia i timeouty są w sekcji **Zaawansowane**.

```json
"providers": {
    "openai": {
        "api_key": "sk-...",
        "model": "gpt-4o",
        "temperature": 0.2,
        "reasoning_effort": "medium"
    },
    "anthropic": {
        "api_key": "sk-ant-...",
        "model": "claude-3-5-haiku-20241022",
        "temperature": 0.2,
        "max_tokens": 2048
    },
    "google": {
        "api_key": "AIza...",
        "model": "gemini-2.0-flash",
        "temperature": 0.2
    },
    "opencode_go": {
        "api_key": "ocg-...",
        "model": "deepseek-v4-pro",
        "temperature": 0.6,
        "reasoning_effort": "max"
    }
}
```

`reasoning_effort` zachowuje się różnie w zależności od dostawcy:

- **openai / cometapi / openrouter** — dropdown z wartościami `none`, `minimal`, `low`, `medium`, `high`, `xhigh`. Wysyłany tylko dla modeli OpenAI reasoning (`o1/o3/o4`, `gpt-5+`). Modele reasoning nie dostają `temperature`. Fallback automatyczny jeśli model zwróci HTTP 400.
- **opencode_go** — wolny tekst (QLineEdit). Wartości różnią się per model: `max` dla DeepSeek V4 Pro, inne modele mają inne wartości lub nie obsługują reasoning. Puste pole = parametr nie jest wysyłany. Fallback automatyczny jeśli API zwróci błąd.
- **mistral** — nie obsługuje `reasoning_effort` (własne modele, nie proxy OpenAI).
- **anthropic / google** — nie mają pola `reasoning_effort` w UI.

`max_tokens` jest wymagany przez Anthropic API (inni dostawcy go ignorują). Domyślnie `2048`. Zwiększ jeśli generujesz długie odpowiedzi (np. rozbudowane przykłady zdań).

### Dostępni dostawcy

| Dostawca | Endpoint | Gdzie pobrać klucz API |
|---|---|---|
| `openai` | `api.openai.com` | platform.openai.com |
| `anthropic` | `api.anthropic.com` | console.anthropic.com |
| `google` | `generativelanguage.googleapis.com` | aistudio.google.com |
| `openrouter` | `openrouter.ai` | openrouter.ai/keys |
| `cometapi` | `api.cometapi.com` | cometapi.com |
| `mistral` | `api.mistral.ai` | console.mistral.ai |
| `opencode_go` | `opencode.ai/zen/go/v1` | opencode.ai/auth |

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
| `opencode_go` | `GET /zen/go/v1/models` | tak |

Po kliknięciu **Pobierz** pole modelu (edytowalny QComboBox) wypełnia się listą modeli. Nadal możesz wpisać model ręcznie jeśli wolisz. Lista jest cachowana — ponowne kliknięcie używa cache; zmiana klucza API powoduje ponowne pobranie.

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
| `opencode_go` | `deepseek-v4-pro` | Reasoning, tani w subskrypcji Go |
| `opencode_go` | `deepseek-v4-flash` | Bardzo tani, szybki |
| `opencode_go` | `kimi-k2.6` | Dobry do kodowania |
| `opencode_go` | `glm-5.1` | Alternatywa |

### Typy notatek

```json
"note_types": {
    "angielski": {
        "cz_mowy": {
            "target": "cz_mowy",
            "provider": "cometapi",
            "prompt": "Classify: EN: {{ang}} PL: {{pol}}"
        },
        "def": {
            "target": "def",
            "provider": "openai",
            "prompt": "Write a definition for: {{ang}}"
        }
    }
}
```

- Klucz zewnętrzny (`"angielski"`) — nazwa typu notatki **dokładnie jak w Anki**
- Klucz wewnętrzny (`"cz_mowy"`) — **nazwa zadania**: dowolny identyfikator, decyduje o kolejności generowania
- `target` — nazwa pola karty do wypełnienia
- `provider` — którego dostawcy użyć dla tego pola
- `prompt` — treść prompta z opcjonalnymi szablonami

## Szablony promptów

| Składnia | Działanie |
|---|---|
| `{{ang}}` | Wstawia wartość pola `ang` z karty |
| `{{pol}}` | Wstawia wartość pola `pol` z karty |
| `{% if def %}...{% endif %}` | Renderuje blok tylko gdy pole `def` jest niepuste |
| `{% if def %}...{% else %}...{% endif %}` | Wariant z fallbackiem |

Pola są generowane w kolejności wpisu w `note_types`. Wynik wcześniejszego pola można użyć w prompcie następnego przez `{{nazwa_pola}}`. Zmiana nazwy zadania w edytorze promptów zachowuje jego pozycję w kolejności.

> **Ograniczenie:** zagnieżdżone `{% if %}` wewnątrz `{% if %}` nie są obsługiwane.

> **Uwaga:** Wartości pól użyte w szablonach są pobierane na początku generowania (przed wywołaniem API). Pola zawierające HTML (`<div>`, `&nbsp;` itp.) są automatycznie oczyszczane przed wstawieniem do promptu — AI otrzymuje czysty tekst.

## Dodanie nowego dostawcy

1. Utwórz `providers/moj_provider.py`:
```python
from .base import BaseProvider
from typing import Optional
import json

class MojProvider(BaseProvider):
    def call_api(self, prompt: str) -> Optional[str]:
        req = self._build_request(prompt)
        raw = self._request_with_retry(req)  # automatyczny retry dla 429/5xx
        if raw is None:
            return None
        res_data = json.loads(raw.decode("utf-8"))
        # Waliduj strukturę odpowiedzi przed dostępem
        # ...
        return wynik
```

2. Zarejestruj w `providers/__init__.py`:
```python
from .moj_provider import MojProvider
PROVIDERS = { ..., "moj_provider": MojProvider }
```

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

4. Dodaj nazwę do list `_PROVIDER_NAMES` w `settings/ai_generator_tab.py` i `settings/prompts_tab.py`

`BaseProvider.__init__` przyjmuje `max_retries`, `timeout`, `max_tokens` i `reasoning_effort` — są przekazywane automatycznie z konfiguracji. `max_tokens` jest opcjonalne (tylko Anthropic go używa). Jeśli nowy dostawca proxy'uje modele OpenAI, użyj `add_reasoning_effort_if_supported()` i `self._request_with_reasoning_fallback()` zamiast `_request_with_retry()` — otrzymasz automatyczny fallback gdy model nie obsługuje reasoning.
