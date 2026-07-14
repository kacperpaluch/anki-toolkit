# Anki Toolkit

Anki Toolkit to zestaw narzędzi wspierających przygotowanie i organizację
materiałów w Anki. Łączy generowanie treści przez AI, wymowę, workflowy,
reguły udostępniania kart oraz prywatne integracje w jednym dodatku.

Każdy moduł można włączyć lub wyłączyć. Interfejs ustawień grupuje funkcje według
zadań użytkownika, niezależnie od technicznego podziału kodu.

## Główny przepływ

Typowy proces przygotowania materiału wygląda tak:

```text
słowo lub notatka
      ↓
generowanie treści AI
      ↓
wymowa ze słownika lub TTS
      ↓
rozdzielenie przykładów na pola
      ↓
reguły stopniowego udostępniania kart
```

Kroki można połączyć w nazwany workflow i uruchamiać z edytora albo menu
kontekstowego przeglądarki Anki.

## Instalacja

1. Skopiuj katalog dodatku do `addons21/anki-toolkit/`.
2. Uruchom ponownie Anki.
3. Otwórz **Narzędzia → Anki Toolkit → Ustawienia…**.
4. W zakładce **Generowanie AI** skonfiguruj przynajmniej jednego dostawcę.
5. W **Wymowa** skonfiguruj TTS lub przyciski słowników.
6. W **Workflowy** wybierz kroki głównego procesu.

Normalizacja audio wymaga programu `ffmpeg` dostępnego w `PATH` albo wskazanego
w ustawieniach.

## Ustawienia

Nawigacja odpowiada zadaniom, a nie katalogom kodu:

| Obszar | Zawartość |
|---|---|
| **Start** | Gotowość głównego workflow, trwające batche i problemy blokujące |
| **Workflowy** | Nazwane procesy oraz ustawienia rozdzielania pól |
| **Generowanie AI** | Prompty, dostawcy, modele i opcje zaawansowane |
| **Wymowa** | TTS oraz nagrania i IPA ze słowników |
| **Reguły kart** | Sentence Unlocker, Sibling Manager, Homograph Manager, Deck Router i presety powtórek |
| **Integracje** | Kolejka słówek n8n oraz lokalny Web Bridge |
| **Moduły** | Włączanie i wyłączanie funkcji |
| **Konserwacja** | Normalizacja audio, czyszczenie HTML i ukrywanie pól |
| **Diagnostyka** | Statystyki użycia oraz logi |

Zmiana stanu modułu wymaga restartu Anki. Pozostałe ustawienia zwykle zaczynają
działać po zapisaniu dialogu.

## Funkcje

### Treść

- **Workflowy** wykonują kroki AI, słownika, TTS i rozdzielania pól w ustalonej
  kolejności.
- **AI Generator** wypełnia pola notatki pojedynczo lub wsadowo. Obsługuje
  dostawców OpenAI, Anthropic, Google, OpenRouter, CometAPI, Mistral, NVIDIA NIM
  i OpenCode Go.
- **Batch API** umożliwia asynchroniczny backfill przez OpenAI lub Anthropic.
- **Słownik** pobiera nagrania i IPA z Diki, Oxford, Cambridge, Longman oraz
  Wiktionary.
- **TTS** generuje dźwięk przez lokalny serwer Kokoro albo OpenRouter.
- **Field Splitter** dzieli jedno pole, np. `przyklad`, na `p1`, `p2`, `p3`.

Szczegóły: [AI Generator](ai_generator/README.md),
[TTS](tts/README.md), [Słownik](dictionary/README.md) i
[Field Splitter](field_splitter/README.md).

### Nauka

- **Sentence Unlocker** stopniowo tworzy karty kolejnych zdań, gdy wcześniejsze
  karty osiągną ustalony interwał.
- **Sibling Manager** tymczasowo zawiesza nowe siblingi niedojrzałej karty.
- **Homograph Manager** rozdziela osobne notatki z tym samym słowem (np. kilka
  znaczeń „assault") — kolejne znaczenie odblokowuje się dopiero, gdy poprzednie
  dojrzeje.
- **Deck Router** kieruje karty do talii według tagu i opcjonalnie szablonu.
- **Filtered Deck** udostępnia presety szybkich powtórek.

Szczegóły: [kontekst reguł nauki](learning-context.md),
[Sentence Unlocker](sentence_unlocker/README.md),
[Sibling Manager](sibling_manager/README.md),
[Homograph Manager](homograph_manager/README.md) i [Deck Router](deck_router/README.md).

### Integracje i konserwacja

- **Word Queue** pobiera słowa z tabeli n8n, wyświetla słowniki w Anki i oznacza
  rekord po dodaniu notatki.
- **Web Bridge** przyjmuje dane z userscriptu słownikowego na lokalnym adresie
  `127.0.0.1:8766`.
- **Audio Normalizer** normalizuje nagrania przez `ffmpeg` zgodnie z EBU R128.
- **Audio Embed** zamienia `[sound:...]` na osadzony `<audio class="ex-audio">`
  w wybranych typach notatek i polach (niezależnie od źródła audio).
- **HTML Cleanup** usuwa `&nbsp;` i normalizuje bloki `<div>`.
- **Field Hider** chowa wybrane pola wyłącznie w oknie dodawania notatki.

Szczegóły: [Word Queue](word_queue/README.md), [Web Bridge](web_bridge/README.md),
[normalizacja audio](audio_normalizer/README.md) i [Audio Embed](audio_embed/README.md).

## Konfiguracja i dane

`config.json` jest domyślnym szablonem. Anki zapisuje konfigurację użytkownika w
`meta.json`. Pełna referencja kluczy znajduje się w [config.md](config.md).

Dane, które mają przetrwać aktualizację dodatku, są zapisywane w `user_files/`:

- `usage_stats.json` — statystyki AI i TTS,
- `ai_batches.json` — stan Batch API,
- `audio_normalizer_history.json` — historia normalizacji.

Nie publikuj `meta.json` ani zawartości `user_files/`; mogą zawierać prywatną
konfigurację lub historię pracy.

## Bezpieczeństwo

- Klucze API pozostają w konfiguracji profilu Anki.
- Web Bridge nasłuchuje wyłącznie na `127.0.0.1` i sprawdza dozwolone źródła.
- Operacje sieciowe i audio wykonują się poza wątkiem interfejsu.
- Zmiany kolekcji Anki są zatwierdzane na jej głównym wątku.

## Rozwiązywanie problemów

1. Otwórz **Ustawienia → Diagnostyka → Logi**.
2. Włącz tryb debugowania i powtórz operację.
3. Sprawdź ekran Start — pokazuje wyłącznie problemy blokujące główny workflow.
4. W przypadku modułu włączonego lub wyłączonego uruchom ponownie Anki.
5. Dla normalizacji audio sprawdź `ffmpeg` w **Konserwacja**.

Testy czystej logiki można uruchomić bez Anki:

```bash
python3 tests/test_pure_logic.py
python3 tests/test_batch_backfill.py
python3 tests/test_editor_operations.py
python3 tests/test_sentence_unlocker.py
```

## Dla deweloperów i modeli AI

Codex automatycznie zaczyna od [AGENTS.md](AGENTS.md), który definiuje zasady
pracy i wymagane testy. Pozostałe narzędzia powinny następnie przeczytać
[llm-context.md](llm-context.md) — krótką mapę architektury i router do kontekstu
właściwego obszaru. Nie ma potrzeby czytania wszystkich plików modułowych przed
każdą zmianą.
