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

Wtyczka skanuje katalog media Anki, pomija pliki już przetworzone i normalizuje pozostałe. Postęp widoczny jest w oknie dialogowym. Po zakończeniu wyświetlane jest podsumowanie z liczbą przetworzonych plików i ewentualnych błędów.

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

**Narzędzia → Anki Toolkit → Ustawienia... → zakładka Normalizacja**

| Pole | Domyślnie | Opis |
|---|---|---|
| `ffmpeg_path` | `""` (auto-detect) | Pełna ścieżka do ffmpeg — puste = wykryj automatycznie |
| `loudnorm_opts` | `loudnorm=I=-14:TP=-1.5:LRA=8` | Parametry filtra loudnorm |
| `max_workers` | `4` | Liczba równoległych wątków ffmpeg |

```json
"audio_normalizer": {
    "ffmpeg_path": "",
    "loudnorm_opts": "loudnorm=I=-14:TP=-1.5:LRA=8",
    "max_workers": 4
}
```

> `config.py` w katalogu modułu zawiera wartości domyślne używane jako fallback gdy sekcja `audio_normalizer` nie istnieje w konfiguracji profilu.

## Logi błędów

Błędy ffmpeg są logowane przez standardowy logger Python (`logging`). Są widoczne w konsoli Anki, Debug Console albo w narzędziu zbierającym logi z uruchomionej aplikacji.
