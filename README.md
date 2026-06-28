# Anki Toolkit

Scalona wtyczka łącząca osiem narzędzi do zarządzania kartami Anki.

## Struktura

```
anki-toolkit/
├── __init__.py                      # entry point — rejestruje wszystkie hooki
├── config.json                      # szablon domyślny (nie nadpisywany)
├── config.md                        # dokumentacja konfiguracji
├── manifest.json                    # metadane Anki
│
├── common/                          # współdzielone narzędzia
│   ├── __init__.py
│   ├── consts.py                    # ADDON_NAME (wyliczane z nazwy folderu wtyczki)
│   ├── html.py                      # clean_html(), clean_html_normalized()
│   ├── text.py                      # unique(), safe_str(), unique_filename(), normalize_float(), split_separator_regex(), plural_pl(), apply_word_replacements()
│   ├── http.py                      # fetch_url(), fetch_text(), post_json() (retry dla POST), extract_http_error(), RETRYABLE_STATUS_CODES
│   ├── config.py                    # get_full_config(), save_full_config(), get_module_config(), save_module_config()
│   ├── debug_log.py                 # setup_logging(), konfiguracja logowania wtyczki (plik + konsola)
│   └── ui.py                        # widgety Qt: palette (kolory zależne od motywu), hint_label, _expanding_line_edit, _api_key_widget, _scrollable, get_note_type_names, get_fields_for_note_type, get_sample_notes
│
├── user_files/                      # dane użytkownika (statystyki, historia) — przeżywają aktualizację wtyczki
│
├── settings/                        # Dialog ustawień dla wszystkich modułów
│   ├── __init__.py                  # SettingsDialog, open_settings()
│   ├── status_tab.py                # Zakładka: Start — dashboard pipeline'u workflow
│   ├── modules_tab.py               # Zakładka: Moduły
│   ├── dictionary_tab.py            # Zakładka: Słownik
│   ├── ai_generator_tab.py          # Zakładka: AI Generator
│   ├── workflows_tab.py             # Zakładka: Workflowy — lista nazwanych workflowów + widoczność sekcji PPM
│   ├── prompts_tab.py               # Zakładka: Prompty (edytor + podgląd + kolorowanie składni)
│   ├── prompt_wizard.py             # Dialog „Nowe zadanie AI” (opcjonalny szablon startowy)
│   ├── prompt_templates.py          # Startowe szablony promptów
│   ├── tts_tab.py                   # Zakładka: TTS
│   ├── audio_normalizer_tab.py      # Zakładka: Normalizacja
│   ├── narzedzia_tab.py             # Zakładka: Narzędzia
│   ├── stats_tab.py                 # Zakładka: Statystyki — dashboard użycia AI + koszty
│   └── logs_tab.py                  # Zakładka: Logi — tryb debugowania + podgląd logów
│
├── dictionary/                      # Moduł 1: pobieranie audio + IPA
│   ├── __init__.py                  # re-eksport hooków
│   ├── service.py                   # logika biznesowa (ProcessNoteResult, process_note_group)
│   ├── editor_ui.py                 # przyciski edytora
│   ├── browser_ui.py                # submenu przeglądarki + batch
│   ├── dictionary_service.py        # fetching MP3 z Oxford/Cambridge/Diki/Longman
│   └── ipa_service.py               # fetching IPA z Oxford/Cambridge/Wiktionary
│
├── ai_generator/                    # Moduł 2: generowanie pól przez AI + workflow
│   ├── __init__.py                  # re-eksport hooków
│   ├── _generator.py                # zarządzanie stanem generatora (config-aware cache)
│   ├── editor_ui.py                 # przycisk AI + przyciski workflowów (per editor_button)
│   ├── browser_ui.py                # menu przeglądarki + batch
│   ├── field_generator.py           # logika generowania, niezależna od dostawcy
│   ├── template_engine.py           # silnik szablonów {{pole}} / {% if %}
│   ├── stats.py                     # lokalne statystyki użycia (tokeny, requesty) + dopasowanie cen
│   ├── workflow.py                  # workflowy (lista nazwanych): get_workflows/migrate_workflows/execute_step (AI/Dict/TTS/Rozdziel)
│   └── providers/
│       ├── __init__.py              # rejestr dostawców + fabryka get_provider() + klasy OpenAI-compatible (OpenAI, OpenRouter, CometAPI, Mistral)
│       ├── base.py                  # BaseProvider (ABC) + OpenAICompatProvider + wspólne parsery odpowiedzi
│       ├── openai_compat.py         # helpery OpenAI-compatible
│       ├── anthropic.py             # Anthropic Messages API
│       ├── google.py                # Google Gemini generateContent
│       ├── opencode_go.py           # OpenCode Go (Chat Completions / Anthropic Messages)
│       └── model_discovery.py       # pobieranie listy modeli z API dostawców
│
├── tts/                             # Moduł 3: generowanie audio przez Kokoro TTS lub OpenRouter
│   ├── __init__.py                  # submenu TTS w menu kontekstowym przeglądarki + przycisk edytora
│   ├── config.py                    # _DEFAULTS, get_tts_config(), validate_config(), get_tasks()
│   ├── api.py                       # generate_audio(), _generate_kokoro(), _generate_openrouter(), fetch_openrouter_tts_models()
│   ├── processor.py                 # wspólne build_note_work_items()/generate_for_items()/apply_results_to_note() + batch + process_single_note()
│   └── editor_ui.py                 # przycisk TTS w toolbarze edytora (async, używa wspólnych funkcji procesora)
│
├── filtered_deck/                   # Moduł 4: tworzenie talii filtrowanej
│   └── __init__.py                  # dialog ustawień + tworzenie talii
│
├── audio_normalizer/                # Moduł 5: normalizacja audio przez ffmpeg
│   ├── __init__.py
│   ├── config.py                    # konfiguracja ffmpeg, parametry EBU R128
│   ├── gui.py                       # dialog postępu Qt + wątek roboczy
│   └── logic.py                     # skanowanie plików, historia, przetwarzanie równoległe
│
├── nbsp_remover/                    # Moduł 6: czyszczenie &nbsp; i tagów <div>
│   ├── __init__.py
│   ├── cleaning.py                  # czysta logika czyszczenia pól + liczniki
│   ├── addcards.py                  # hook na dodawanie kart — czyszczenie w locie
│   ├── collection.py                # akcja czyszczenia HTML w całej kolekcji
│   └── utils.py
│
├── field_splitter/                  # Moduł 7: rozdzielanie pola na p1, p2, p3...
│   ├── __init__.py                  # UI (browser context menu + Tools menu) + batch
│   └── splitting.py                 # czysta logika split + parse_target_fields
│
├── sibling_manager/                 # Moduł 8: dynamiczne zawieszanie siblingów
│   ├── __init__.py                  # hook reviewer'a + akcja menu Narzędzia
│   ├── logic.py                     # process_note() — czysta logika suspend/unsuspend
│   ├── README.md
│   └── llm-context.md
│
└── tests/                           # testy czystej logiki bez uruchamiania Anki
```

