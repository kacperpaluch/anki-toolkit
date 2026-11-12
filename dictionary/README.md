# Wymowa ze słowników (`dictionary/`)

Pobiera nagrania MP3 i transkrypcję IPA dla pojedynczych słów z Diki, Oxford,
Cambridge i Longman. Ustawienia są w **Ustawienia → Wymowa ze słowników**.
Krok „Wymowa” jest też dostępny w sekwencjach.

## Gdzie to jest

- **Edytor → przyciski D (Diki), O (Oxford)** albo **Toolkit ▾ → Pobierz wymowę: …** — pobiera wymowę w tle i ją odtwarza. Co jest przyciskiem, ustawiasz w **Toolkit ▾ → Przypnij do paska**.
- **Prawy klik na polu źródłowym lub docelowym** → **Pobierz wymowę: …**.
- **Przeglądarka → prawy klik → Anki Toolkit → Pobierz wymowę** — jeden słownik albo
  **Wszystkie włączone słowniki**; praca idzie z paskiem postępu i przyciskiem Anuluj.

Pozycje w menu to grupy zaznaczone w sekcji **Słowniki w menu**.

## Co jest pobierane

| Audio | IPA | Akcja |
|---|---|---|
| puste | puste | audio i IPA |
| pełne | puste | tylko IPA |
| puste | pełne | tylko audio |
| pełne | pełne | nic |

Pole z samym `<br>` lub `&nbsp;` liczy się jako puste, pole z obrazkiem jako pełne.
Plik ma stałą nazwę (`dict_<źródło>_<słowo>_<skrót>.mp3`), więc słowo, które
już ma nagranie w mediach, nie jest pobierane drugi raz. Żeby wymusić nowe
pobranie, usuń plik z mediów. Błąd jednej notatki nie przerywa pracy na reszcie.

IPA dają Oxford i Cambridge. Gdy nie znajdą transkrypcji, moduł pyta Wiktionary
(`wiktionary_ipa_fallback`). Diki i Longman dają tylko audio; dla Diki IPA może
pochodzić z osobnego źródła (`diki_ipa_fallback`).

## Konfiguracja (`dictionary`)

| Klucz | Znaczenie |
|---|---|
| `source_field` | Pole ze słowem (domyślnie `ang`) |
| `target_field` | Pole na `[sound:…]` (domyślnie `audio`) |
| `ipa_field` | Pole na IPA; puste wyłącza IPA |
| `ipa_format` | `compact` (`/θɔːt/` albo `UK: … • US: …`, gdy się różnią), `both`, `uk_only`, `us_only` |
| `wiktionary_ipa_fallback` | IPA z Wiktionary, gdy Oxford/Cambridge nic nie zwrócą |
| `diki_ipa_fallback`, `diki_ipa_fallback_source` | IPA dla Diki z `wiktionary`, `oxford` albo `cambridge` |
| `max_retries`, `page_timeout`, `mp3_timeout` | Ponowienia i limity czasu (sekcja **Zaawansowane (sieć)**) |
| `buttons` | Grupy słowników: `dictionaries`, `label`, `enabled` |

Słowniki w grupie: `diki_uk`, `diki_us`, `oxford_uk`, `oxford_us`, `cambridge_uk`,
`cambridge_us`, `longman_uk`, `longman_us`. Grupa z UK i US zapisuje dwa nagrania
w jednym polu, a stronę słownika pobiera raz.

```json
{"dictionaries": ["oxford_uk", "oxford_us"], "label": "Oxford", "enabled": true}
```

Oxford, Cambridge i Longman są parsowane z HTML, więc zmiana wyglądu strony
może wymagać poprawki kodu.
