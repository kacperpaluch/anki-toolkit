# LLM Context — dictionary

## Co robi

Pobiera audio MP3 i transkrypcję IPA dla angielskich słów z czterech słowników online. Działa w edytorze kart (przyciski w toolbarze) i przeglądarce przez menu kontekstowe **Anki Toolkit → Pobierz wymowę** dla zaznaczonych notatek.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Re-eksport hooków — importuje z `editor_ui` i `browser_ui` |
| `service.py` | Logika biznesowa — `ProcessNoteResult`, `process_note_group()` (bez Qt); reużywa istniejące pliki media (`os.path.exists(dict_{source}_{safe_word}.mp3)`) i fetchuje tylko brakujące źródła; używa `clean_html_normalized()` z `common` |
| `editor_ui.py` | Hooki edytora — przyciski w toolbarze, odtwarzanie audio; `saveNow(start)` przed fetchowaniem + `run_in_background` (UI nie zamarza) + guard `_FETCHING`; rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na `source_field` lub `target_field` (np. `ang`/`audio`): „Pobierz wymowę: [słownik]" per włączony przycisk (wymaga treści w `source_field`); używa `ADDON_NAME` z `common` |
| `browser_ui.py` | Hooki przeglądarki — submenu batch; natywny pasek `mw.progress` przez `common.progress` (`start_progress`/`update_progress`/`finish_progress`); używa `ADDON_NAME` z `common` |
| `dictionary_service.py` | HTTP + HTML scraping dla Oxford, Cambridge, Diki.pl, Longman; używa `fetch_text()` i `fetch_url()` z `common.http` |
| `ipa_service.py` | HTTP + HTML scraping IPA dla Oxford, Cambridge + Wiktionary REST API; używa `fetch_text()` z `common.http` |

## Przepływ danych

```
Kliknięcie przycisku/menu
  → editor_ui / browser_ui wywołuje service.process_note_group()
      → process_note_group(note, config, dictionaries)
          → max_retries = config.get("max_retries", 3)
          → page_timeout = config.get("page_timeout", 10)
          → mp3_timeout = config.get("mp3_timeout", 10)
      → CACHE (media folder = cache): dla każdego źródła sprawdź os.path.exists(media_dir / dict_{source}_{safe_word}.mp3)
          # trafienie → reuse istniejącego pliku, bez sieci; tylko missing_sources idą do fetch_audio_group
          # deterministyczna nazwa + dedup Anki = persistencja cross-run (kolejne karty tego samego słowa nie pobierają ponownie)
      → dictionary_service.fetch_audio_group(word, missing_sources, max_retries, page_timeout, mp3_timeout, batch_cache)
          # batch_cache: dict wspólny dla całego batcha — pomija re-fetch tego samego słowa (komplementarny do cache media)
          # pobiera stronę raz na słownik, uruchamia parsery UK i US na tym samym HTML
          → fetch_text(url, max_retries, timeout=page_timeout)  # 1× GET na słownik (Oxford/Cambridge/Longman)
          → _get_{oxford,cambridge,longman}_audio_url()   # parser UK na tym HTML
          → _get_{oxford,cambridge,longman}_audio_url()   # parser US na tym samym HTML
          → fetch_url(audio_url, max_retries, timeout=mp3_timeout)  # GET bajty UK
          → fetch_url(audio_url, max_retries, timeout=mp3_timeout)  # GET bajty US
          # zwraca też page_cache: {"oxford": html, ...}
      → mw.col.media.write_data(filename, bytes)          # zapisuje TYLKO świeżo pobrane; nazwa deterministyczna dict_{source}_{safe_word}.mp3
      → tagi w kolejności `dictionaries` (reused + fetched razem); result.saved_filenames = wszystkie użyte pliki (więc note_modified działa też przy samym reuse)
      → note[target_field] = "[sound:uk.mp3] [sound:us.mp3]"
      → ipa_service.fetch_ipa(word, source, html=page_cache.get(source), max_retries, timeout)
          # html przekazany z cache → brak dodatkowego HTTP GET dla Oxford/Cambridge
          # jeśli primary source zwraca None → fallback na Wiktionary
          → note[ipa_field] = "/θɔːt/"
  → jeśli pole audio już miało treść:
      → tooltip("Pole audio już zawiera treść.")
  → jeśli audio było potrzebne, ale nie znaleziono żadnego pliku:
      → tooltip("Brak audio do pobrania dla tego hasła.")
```