> Każdy moduł można niezależnie włączyć lub wyłączyć — patrz sekcja **Ustawienia**.

---

## Instalacja

1. Skopiuj folder `anki-toolkit/` do katalogu addons Anki:
   - macOS: `~/Library/Application Support/Anki2/addons21/`
   - Windows: `%APPDATA%\Anki2\addons21\`
2. Uruchom Anki.
3. Otwórz **Narzędzia → Anki Toolkit → Ustawienia...** i uzupełnij klucze API.
4. Upewnij się, że `ffmpeg` jest zainstalowany i dostępny w PATH (wymagane przez `audio_normalizer`).

---

## Ustawienia

Wszystkie moduły można skonfigurować przez jeden centralny dialog:

**Narzędzia → Anki Toolkit → Ustawienia...**

### Zakładki

Nawigacja jest pionowa (pasek po lewej, z ikonami), pogrupowana: **Treść** (AI Generator, Workflowy, TTS, Słownik), **System** (Moduły, Narzędzia, Normalizacja), **Wgląd** (Statystyki, Logi).

| Zakładka | Zawartość |
|---|---|
| **Start** | Dashboard: wiersz „Szybki dostęp" (skróty do najczęstszych zakładek), kafelki kroków reprezentatywnego workflow (✓/⚠/○, zawijane), jeden globalny status (Gotowe / N rzeczy do zrobienia), sekcja „Do zrobienia" z przyciskami Napraw, wiersz pozostałych modułów. Odświeża się przy każdym wejściu na zakładkę i uwzględnia niezapisane zmiany z innych zakładek |
| **Moduły** | Włącz/wyłącz każdy moduł (zmiana wymaga restartu Anki) |
| **Słownik** | Pola źródłowe/docelowe, format IPA, przyciski słowników, limity sieci |
| **AI Generator** | Prompty oraz dostawcy AI w osobnych podzakładkach; każdy prompt wybiera dostawcę i model (lista modeli filtruje po fragmencie nazwy); dostawcy jako lista z detalem (✓ = klucz API ustawiony); prompty z dialogiem nowego zadania, podglądem na przykładowej notatce i kolorowaniem składni; w Zaawansowanych m.in. liczba równoległych żądań batcha |
| **Workflowy** | Lista nazwanych workflowów (Dodaj/Edytuj/Usuń, kolejność ▲▼ = kolejność w menu PPM); edytor kroków (AI/Słownik/TTS/Rozdziel) z parametrami; checkbox „Pokaż jako przycisk w edytorze" per workflow; checkboxy widoczności wbudowanych sekcji PPM (Pobierz wymowę / TTS / Generuj pola / Generuj zablokowane / Rozdziel pole) |
| **TTS** | Dostawca (Kokoro/OpenRouter), klucz API, model, wybór głosów z przyciskami **▶** (podgląd każdego głosu bez zaznaczania), zadania TTS, szybkość, liczba wątków |
| **Normalizacja** | Ścieżka ffmpeg (z przyciskiem "Sprawdź"), opcje loudnorm, liczba wątków |
| **Narzędzia** | Talia filtrowana · czyszczenie HTML (`&nbsp;`, `<div>`) · rozdzielanie pól · Sibling Manager (dynamiczne zawieszanie siblingów) |
| **Statystyki** | Dashboard użycia AI: requesty, błędy, tokeny wej./wyj., wygenerowane pola i szacowany koszt per model (przycisk **Pobierz ceny (OpenRouter)** dopasowuje cennik do Twoich modeli); osobna tabela **TTS** — requesty, błędy, znaki i pliki audio per model (Kokoro i OpenRouter; koszt OpenRouter liczony per znak); wybór zakresu (dziś / 7 / 30 / 365 dni / wszystko / własny zakres dat od–do) i przycisk resetu |
| **Logi** | Tryb debugowania + podgląd bufora logów wtyczki (auto-odświeżanie, Kopiuj/Wyczyść) |

> **Gdzie są przechowywane ustawienia?** `config.json` w folderze wtyczki to szablon domyślny — nie jest nadpisywany. Twoje zmiany są zapisywane przez Anki w katalogu profilu (`addons21/.../meta.json`). Po ponownym otwarciu dialogu zobaczysz zapisane wartości.

---

## Włączanie i wyłączanie modułów

Przez dialog **Ustawienia → zakładka Moduły**, lub ręcznie w `config.json`:

```json
"modules": {
    "dictionary":        true,
    "ai_generator":      true,
    "tts":               false,
    "filtered_deck":     true,
    "audio_normalizer":  true,
    "nbsp_remover":      true,
    "field_splitter":    true,
    "sibling_manager":   true
}
```

Zmiana wymaga restartu Anki. Brakujący klucz jest traktowany jako `true`.

---

## Opis modułów

### Słownik (`dictionary`)

Przyciski pojawiają się w toolbarze edytora kart — kliknięcie najpierw zapisuje bieżące pola, a pobieranie działa w tle (Anki nie zamarza). W przeglądarce dostępne jest też submenu **Pobierz wymowę** pod prawym przyciskiem myszy w sekcji **Anki Toolkit**, które pozwala uruchomić batch dla wszystkich włączonych słowników albo tylko dla wybranego, np. Diki lub Oxford. Moduł pobiera audio i IPA z wybranych słowników. Batch działa w tle — Anki nie zamraża się, widoczny pasek postępu z przyciskiem Anuluj.

**PPM na polu źródłowym w edytorze** (np. `ang`) — gdy pole ma treść, pojawiają się pozycje „Pobierz wymowę: Diki", „Pobierz wymowę: Oxford" itd. (tylko włączone słowniki). Działa też w oknie dodawania nowej karty.

Konfiguracja w **Ustawienia → Słownik**:

| Pole | Opis |
|---|---|
| `source_field` | Pole z angielskim słowem (np. `"ang"`) |
| `target_field` | Pole docelowe dla audio (np. `"audio"`) |
| `ipa_field` | Pole docelowe dla IPA (puste = wyłączone) |
| `ipa_format` | `"compact"` / `"both"` / `"uk_only"` / `"us_only"` |
| `wiktionary_ipa_fallback` | `true` — gdy Oxford/Cambridge nie znajdzie IPA, odpyta Wiktionary API (domyślnie `true`) |
| `diki_ipa_fallback` | `true` — gdy fetchujesz z Diki (brak natywnego IPA), pobierz IPA z osobnego źródła (domyślnie `false`) |
| `diki_ipa_fallback_source` | Źródło IPA dla Diki: `"wiktionary"` / `"oxford"` / `"cambridge"` (domyślnie `"wiktionary"`) |
| `max_retries` | Liczba prób przy błędach sieci (domyślnie 3) |
| `page_timeout` | Timeout pobierania strony słownika w sekundach (domyślnie 10) |
| `mp3_timeout` | Timeout pobierania pliku MP3 w sekundach (domyślnie 10) |
| Przyciski | Zaznacz które słowniki mają być widoczne w edytorze |

Dostępne słowniki: `oxford_uk`, `oxford_us`, `cambridge_uk`, `cambridge_us`, `diki_uk`, `diki_us`, `longman_uk`, `longman_us`.

Wpisy `buttons` sterują jednocześnie:
- przyciskami w edytorze
- pozycjami w submenu batchowym w przeglądarce

---

### Workflowy (własne, nazwane)

Workflow to nazwany łańcuch kroków (AI / Słownik / TTS / Rozdziel pole) uruchamiany jednym kliknięciem. **Tworzysz i nazywasz własne workflowy z poziomu interfejsu**: **Ustawienia → Workflowy**.

- **Dodaj / Edytuj / Usuń** workflow; kolejność na liście = kolejność w menu PPM (▲▼)
- W edytorze workflow: nazwa, checkbox „Pokaż jako przycisk w edytorze" oraz kroki
- Dodawaj kroki przyciskami **+ AI**, **+ Słownik**, **+ TTS**, **+ Rozdziel**; kolejność ▲▼
- Krok **AI** ma parametr „które pola": wszystkie puste / zablokowane (`manual_only`) / konkretne pola (dwuklik edytuje); krok **Słownik** pozwala wybrać słowniki
- Każdy workflow z zaznaczonym „Pokaż jako przycisk" dostaje własny przycisk w toolbarze edytora

Domyślne workflowy (po migracji ze starej konfiguracji): „Generuj fiszkę" (AI → Oxford → TTS), „Generuj wszystko: puste → TTS → rozdziel → zablokowane" oraz „Rozdziel + generuj naukę (p1–p3)".

**Co jest widoczne w PPM:** w **Ustawienia → Workflowy** decydujesz też o widoczności wbudowanych (auto-generowanych) sekcji menu — checkboxy „Pobierz wymowę", „TTS", „Generuj pola", „Generuj zablokowane", „Rozdziel pole". Workflowy są zawsze na górze menu.

**Batch w przeglądarce:** prawy klik → **Anki Toolkit → [nazwa workflow]** uruchamia łańcuch dla wszystkich zaznaczonych notatek — z paskiem postępu, przyciskiem Anuluj i zapisem jako **jedna operacja z undo** (Ctrl+Z cofa cały batch).

---

### Generator AI (`ai_generator`)

Pomocniczy przycisk **AI** w toolbarze edytora generuje wszystkie skonfigurowane puste pola AI dla pojedynczej karty. Dodatkowo dostępne są dwie ścieżki per-pole:

- **PPM na polu w edytorze** → „Wygeneruj `pole` przez AI" (pole puste) lub „Regeneruj `pole` przez AI" (pole pełne — nadpisuje). Opcja pojawia się tylko na polach które mają skonfigurowany prompt dla bieżącego typu notatki.
- **Przeglądarka** → **prawy klik → Anki Toolkit → Generuj pola ▸** — submenu: „Wszystkie puste" (obecne zachowanie) oraz osobne pozycje per pole docelowe (np. „AI: def", „AI: cz_mowy"). Pozycje per pole pomijają wypełnione — bezpieczne na wielu notatkach różnych typów (każdy typ dostaje swój prompt).
- **Przeglądarka** → **prawy klik → Anki Toolkit → Generuj zablokowane ▸** — submenu pojawia się tylko gdy istnieją pola oflagowane „Tylko na żądanie" w ustawieniach promptów. Zawiera „Wszystkie zablokowane" (generuje wszystkie pola zablokowane dla zaznaczonych notatek) oraz osobne pozycje per pole.
- **Przeglądarka** → **prawy klik → Anki Toolkit → [workflowy]** — domyślne workflowy „Rozdziel + generuj naukę (p1–p3)" (rozdziela `przyklad` na `p1`/`p2`/`p3` i generuje `p1-nauka`/`p2-nauka`/`p3-nauka`) oraz „Generuj wszystko: puste → TTS → rozdziel → zablokowane" (4 kroki: puste pola AI → wszystkie zadania TTS → rozdziel `przyklad` → pola `manual_only`) są teraz **edytowalnymi workflowami** (Ustawienia → Workflowy). Każdy krok startuje po zapisaniu poprzedniego do kolekcji, więc czyta świeże pola; kroki bez konfiguracji są pomijane, a łańcuch leci dalej.

- **Edytor**: działa asynchronicznie — Anki nie zamarza podczas oczekiwania na API. Możesz swobodnie edytować inne pola w tym czasie. Pola docelowe AI są zawsze nadpisywane wynikiem; pola których AI nie dotyka są chronione przez `saveNow` przed skasowaniem Twoich edycji. Jeśli w trakcie generowania przełączysz się na inną kartę, wynik trafia do właściwej notatki (zapis do kolekcji), nie do aktualnie wyświetlanej.
- **Batch**: działa w tle z paskiem postępu i przyciskiem Anuluj; notatki są przetwarzane **równolegle** (liczba wątków: `parallel_requests`, domyślnie 3) w paczkach po `batch_limit` z przerwą `batch_sleep`. Zmiany zapisywane są jedną operacją z undo. Po zakończeniu jeden tooltip z podsumowaniem.
- Główny przycisk **AI** i batch „Wszystkie puste" pomijają pola z treścią — generator uzupełnia tylko puste pola. PPM w edytorze może nadpisać pojedyncze pole („Regeneruj"). Pola oflagowane „Tylko na żądanie" są pomijane w batchu, workflow i głównym przycisku AI — dostępne tylko przez jawne wskazanie (PPM, submenu „Generuj zablokowane").
- Zmiana kluczy API i promptów **nie wymaga restartu Anki**.
- **Statystyki użycia** (requesty, tokeny, pola per model, szacowany koszt) są zliczane lokalnie (`user_files/usage_stats.json`) i widoczne w **Ustawienia → Statystyki**.
- Żądania do OpenRouter wysyłają atrybucję aplikacji (`HTTP-Referer`/`X-Title`), więc w statystykach OpenRouter pojawiają się jako „Anki Toolkit" (automatyczne, bez konfiguracji).

Konfiguracja w **Ustawienia → AI Generator**:

| Pole | Opis |
|---|---|
| `button_label` | Etykieta przycisku w edytorze |
| `skip_tags` | Lista tagów wykluczających — notatki z dowolnym z tych tagów są pomijane w całości (brak wywołań API, brak aktualizacji) |
| `batch_limit` | Liczba kart w jednej paczce — po paczce następuje przerwa `batch_sleep` |
| `batch_sleep` | Pauza (sekundy) między paczkami kart — zapobiega limitom API |
| `parallel_requests` | Liczba notatek przetwarzanych równolegle w batchu (domyślnie 3) |
| `max_retries` | Liczba prób przy błędach API 429/5xx (domyślnie 3) |
| `request_timeout` | Timeout żądania do API w sekundach (domyślnie 30) |
| `free_model_rate_limit` | Limit RPM dla modeli `:free` OpenRouter (domyślnie 15; max 20 wg OpenRouter) |
| Dostawcy | Klucz API, model domyślny (przycisk **Pobierz** pobiera listę dostępnych modeli z API), model zapasowy (fallback), temperatura osobno dla każdego dostawcy; dla OpenAI, CometAPI i OpenRouter także poziom reasoning |
| Prompty | Dostawca, model, model zapasowy (fallback), dostawca zapasowy (fallback) — per prompt; nadpisuje fallback z poziomu dostawcy |

`reasoning_effort` jest konfigurowalne dla `openai`, `cometapi` i `openrouter` i wysyłane tylko dla modeli obsługujących reasoning. Jeśli model zwróci błąd HTTP 400 z powodu nieobsługiwanego `reasoning_effort`, żądanie jest automatycznie ponawiane bez tego parametru. Modele OpenAI reasoning nie dostają `temperature`. `max_tokens` jest konfigurowalne dla Anthropic (wymagany przez ich API, domyślnie `2048`). Pola notatki zawierające HTML są automatycznie oczyszczane przed wstawieniem do promptu.

#### Dostępni dostawcy

| Dostawca | Endpoint |
|---|---|
| `openai` | `https://api.openai.com/v1/chat/completions` |
| `cometapi` | `https://api.cometapi.com/v1/chat/completions` |
| `openrouter` | `https://openrouter.ai/api/v1/chat/completions` |
| `anthropic` | `https://api.anthropic.com/v1/messages` |
| `google` | `https://generativelanguage.googleapis.com/v1beta/models` |
| `mistral` | `https://api.mistral.ai/v1/chat/completions` |
| `opencode_go` | `https://opencode.ai/zen/go/v1/chat/completions` (większość modeli) / `.../messages` (MiniMax, Qwen3.x) |

