# LLM Context — audio_normalizer

## Co robi

Normalizuje głośność wszystkich plików audio w katalogu media Anki do standardu EBU R128 przez ffmpeg. Dostępne przez **Narzędzia → Anki Toolkit → Normalizuj Audio (ffmpeg)**. Pamięta przetworzone pliki — ponowne uruchomienie pomija już znormalizowane.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Entry point — `setup_menu(parent_menu=None)` rejestruje akcję w menu Anki Toolkit |
| `gui.py` | `ProgressDialog` (Qt) + `Worker(QThread)` — czyta konfigurację przez `addonManager` (używa `common.ADDON_NAME`), przekazuje parametry do `logic.process_collection`; po zakończeniu wywołuje `_sync_media_files()` → `mw.col.media.write_data()` dla każdego zmodyfikowanego pliku |
| `logic.py` | Skanowanie media, historia, wywołania ffmpeg, równoległość; `process_collection` zwraca `(count, errors, modified_files)`; `normalize_file` zwraca `(success, new_mtime)` |
| `config.py` | Wartości domyślne: `FFMPEG_CMD` (auto-detect), `LOUDNORM_OPTS`, `AUDIO_EXTENSIONS`, `MAX_WORKERS` — używane jako fallback |

## Przepływ danych

```
Narzędzia → Anki Toolkit → Normalizuj Audio
  → run_normalization()
      → _get_normalizer_config()                    # addonManager.getConfig("anki-toolkit")["audio_normalizer"]
      → ffmpeg_cmd = cfg["ffmpeg_path"] lub auto-detect z config.FFMPEG_CMD
      → loudnorm_opts = cfg["loudnorm_opts"]
      → max_workers = cfg["max_workers"]
      → sprawdź czy ffmpeg dostępny (shutil.which)
      → ProgressDialog.show()
      → Worker(max_workers, ffmpeg_cmd, loudnorm_opts).start()
          → logic.process_collection(callback, max_workers, ffmpeg_cmd, loudnorm_opts)
              → os.listdir(mw.col.media.dir())        # wszystkie pliki media
              → filtruj po config.AUDIO_EXTENSIONS
              → dla każdego: needs_processing(path, name, history)  # mtime check
              → ThreadPoolExecutor(max_workers)
                  → normalize_file(path, ffmpeg_cmd, loudnorm_opts)
                      → ffmpeg -i input -af loudnorm_opts -y temp.mp3
                      → os.replace(temp, input)         # atomic replace
                      → return (True, new_mtime)
              → save_history(history)                   # zapisz mtime
              → return (count, errors, modified_files)
          → Worker emituje sygnały Qt do ProgressDialog
          → on_finished(count, errors, modified_files)
              → _sync_media_files(modified_files)       # mw.col.media.write_data() dla każdego pliku
  → showInfo z liczbą przetworzonych / błędów
```

## Konfiguracja (sekcja `audio_normalizer` w config.json)

```json
{
    "ffmpeg_path": "",
    "loudnorm_opts": "loudnorm=I=-14:TP=-1.5:LRA=8",
    "max_workers": 4
}
```

- `ffmpeg_path` — puste `""` = auto-detect przez `config.find_ffmpeg()` (PATH → /opt/homebrew → /usr/local → /usr)
- `loudnorm_opts` — pełny string opcji ffmpeg filtra loudnorm
- `max_workers` — liczba równoległych procesów ffmpeg

Edytowalne przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Normalizacja**. Zakładka zawiera przycisk **"Sprawdź"** przy polu ścieżki ffmpeg — testuje dostępność i wyświetla wersję przez `tooltip()`.

`config.py` zawiera wartości domyślne używane gdy klucz nie istnieje w konfiguracji profilu. `AUDIO_EXTENSIONS` (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`) nie jest konfigurowalny przez UI.

## Pliki danych (w katalogu modułu)

| Plik | Zawartość |
|---|---|
| `processed_history.json` | `{"filename.mp3": mtime_float, ...}` |

Ścieżka wyznaczana przez `os.path.dirname(__file__)` — zawsze względem katalogu modułu. Błędy ffmpeg trafiają do standardowego loggera Python (`logging.getLogger(__name__)`).

## Logika skip (needs_processing)

Plik jest pomijany jeśli jest w historii **i** jego `mtime` zgadza się z zapisanym (tolerancja 1s). Po normalizacji ffmpeg zmienia mtime — nowy mtime jest zapisywany do historii.

## Jak gui.py czyta konfigurację

```python
from ..common import ADDON_NAME

def _get_normalizer_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("audio_normalizer", {})
```

`Worker` otrzymuje wartości przy tworzeniu (`__init__`) — jest odizolowany od addonManager podczas działania w wątku. Sygnał `finished_processing` emituje `(count, errors, modified_files)` — lista nazw plików które zostały znormalizowane.

`on_finished(count, errors, modified_files)` wywołuje `_sync_media_files(modified_files)` przed wyświetleniem podsumowania — każdy plik jest re-readowany przez `mw.col.media.write_data()` aby zaktualizować hash w Anki media DB.

`start_normalization` zatrzymuje poprzedni worker przed stworzeniem nowego (guard przed podwójnym wywołaniem):

```python
def start_normalization(self, max_workers, ffmpeg_cmd, loudnorm_opts):
    if self.worker is not None and self.worker.isRunning():
        self.worker.quit()
        self.worker.wait()
    self.worker = Worker(...)
    ...
```

## Zależności

- Stdlib: `os`, `json`, `subprocess`, `concurrent.futures`, `shutil`, `time`
- Anki API: `mw.col.media.dir()`, `mw.addonManager.getConfig()`
- Własne: `common.ADDON_NAME`
- PyQt6: `QThread`, `pyqtSignal`, `QDialog`, `QProgressBar`
- Wymaga zainstalowanego **ffmpeg** w systemie
- Brak pip packages