W przeglądarce submenu `Pobierz wymowę` jest dostępne w menu kontekstowym `Anki Toolkit`:
- `Wszystkie włączone słowniki` — batch po wszystkich aktywnych pozycjach z `buttons`
- `Pobierz z {label}` — batch tylko dla jednej skonfigurowanej grupy słowników

Batch działa w tle (`mw.taskman.run_in_background`); notatki są wczytywane (`mw.col.get_note`) na głównym wątku przed startem — kolekcja Anki jest jednowątkowa, wątek roboczy tylko mutuje je w pamięci (ten sam wzorzec co batch AI/TTS), a zapisuje `CollectionOp` na głównym wątku. Postęp przez natywny pasek Anki (`common.progress.start_progress`/`update_progress`/`finish_progress` → `mw.progress`) — trzyma Anki „busy", więc automatyczna kopia zapasowa / sync nie wyskakuje NAD paskiem i nie blokuje Anuluj (kosztem zablokowania całego okna na czas batcha). Anulowanie: `update_progress` czyta `mw.progress.want_cancel()` → ustawia `cancel_flag["cancelled"]`, sprawdzane między notatkami. Po zakończeniu jeden `tooltip` z podsumowaniem (Zaktualizowano: N · Brak audio: M).

Przycisk w edytorze również działa w tle: `editor.saveNow(start)` najpierw zapisuje bieżące pola (świeżo wpisane słowo jest widoczne), potem fetch w `run_in_background`. Guard `_FETCHING` blokuje podwójne kliknięcie. Po zakończeniu wynik trafia do notatki złapanej na starcie — jeśli użytkownik przełączył kartę w trakcie, zmiany są zapisywane przez `mw.col.update_note()` zamiast do aktualnie wyświetlanej notatki.

## Konfiguracja (sekcja `dictionary` w config.json)

```json
{
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
    {"dictionaries": ["diki_uk", "diki_us"], "label": "Diki", "enabled": true}
  ]
}
```

- `max_retries` — liczba prób przy HTTP 429/5xx oraz błędach połączenia/timeoutach, przekazywana przez `process_note_group()` do `fetch_audio_group(max_retries=...)`
- `page_timeout` — timeout GET strony słownika (Oxford/Cambridge/Longman); przekazywany do `fetch_text(timeout=page_timeout)`
- `mp3_timeout` — timeout GET pliku MP3; przekazywany do `fetch_url(timeout=mp3_timeout)`
- `wiktionary_ipa_fallback` — `true` (domyślnie) = gdy primary IPA source (oxford/cambridge) zwróci `None`, próbuje Wiktionary API; `false` = wyłącza fallback; konfigurowalne w **Wymowa → Słownik**
- `diki_ipa_fallback` — gdy `true`, przy pobieraniu z Diki moduł próbuje uzupełnić IPA z `diki_ipa_fallback_source`
- `diki_ipa_fallback_source` — źródło IPA dla Diki (`wiktionary`, `oxford`, `cambridge`); jeśli źródło inne niż Wiktionary zwróci `None`, może zadziałać `wiktionary_ipa_fallback`
- Każdy przycisk może mieć listę słowników — pobiera UK i US naraz, zapisuje oba `[sound:...]` w jednym polu
- Te same wpisy `buttons` sterują też submenu w przeglądarce (`Pobierz z Diki`, `Pobierz z Oxford`, itd.)
- `ipa_format`: `"compact"` (jeden zapis gdy UK=US), `"both"`, `"uk_only"`, `"us_only"`
- IPA jest fetchowane, gdy słownik ma support: Oxford → oxford, Cambridge → cambridge; dla Diki tylko przez opcjonalny fallback `diki_ipa_fallback`; Longman nie ma IPA
- Wiktionary jest **wyłącznie IPA fallback** — nie dostarcza audio, nie pojawia się w `buttons`

## Smart fetch — kiedy co pobiera

| Stan pola audio | Stan pola IPA | Akcja |
|---|---|---|
| puste | puste | pobierz audio + IPA |
| pełne (`audio_skipped=True`) | puste | pobierz tylko IPA |
| puste | pełne | pobierz tylko audio |
| pełne | pełne | nic nie rób |

## Deduplikacja HTTP requestów

`fetch_audio_group` grupuje sources po base dictionary i pobiera stronę HTML **raz na słownik**, nawet gdy button ma `["oxford_uk", "oxford_us"]`. Wynikowy `page_cache` jest przekazywany do `ipa_service.fetch_ipa(html=...)`, który pomija własny GET gdy HTML jest dostępny.

