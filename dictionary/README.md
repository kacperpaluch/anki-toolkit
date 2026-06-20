# Dictionary — pobieranie audio i IPA

Pobiera pliki audio MP3 z wymową oraz transkrypcje IPA z czterech słowników online. Działa w edytorze kart i przeglądarce.

## Jak używać

### Edytor kart
Przyciski słownikowe pojawiają się w toolbarze edytora. Kliknięcie przycisku (np. **Diki**) najpierw zapisuje bieżące pola (świeżo wpisane słowo jest od razu widoczne), pobiera audio w tle — Anki nie zamarza — i automatycznie je odtwarza.

**PPM na polu źródłowym** (np. `ang`) — gdy pole ma treść, pojawiają się pozycje „Pobierz wymowę: Diki", „Pobierz wymowę: Oxford" itd. (tylko włączone słowniki). Działa też w oknie dodawania nowej karty (AddCards).

### Przeglądarka (batch)
Zaznacz notatki → **menu kontekstowe → Anki Toolkit → Pobierz wymowę**.

W submenu dostępne są:
- **Wszystkie włączone słowniki** — używa wszystkich aktywnych pozycji z `buttons`
- **Pobierz z Diki / Oxford / ...** — uruchamia batch tylko dla wybranego przycisku/słownika

Anki **nie zamraża się** podczas przetwarzania — batch działa w tle. Widoczny pasek postępu z licznikiem i przycisk **Anuluj**.

### Inteligentne uzupełnianie

Moduł sprawdza stan pól przed pobraniem:

| Audio | IPA | Akcja |
|---|---|---|
| puste | puste | Pobierz audio + IPA |
| pełne | puste | Pobierz tylko IPA, tooltip "Pole audio już zawiera treść." |
| puste | pełne | Pobierz tylko audio |
| pełne | pełne | Nic nie rób |

## Dostępne słowniki

| Klucz | Słownik | Wariant |
|---|---|---|
| `oxford_uk` | Oxford Learner's Dictionaries | brytyjski |
| `oxford_us` | Oxford Learner's Dictionaries | amerykański |
| `cambridge_uk` | Cambridge Dictionary | brytyjski |
| `cambridge_us` | Cambridge Dictionary | amerykański |
| `diki_uk` | Diki.pl | brytyjski |
| `diki_us` | Diki.pl | amerykański |
| `longman_uk` | Longman LDOCE | brytyjski |
| `longman_us` | Longman LDOCE | amerykański |

Obsługa IPA: Oxford i Cambridge. Diki i Longman — tylko audio.

### Wiktionary — fallback IPA

Wiktionary **nie jest słownikiem audio** i nie pojawia się na liście przycisków. Służy wyłącznie jako automatyczna rezerwa dla IPA: gdy Oxford lub Cambridge nie zwróci transkrypcji dla danego słowa, moduł odpytuje Wiktionary API i używa jego wyniku.

Zachowanie kontrolowane przez ustawienie `wiktionary_ipa_fallback`:

| Wartość | Efekt |
|---|---|
| `true` (domyślnie) | Gdy primary IPA source zwróci `None`, zapytaj Wiktionary |
| `false` | Wyłącz fallback — pole IPA pozostaje puste gdy primary source nie znajdzie nic |

Wiktionary używa oficjalnego REST API (`en.wiktionary.org/w/api.php`) — nie scrapuje HTML. Nie ma opcji audio z Wiktionary.

## Konfiguracja (`config.json` → sekcja `dictionary`)

```json
"dictionary": {
    "source_field": "ang",
    "target_field": "audio",
    "ipa_field": "IPA",
    "ipa_format": "compact",
    "wiktionary_ipa_fallback": true,
    "diki_ipa_fallback": false,
    "diki_ipa_fallback_source": "wiktionary",
    "max_retries": 3,
    "page_timeout": 10,
    "mp3_timeout": 10,
    "buttons": [
        {"dictionaries": ["diki_uk", "diki_us"],    "label": "Diki",     "enabled": true},
        {"dictionaries": ["oxford_uk", "oxford_us"], "label": "Oxford",   "enabled": true},
        {"dictionaries": ["cambridge_uk", "cambridge_us"], "label": "Cambridge", "enabled": false},
        {"dictionaries": ["longman_uk", "longman_us"],     "label": "Longman",   "enabled": false}
    ]
}
```

| Pole | Opis |
|---|---|
| `source_field` | Pole z angielskim słowem (domyślnie `"ang"`) |
| `target_field` | Pole docelowe dla audio `[sound:...]` (domyślnie `"audio"`) |
| `ipa_field` | Pole docelowe dla IPA — puste `""` wyłącza IPA |
| `ipa_format` | Format zapisu IPA (patrz niżej) |
| `wiktionary_ipa_fallback` | `true` — gdy primary source nie znajdzie IPA, próbuje Wiktionary API |
| `diki_ipa_fallback` | `true` — gdy pobierasz audio z Diki, pobierz IPA z osobnego źródła |
| `diki_ipa_fallback_source` | Źródło IPA dla Diki: `wiktionary`, `oxford` albo `cambridge` |
| `max_retries` | Liczba prób przy błędach sieci — HTTP 429/5xx, timeouty, błędy połączenia (domyślnie `3`) |
| `page_timeout` | Timeout pobierania strony słownika w sekundach (domyślnie `10`) |
| `mp3_timeout` | Timeout pobierania pliku MP3 w sekundach (domyślnie `10`) |
| `buttons` | Lista przycisków w edytorze |

### Formaty IPA (`ipa_format`)

| Wartość | Przykład |
|---|---|
| `"compact"` | `/θɔːt/` gdy UK=US, lub `UK: /θɔːt/ • US: /θɑːt/` gdy różne |
| `"both"` | `UK: /θɔːt/ • US: /θɑːt/` zawsze |
| `"uk_only"` | `/θɔːt/` |
| `"us_only"` | `/θɑːt/` |

### Konfiguracja przycisków

Każdy przycisk to obiekt z:
- `"dictionaries"` — lista słowników do użycia przez ten przycisk. Podanie UK + US = dwa pliki audio zapisane w jednym polu
- `"label"` — tekst na przycisku
- `"enabled"` — `true` / `false`

Przykład przycisku z jednym słownikiem:
```json
{"dictionaries": ["oxford_uk"], "label": "Oxford UK", "enabled": true}
```

## Uwagi

- Gdy button zawiera `["oxford_uk", "oxford_us"]`, strona słownika jest pobierana **raz** — parsery UK i US działają na tym samym HTML; ta sama strona jest reużywana też do ekstrakcji IPA
- W trybie batch notatki z tym samym słowem **nie generują ponownych requestów** — wynik jest cache'owany w ramach jednej sesji batch
- Wyrażenia wielowyrazowe (np. "look forward to") są w pełni obsługiwane — spacje zamieniane są na `_` przy porównaniu z URL
- Jeśli słownik nie zwróci audio, w edytorze pojawia się krótki tooltip; w trybie batch jedno podsumowanie `"Zaktualizowano: N · Brak audio: M"`
- Lista pozycji w submenu przeglądarki jest budowana z włączonych pozycji `buttons`, więc odpowiada temu co masz skonfigurowane w ustawieniach
- Oxford i Cambridge wymagają parsowania HTML strony — zmiany w strukturze strony słownika mogą wymagać aktualizacji kodu
