# Normalizacja audio — wyrównywanie głośności

Normalizuje głośność wszystkich plików audio w katalogu media Anki do standardu EBU R128 przez `ffmpeg`. Eliminuje problem zbyt cichych lub zbyt głośnych nagrań.

## Wymagania

Zainstalowany `ffmpeg` w systemie:
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`
- **Windows:** pobierz z ffmpeg.org i dodaj do PATH

Wtyczka automatycznie wykrywa ścieżkę do `ffmpeg` (PATH, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`). Możesz też podać ścieżkę ręcznie w ustawieniach.

## Jak używać

**Narzędzia → Anki Toolkit → Normalizuj Audio (ffmpeg)**

Wtyczka skanuje katalog media Anki, pomija pliki już przetworzone i normalizuje pozostałe. Postęp widać na **natywnym pasku Anki** z przyciskiem **Anuluj** — na czas przetwarzania okno Anki jest zablokowane, dzięki czemu automatyczna kopia zapasowa / synchronizacja nie wyskakuje w środku operacji. Po zakończeniu wyświetlane jest podsumowanie z liczbą przetworzonych plików i ewentualnych błędów.

### Auto-normalizacja

W **Ustawienia → Konserwacja → Normalizacja audio** zaznacz **Auto-normalizuj nowe pliki audio**. Watcher obserwuje katalog mediów Anki i automatycznie normalizuje nowe/zmienione pliki ~3s po dodaniu (debounce zbiera serie zapisów — np. TTS generujący 20 plików w kilku sekundach traktowany jest jako jeden batch). Normalizacja (ffmpeg) działa **w tle** — Anki nie zamraża się podczas przetwarzania.

Obejmuje **wszystkie źródła**:
- TTS (Kokoro/OpenRouter) — batch i edytor
- Pobieranie audio ze słowników (Oxford/Cambridge/Diki/Longman)
- Workflow AI → Dict → TTS
- Ręczne dodanie pliku do karty
- AnkiWeb sync pobierający nowe media

Po normalizacji pojawia się krótki tooltip w prawym dolnym rogu ("Znormalizowano N plik(ów) audio."). Aby go wyłączyć, ustaw `audio_normalizer.show_tooltip: false` w konfiguracji profilu. Pomija pliki już przetworzone (historia `mtime` w `audio_normalizer_history.json`). Wymaga restartu Anki po zmianie ustawienia.

## Co się dzieje z plikami

1. Wtyczka tworzy plik tymczasowy z zachowaniem oryginalnego rozszerzenia (np. `plik.mp3.temp.mp3`, `plik.wav.temp.wav`) — dzięki temu ffmpeg zachowuje format pliku i nie re-enkoduje `.wav`/`.ogg`/`.flac` do MP3
2. `ffmpeg` przetwarza oryginał → temp z filtrem `loudnorm`
3. Plik tymczasowy zastępuje oryginał (`os.replace` — atomowa operacja)
4. Nowy `mtime` pliku jest zapisywany do historii
5. **Synchronizacja z Anki Media DB:** po zakończeniu normalizacji każdy zmodyfikowany plik jest re-readowany przez `mw.col.media.write_data()`, co aktualizuje hash w bazie mediów Anki. Dzięki temu przy synchronizacji z AnkiWeb pliki nie zostaną nadpisane starą wersją ani oznaczone jako nieużywane.

## Historia przetworzonych plików

Plik `audio_normalizer_history.json` w katalogu `user_files/` (przeżywa aktualizacje wtyczki) przechowuje `mtime` każdego przetworzonego pliku. Przy kolejnym uruchomieniu:
- Plik jest w historii **i** `mtime` się zgadza → **pomiń**
- Plik jest nowy lub zmieniony → **przetwórz**

Dzięki temu ponowne uruchomienie jest szybkie — przetwarza tylko nowe lub zmienione pliki.

## Parametry normalizacji (EBU R128)

Standard używany przez nadawców radiowych i serwisy streamingowe.

| Parametr | Wartość domyślna | Znaczenie |
|---|---|---|
| `I` | `-14 LUFS` | Głośność zintegrowana (perceived loudness) |
| `TP` | `-1.5 dBTP` | Maksymalny poziom szczytowy (true peak) |
| `LRA` | `8 LU` | Zakres głośności (loudness range) |

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → Konserwacja → Normalizacja audio**

| Pole | Domyślnie | Opis |
|---|---|---|
| `ffmpeg_path` | `""` (auto-detect) | Pełna ścieżka do ffmpeg — puste = wykryj automatycznie |
| `loudnorm_opts` | `loudnorm=I=-14:TP=-1.5:LRA=8` | Parametry filtra loudnorm |
| `max_workers` | `4` | Liczba równoległych wątków ffmpeg |
| `auto_normalize` | `false` | Włącz watcher na katalogu mediów — auto-normalizacja nowych plików |

```json
"audio_normalizer": {
    "ffmpeg_path": "",
    "loudnorm_opts": "loudnorm=I=-14:TP=-1.5:LRA=8",
    "max_workers": 4,
    "auto_normalize": false
}
```

> `config.py` w katalogu modułu zawiera wartości domyślne używane jako fallback gdy sekcja `audio_normalizer` nie istnieje w konfiguracji profilu.

## Logi błędów

Błędy ffmpeg są logowane przez standardowy logger Python (`logging`). Są widoczne w konsoli Anki, Debug Console albo w narzędziu zbierającym logi z uruchomionej aplikacji.