W trybie batch (`browser_ui`) `batch_cache: dict = {}` jest tworzony raz przed pętlą po notatkach i przekazywany do `process_note_group(batch_cache=...)`. Klucz cache: `(word, tuple(sorted(sources)))`. Notatki z tym samym słowem nie generują ponownych requestów HTTP.

| Słownik | Sources w buttonie | Requesty (strona + MP3) |
|---|---|---|
| Oxford | `oxford_uk` + `oxford_us` | 1× strona + 2× MP3 = **3** (było 5) |
| Cambridge | `cambridge_uk` + `cambridge_us` | 1× strona + 2× MP3 = **3** (było 5) |
| Longman | `longman_uk` + `longman_us` | 1× strona + 2× MP3 = **3** (było 4, brak IPA) |
| Diki | `diki_uk` + `diki_us` | 2× MP3 bezpośrednio (bez scrapowania) |

## Scrapery HTML

Każdy słownik ma własną klasę parsera dziedziczącą po `html.parser.HTMLParser`:

- `OxfordAudioExtractor` — szuka `<div class="sound audio_play_button pron-uk icon-audio" data-src-mp3="...">`, bierze **pierwszy znaleziony URL** dla danego wariantu (bez walidacji słowa w URL — strona Oxford jest dedykowana jednemu hasłu)
- `CambridgeAudioExtractor` — szuka `<source type="audio/mpeg" src="...uk_pron...">`, ma dwustopniową logikę: `audio_url` (z walidacją `word_normalized` w URL) + `fallback_url` (pierwszy pasujący URL bez walidacji). Zwraca `audio_url or fallback_url`. Cambridge ma wiele wpisów na stronie, stąd walidacja ma tu sens jako preferencja.
- `LongmanAudioExtractor` — szuka `<span class="brefile" data-src-mp3="...">` (UK) lub `<span class="amefile" ...>` (US), bierze **pierwszy znaleziony URL** bez walidacji słowa
- Diki nie wymaga parsowania — URL jest deterministyczny: `diki.pl/images-common/en/mp3/{word}.mp3` (US: `en-ame/mp3/`). `_fetch_diki_audio` próbuje dwa warianty nazwy pliku: najpierw `_`-sanitizowany (zastępuje `-` → `_`, dla 99% haseł), a w razie 404 retry z zachowanym `-` (np. `sun-bleached.mp3`)

`_normalize_word(word)` → `word.lower().replace(' ', '_').replace('-', '_').replace("'", "")` używane przez `CambridgeAudioExtractor` (walidacja URL). `_fetch_diki_audio` używa własnej, lżejszej normalizacji (bez zamiany `-`) z dwuetapowym fallbackiem `_` → `-`.

## Zależności

- Stdlib tylko: `urllib.parse`, `html.parser`, `re`, `json`, `logging`, `dataclasses`, `typing`
- Anki API: `mw.col.media.write_data`, `mw.col.update_note`, `mw.col.get_note`, `mw.taskman`, `mw.progress` (natywny pasek batcha przez `common.progress`), `aqt.sound.av_player`, `CollectionOp` (batch), `editor.addButton`/`saveNow`/`loadNote`, `gui_hooks.editor_will_show_context_menu`
- Własne: `common` (`clean_html_normalized` re-eksportowany z pakietu), `common.http` (`fetch_url`, `fetch_text`)
- Brak pip packages

## Uwagi implementacyjne

- `fetch_text()` i `fetch_url()` z `common.http` są używane bezpośrednio przez `fetch_audio_group()` — parametry sieci (`max_retries`, `page_timeout`, `mp3_timeout`) przekazywane z `process_note_group()` → `config.get("max_retries", 3)` itp.
- `ipa_service` używa `fetch_text()` z `common.http`; parametry przekazywane przez `fetch_ipa()` z `service.py`; IPA respektuje te same limity co audio
- IPA fallback: gdy primary source (oxford/cambridge) zwraca `None`, automatycznie próbuje Wiktionary; wynik z Wiktionary jest oznaczony `source="wiktionary"` w `IPAResult`
- Wiktionary API: waliduje klucz `"*"` w `wikitext` przed dostępem
- Sygnatura `fetch_audio_group`: `(word, sources, max_retries=3, page_timeout=10, mp3_timeout=10, batch_cache=None)` — wartości domyślne jako bezpieczny fallback
- `ProcessNoteResult.audio_skipped = True` gdy pole audio ma treść → editor_ui wyświetla osobny tooltip
- Nazwa pliku audio jest sanityzowana (`re.sub(r"[^\w-]+", "_", word)`) — znaki typu `/` lub `"` w polu źródłowym nie psują zapisu do mediów