#### Szablony promptów

- `{{nazwa_pola}}` — wstawia wartość pola karty (oczyszczoną z HTML)
- `{% if pole %} ... {% else %} ... {% endif %}` — warunek

Edytor promptów (zakładka **Prompty**):

- **Dialog nowego zadania** — przycisk **+ Dodaj…** otwiera kompaktowy dialog: typ notatki, pole docelowe, dostawca, model, opcjonalny szablon startowy (domyślnie pusty prompt; do wyboru definicja, przykładowe zdania, część mowy, IPA) oraz checkbox „Tylko na żądanie" (pomija pole w batchu/workflow, dostępne tylko przez jawne wskazanie). Po wybraniu szablonu pojawiają się comboboxy mapujące pola szablonu na pola notatki; szablon „Przykładowe zdania" ma opcjonalny warunek „użyj definicji, jeśli pole jest wypełnione" — blok `{% if %}…{% else %}…{% endif %}` generuje się automatycznie.
- **Model per prompt** — edytowalna lista z przyciskiem **Pobierz**; wpisanie np. `5.5` pokazuje tylko modele zawierające `5.5`. Starsze prompty bez pola `model` używają modelu domyślnego dostawcy.
- **Podgląd na przykładowej notatce** — przycisk **Podgląd…** otwiera okno, które renderuje finalny prompt na wybranej notatce z kolekcji (pola podstawione, HTML oczyszczony) i pokazuje, która gałąź każdego `{% if %}` zostanie użyta.
- **Kolorowanie składni** — `{{pola}}` i bloki `{% if %}` są wyróżnione kolorem; pola nieistniejące w typie notatki dostają czerwone faliste podkreślenie.
- Przyciski **Wstaw pole ▾** (wstawia `{{pole}}` w pozycji kursora) i **Wstaw warunek ▾** (wstawia szkielet warunku; zaznaczony tekst trafia do gałęzi „if").
- Walidacja na żywo: nieznane pola, błędy struktury bloków `{% if %}` (niedomknięty, osierocony `{% else %}`/`{% endif %}`, zagnieżdżony) oraz użycie pola generowanego przez późniejsze zadanie.
- **Kolejność zadań** — lista po lewej odpowiada kolejności generowania; przyciski **▲▼** zmieniają kolejność, a wpisy używające wyników innych zadań mają dopisek „zależy od: …".

Każde pole notatki może używać innego dostawcy i modelu. Pola generowane są w kolejności kluczy w `note_types` — wynik wcześniejszego pola można użyć w prompcie następnego.

#### Dodanie nowego dostawcy AI

1. Jeśli API jest zgodne z OpenAI Chat Completions — dodaj cienką klasę dziedziczącą po `OpenAICompatProvider` w `ai_generator/providers/__init__.py` (wystarczy `API_URL` i `LABEL`). W przeciwnym razie utwórz `ai_generator/providers/moj_provider.py` dziedzicząc po `BaseProvider` i zaimplementuj `call_api(self, prompt) -> Optional[str]` (możesz użyć gotowych `_parse_chat_completion()` / `_parse_messages()` z bazy)
2. Zarejestruj klasę w `ai_generator/providers/__init__.py` w słownikach `PROVIDERS` i `PROVIDER_LABELS` (UI ustawień buduje listy dostawców z tego rejestru)
3. Dodaj sekcję `providers.moj_provider` w `config.json`

#### OpenCode Go — szczegóły

Dostawca `opencode_go` obsługuje niskokosztową subskrypcję [OpenCode Go](https://opencode.ai/zen). Automatycznie wybiera format API na podstawie nazwy modelu:
- **Chat Completions** — GLM-5/5.1, Kimi K2.5/K2.6, DeepSeek V4 Pro/Flash, MiMo-V2.5/V2.5-Pro
- **Anthropic Messages** — MiniMax M2.5/M2.7, Qwen3.5/3.6 Plus

Pole `reasoning_effort` to wolny tekst (nie dropdown jak przy OpenAI) — wartości różnią się per model, np. `max` dla DeepSeek V4 Pro. Puste = nie wysyłane. Klucz API uzyskasz na [opencode.ai/auth](https://opencode.ai/auth).

#### Fallback modeli

Gdy główny model zawiedzie (błąd API, rate limit, brak środków na koncie, brak treści w odpowiedzi), wtyczka automatycznie uruchamia model zapasowy z tym samym promptem. Fallback jest konfigurowalny na dwóch poziomach:

| Poziom | Pole | Priorytet |
|---|---|---|
| **Per prompt** | `fallback_provider` + `fallback_model` | Wyższy — jeśli ustawiony, nadpisuje fallback dostawcy |
| **Per dostawca** | `fallback_model` w sekcji providera | Niższy — używany gdy prompt nie ma własnego fallbacku |

- Per-prompt `fallback_provider` pusty = użyj tego samego dostawcy co główny model
- Per-prompt `fallback_model` pusty = brak fallbacku per-prompt → sprawdź `fallback_model` dostawcy
- Obie puste = brak fallbacku (zachowanie jak wcześniej — błąd jest logowany)
- Fallback używa tego samego promptu, temperature, reasoning_effort i klucza API co model główny (jeśli ten sam dostawca) lub klucza API dostawcy zapasowego (jeśli inny dostawca)
- Statystyki użycia zliczają fallback osobno (per `provider/model`)
- Log zawiera ostrzeżenie z info który model → który fallback został użyty

Konfiguracja w **Ustawienia → AI Generator**:
- **Dostawcy** — pole „Model zapasowy" przy każdym dostawcy
- **Prompty** — pola „Dostawca zapasowy" i „Model zapasowy" przy każdym prompcie

#### Modele `:free` (OpenRouter) — rate limiter

OpenRouter oferuje darmowe warianty modeli z sufiksem `:free` (np. `meta-llama/llama-3.2-3b:free`). Mają one limit **20 żądań na minutę** (RPM) narzucony przez OpenRouter.

Wtyczka automatycznie ogranicza żądania do modeli `:free` do **15 RPM** (konfigurowalne w Ustawienia → AI Generator → Zaawansowane → „Limit RPM dla :free"). Gdy limit jest osiągnięty, wtyczka czeka do zwolnienia miejsca w oknie 60-sekundowym — nie odrzuca żądań, tylko pauzuje. Dotyczy to zarówno modelu głównego jak i fallbackowego, jeśli oba są `:free`.

Płatne modele (bez `:free` w nazwie) nie są ograniczane przez tę wartość.

---

### TTS

Dostępny przez **prawy klik → Anki Toolkit → TTS** w przeglądarce (batch z QProgressDialog i Anuluj) oraz **przycisk TTS w edytorze** (pojedyncza karta, wszystkie zadania). Przycisk edytora najpierw zapisuje bieżące pola, więc synteza używa aktualnego tekstu. Obsługuje dwa źródła:

**PPM na polu docelowym w edytorze** (np. `audio`, `przyklad`) — gdy pole jest `target_field` jakiegoś zadania TTS, pojawia się „Generuj TTS: [label]" (pole puste) lub „Regeneruj TTS: [label]" (pole pełne — strip `[sound:...]` i generuj nowe). Działa też w oknie dodawania nowej karty.
- **Kokoro** — lokalny serwer TTS przez Dockera (darmowy, bez limitu)
- **OpenRouter** — API TTS przez chmurę (płatne per znak, nie wymaga lokalnego serwera)

Konfiguracja w **Ustawienia → TTS**:

| Pole | Opis |
|---|---|
| `tts_provider` | Dostawca: `kokoro` (lokalny) lub `openrouter` (API) |
| `button_label` | Etykieta przycisku w edytorze (domyślnie `"TTS"`) |
| `api_url` | Adres serwera Kokoro (tylko dla Kokoro) |
| `model` | Nazwa modelu Kokoro (tylko dla Kokoro) |
| `openrouter_api_key` | Klucz API OpenRouter (lub zaznacz "Użyj klucza z AI Generatora") |
| `use_ai_openrouter_key` | `false` — użyj klucza OpenRouter z AI Generatora zamiast wpisywać osobno |
| `openrouter_model` | Model TTS OpenRouter — kliknij **Pobierz** aby zobaczyć dostępne modele z cenami |
| `voices` | Lista głosów do losowania. Dla OpenRouter: po wybraniu modelu pojawia się lista z checkboxami |
| `tasks` | Lista zadań TTS (konfigurowalna przez UI: Dodaj/Edytuj/Usuń) |
| `speed` | Tempo mowy (0.1–3.0, domyślnie 0.9) |
| `max_workers` | Liczba równoległych wątków generowania audio (domyślnie 12) |
| `max_retries` | Liczba prób przy błędach API 429/5xx (domyślnie 3) |
| `timeout` | Timeout żądania TTS w sekundach (domyślnie 60) |

Dla OpenRouter: po kliknięciu **Pobierz** wtyczka pobiera listę dostępnych modeli TTS z OpenRouter (wraz z cenami w `$/1k zn`). Po wybraniu modelu pojawia się lista głosów z checkboxami — zaznacz które chcesz używać.

**Zadania TTS**: zamiast sztywnych pól `ang`/`przyklad`, moduł używa konfigurowalnej listy zadań. Każde zadanie definiuje etykietę menu, pola źródłowe/docelowe oraz tryb (`single` — jedno audio, `split` — dzielone separatorem). Menu TTS jest budowane dynamicznie. Opcja **Uruchom wszystkie** wykonuje zadania jako jedną operację z jednym paskiem postępu i jednym podsumowaniem. Backward compat: stare pola `ang_source_field`/`przyklad_target_field` są czytane z zapisanego configu tylko gdy klucz `tasks` w ogóle nie istnieje — wystarczy raz zapisać ustawienia, by `tasks` stało się jedynym źródłem.

Batch zapisuje zmiany jako **jedną operację z undo**. Przycisk **Anuluj** faktycznie przerywa kolejkę — żądania, które jeszcze nie wystartowały, są odwoływane (już wygenerowane audio zostaje zapisane).

Każde wygenerowane audio (Kokoro i OpenRouter) jest zliczane w **Ustawienia → Statystyki**: requesty, błędy, liczba znaków i plików per model; dla OpenRouter dostępny jest szacowany koszt (cennik per znak).

---

### Talia filtrowana (`filtered_deck`)

Dostępny przez **Narzędzia → Anki Toolkit → Utwórz talię filtrowaną: ...** — nazwa talii w menu odpowiada skonfigurowanej nazwie wyszukiwanej talii.

Konfiguracja w **Ustawienia → Narzędzia** (sekcja Talia filtrowana):

| Pole | Opis |
|---|---|
| `deck_name` | Nazwa tworzonej talii filtrowanej (domyślnie `"Angielski - Powtórka z wyprzedzeniem"`) |
| `search_deck` | Nazwa talii do wyszukiwania w `deck:` (domyślnie `"angielski"`) |

Jeśli talia filtrowana o tej nazwie już istnieje, jest **aktualizowana i przebudowywana** zamiast tworzenia kolejnych kopii z sufiksem `(1)`, `(2)`…

Dialog przy każdym użyciu pozwala wybrać dodatkowe opcje:

| Opcja | Opis |
|---|---|
| Dni do przodu | Zakres `prop:due<=X` (domyślnie 9999 = wszystkie) |
| Limit kart | Maksymalna liczba kart w talii (domyślnie 99999) |
| Kolejność | Losowo, wg interwału, wg terminu itp. |

---

### Normalizacja audio (`audio_normalizer`)

Dostępny przez **Narzędzia → Anki Toolkit → Normalizuj Audio (ffmpeg)**.

Normalizuje wszystkie pliki audio w katalogu media Anki do głośności EBU R128 (`I=-14 LUFS, TP=-1.5, LRA=8`).
Przetworzone pliki są zapamiętywane w `user_files/audio_normalizer_history.json` (katalog `user_files/` przeżywa aktualizacje wtyczki) — ponowne uruchomienie pomija już znormalizowane pliki.
Błędy są logowane przez standardowy logger Pythona i są widoczne w konsoli/debug logach Anki.

**Synchronizacja z Anki Media DB:** Po normalizacji wtyczka automatycznie re-readuje zmodyfikowane pliki przez `mw.col.media.write_data()`, co aktualizuje hashe w bazie mediów Anki.

**Auto-normalizacja:** Włącz **Auto-normalizuj nowe pliki audio** w ustawieniach, aby watcher obserwował katalog mediów i automatycznie normalizował nowe pliki ~3s po dodaniu (debounce zbiera serie zapisów). Obejmuje wszystkie źródła: TTS, słownik, AI workflow, ręczne dodanie, AnkiWeb sync. Po normalizacji pojawia się krótki tooltip w prawym dolnym rogu. Wymaga restartu Anki po zmianie ustawienia.

Konfiguracja w **Ustawienia → Normalizacja**:

| Pole | Opis |
|---|---|
| `ffmpeg_path` | Ścieżka do ffmpeg — puste = wykryj automatycznie; przycisk **Sprawdź** testuje ścieżkę i pokazuje wersję |
| `loudnorm_opts` | Parametry filtra loudnorm (standard EBU R128) |
| `max_workers` | Liczba równoległych wątków ffmpeg (domyślnie 4) |
| `auto_normalize` | Włącz auto-normalizację nowych plików (watcher na katalogu mediów; domyślnie `false`; wymaga restartu) |

---

### Czyszczenie HTML (`nbsp_remover`)

Działa automatycznie przy dodawaniu kart. Ręczne czyszczenie całej kolekcji przez **Narzędzia → Anki Toolkit → Wyczyść HTML w kolekcji...**

| Akcja | Opis |
|---|---|
| Dodawanie karty | Usuwa `&nbsp;` i czyści `<div>` z każdego pola w locie |
| Wyczyść HTML w kolekcji | Jednorazowe czyszczenie całej kolekcji — działa w tle, z możliwością cofnięcia (jeden krok undo) |

Zagnieżdżone `<div>` są rozwijane od środka (bez pozostawiania niesparowanych tagów). Opcja „Czyść przy starcie" uruchamia się po załadowaniu profilu (hook `profile_did_open`).

Dla pola konfigurowalnego (domyślnie `ang`): tagi `<div>` są usuwane całkowicie.
Dla pozostałych pól: `<div>tekst</div>` zastępowane przez `tekst<br>`.

Konfiguracja w **Ustawienia → Narzędzia** (sekcja Czyszczenie HTML):

| Opcja | Domyślnie | Opis |
|---|---|---|
| Pokazuj tooltip | `true` | Wyświetlaj powiadomienie po wyczyszczeniu |
| Czyść przy starcie | `false` | Automatycznie uruchamiaj czyszczenie kolekcji przy starcie Anki |
| Pole pomijane | `"ang"` | Pole z którego tagi `<div>` są usuwane całkowicie (zamiast zamiany na `<br>`) |

---

### Rozdzielanie pól (`field_splitter`)

Rozdziela zawartość pola źródłowego (np. `przyklad`) po separatorze i **kopiuje** części do kolejnych pól docelowych (`p1`, `p2`, `p3`…). Pole źródłowe nie jest modyfikowane.

Dostępne przez:
- **PPM w przeglądarce → Anki Toolkit → Rozdziel pole przyklad → p1, p2, p3...** — batch na zaznaczonych notatkach
- **Narzędzia → Anki Toolkit → Rozdziel pola w kolekcji...** — wszystkie notatki (z potwierdzeniem)

Konfiguracja w **Ustawienia → Narzędzia** (sekcja Rozdzielanie pól):

| Pole | Opis |
|---|---|
| `source_field` | Pole źródłowe z danymi do rozdzielenia (domyślnie `"przyklad"`) |
| `separator` | Separator części (domyślnie `"<br><br>"`; whitespace-tolerant) |
| `target_fields` | Pola docelowe oddzielone przecinkami (domyślnie `"p1, p2, p3, p4, p5"`) |
| `overwrite` | `true` (domyślnie) = nadpisuj zawsze; `false` = wypełniaj tylko puste pola docelowe |

Zasady:
- Pierwsza część → `p1`, druga → `p2`, trzecia → `p3` itd.
- Więcej części niż pól docelowych: nadmiarowe części są pomijane
- Mniej części niż pól docelowych: pozostałe pola nietknięte
- Pole źródłowe zawsze zachowane (kopia, nie przeniesienie)
- Batch zapisywany jako **jedna operacja z undo** (Ctrl+Z cofa cały batch)
- Tylko notatki posiadające pole źródłowe są przetwarzane; pola docelowe nieistniejące w typie notatki są pomijane
- `overwrite: false` jest bezpieczny gdy chcesz uzupełnić brakujące pola bez ryzyka nadpisania ręcznych poprawek

---

### Sibling Manager (`sibling_manager`)

Dynamiczne zawieszanie kart-siblingów. Po odpowiedzi na kartę, moduł zawiesza pozostałe NEW siblingi dopóki aktywna karta nie dojrzeje. Gdy dojrzeje — uwalnia wszystkie zawieszone na raz, a Anki pokazuje następną (losowo).

W przeciwieństwie do [SibPush](https://github.com/DerDemystifier/SibPush_Delay-New-Sibs), który pre-suspenduje z góry wg kolejności szablonów, ten moduł jest **reaktywny** — działa dopiero po odpowiedzi na kartę. Większa losowość: to Anki decyduje którą kartę pokazać, a nie z góry ustalona kolejność.

**Zasada działania:**
1. Anki pokazuje kartę → odpowiadasz → hook `reviewer_did_answer_card`
2. Interval < próg (30 dni) → **zawiesza wszystkie inne NEW siblingi**
3. Interval ≥ próg → **uwolnić wszystkie zawieszone siblingi** na raz
4. Anki pokazuje kolejną → cykl się powtarza

**Zapomnienie karty:** Jeśli dojrzała karta zostanie zapomniana (interval spadnie poniżej progu), przy kolejnej odpowiedzi hook znów zawiesi NEW siblingi. Karty w nauce/review (nie `CARD_TYPE_NEW`) nie są dotykane.

**Uczenie na telefonie + synchronizacja:** Hook reviewer'a odpala się tylko na desktopie. Po synchronizacji z AnkiMobile/AnkiWeb automatycznie uruchamia się batch scan (hook `sync_did_finish`) — przetwarza wszystkie notatki z NEW siblingami w tle (CollectionOp, jeden krok undo). Ręczny catch-up: **Narzędzia → Anki Toolkit → Sibling Manager: przeskanuj całą kolekcję (zawieś/uwolnij siblingi)...**.

**Reset:** **Narzędzia → Anki Toolkit → Uwolnij karty zawieszone przez Sibling Manager...** — uwalnia wszystkie zawieszone karty i usuwa tagi (jeden krok undo).

**Powiadomienia i logi:** Po każdej odpowiedzi log z licznikami ("zawieszono 2, odwieszono 0") trafia do bufora logów (**Ustawienia → Logi**). Po sync catch-up dodatkowo tooltip "Sibling Manager: zawieszono X, odwieszono Y" (gdy coś zrobiono, można wyłączyć). Brak tooltipa po pojedynczej odpowiedzi — nie spamuje przy setkach kart. Bufor logów: 2000 linii w pamięci, znika po restarcie.

Konfiguracja w **Ustawienia → Narzędzia** (sekcja Sibling Manager):

| Pole | Default | Opis |
|---|---|---|
| `interval` | `30` | Po ilu dniach interval karta uznana za dojrzałą → uwolnienie siblingów |
| `tag` | `tk-sib-suspended` | Tag dodawany do notatki gdy ma zawieszone siblingi |
| `ignore_tag` | `tk-sib-ignored` | Notatki z tym tagiem są pomijane przez moduł |
| `show_tooltip` | `true` | Tooltip po sync catch-up ("zawieszono X, odwieszono Y") |

**Współistnienie z SibPush:** Jeśli używałeś wcześniej SibPush, **wyłącz go** przed włączeniem tego modułu — oba zarządzają zawieszaniem i mogłyby konfliktować.

---

## Bezpieczeństwo

Klucze API są przechowywane w profilu Anki w czystym tekście. Nie udostępniaj katalogu profilu publicznie.
