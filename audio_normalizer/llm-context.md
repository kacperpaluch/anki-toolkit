# LLM Context — audio_normalizer

## Co robi

Normalizuje głośność wszystkich plików audio w katalogu media Anki do standardu EBU R128 przez ffmpeg. Dostępne przez **Narzędzia → Anki Toolkit → Normalizuj Audio (ffmpeg)**. Pamięta przetworzone pliki — ponowne uruchomienie pomija już znormalizowane. Opcjonalna **auto-normalizacja** (`auto_normalize: true`) obserwuje katalog mediów i normalizuje nowe pliki w tle.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Entry point — `setup_menu(parent_menu=None)` rejestruje akcję w menu Anki Toolkit + `watcher.init_auto_normalize()` |
| `gui.py` | `run_normalization()` — czyta konfigurację przez `addonManager` (używa `common.ADDON_NAME`), uruchamia `logic.process_collection` przez `mw.taskman.run_in_background` z natywnym paskiem `mw.progress` (`common.progress`: `start_progress`/`update_progress`/`finish_progress`); w `on_done` wywołuje `_sync_media_files()` → `mw.col.media.write_data()` dla każdego zmodyfikowanego pliku. Nie ma już własnego `QThread`/`QDialog` — pasek `mw.progress` trzyma Anki „busy", więc backup/sync się odkłada i nie zasłania Anuluj |
| `logic.py` | Skanowanie media, historia, wywołania ffmpeg, równoległość; `process_collection(..., should_cancel=None)` zwraca `(count, errors, modified_files)` — `should_cancel()` pollowane między plikami (`executor.shutdown(cancel_futures=True)` + break); ffmpeg-i już działające w chwili anulowania dokańczają, a ich wyniki są dozbierane po wyjściu z puli (trafiają do historii i `modified_files`), inaczej kolejny przebieg znormalizowałby je drugi raz — dodatkowy stratny re-encode; `normalize_file` zwraca `(success, new_mtime)` |
| `config.py` | Wartości domyślne: `FFMPEG_CMD` (auto-detect), `LOUDNORM_OPTS`, `AUDIO_EXTENSIONS`, `MAX_WORKERS`, `AUTO_NORMALIZE` — używane jako fallback |
| `watcher.py` | Auto-normalizacja — `QFileSystemWatcher` na `mw.col.media.dir()` + `QTimer` debounce 3s + flaga `_normalizing` (ochrona przed feedback loop: ffmpeg temp+rename i `media.write_data` sync nie re-triggerują). `_run_auto_normalize()` czyta konfigurację na głównym wątku, po czym uruchamia `logic.process_collection` (ffmpeg) przez `mw.taskman.run_in_background` — **nie blokuje UI**; sync media DB (`media.write_data`) i tooltip wykonują się w `on_done` na głównym wątku, a `_normalizing` jest zwalniane dopiero tam (przez cały czas pracy chroni przed re-triggerem). Po normalizacji tooltip w prawym dolnym rogu ("Znormalizowano N plik(ów) audio.") jeśli `show_tooltip=true`. `init_auto_normalize()` rejestruje `gui_hooks.profile_did_open` (startuje watcher gdy `auto_normalize=true`) — wzorzec jak `nbsp_remover` (start natychmiast jeśli `mw.col` już otwarte) |

## Przepływ danych

```
Narzędzia → Anki Toolkit → Normalizuj Audio
  → run_normalization()
      → _get_normalizer_config()                    # addonManager.getConfig("anki-toolkit")["audio_normalizer"]
      → ffmpeg_cmd = cfg["ffmpeg_path"] lub auto-detect z config.FFMPEG_CMD
      → loudnorm_opts = cfg["loudnorm_opts"]
      → max_workers = cfg["max_workers"]
      → sprawdź czy ffmpeg dostępny (shutil.which)
      → start_progress("Normalizacja audio", 0, "Normalizacja Audio")   # common.progress → natywny mw.progress (Anki „busy")
      → mw.taskman.run_in_background(task, on_done)
          → task(): logic.process_collection(progress_cb, max_workers, ffmpeg_cmd, loudnorm_opts, should_cancel)
              → os.listdir(mw.col.media.dir())        # wszystkie pliki media
              → filtruj po config.AUDIO_EXTENSIONS
              → dla każdego: needs_processing(path, name, history)  # mtime check
              → ThreadPoolExecutor(max_workers)
                  → normalize_file(path, ffmpeg_cmd, loudnorm_opts)
                      → ffmpeg -i input -af loudnorm_opts -y input.temp{ext}
                        # temp zachowuje oryginalne rozszerzenie — ffmpeg wnioskuje
                        # format wyjściowy z rozszerzenia, więc .wav/.ogg/.flac
                        # nie są po cichu re-enkodowane do MP3
                      → os.replace(temp, input)         # atomic replace
                      → return (True, new_mtime)
              → save_history(history)                   # zapisz mtime
              → return (count, errors, modified_files)
          → progress_cb(processed, total, name) → update_progress(...) (główny wątek, czyta want_cancel → cancel_flag)
          → on_done(fut) (główny wątek):
              → finish_progress()
              → _sync_media_files(modified_files)       # mw.col.media.write_data() dla każdego pliku
              → showInfo z liczbą przetworzonych / błędów (+ „(przerwano)" gdy anulowano)
```

## Konfiguracja (sekcja `audio_normalizer` w config.json)

```json
{
    "ffmpeg_path": "",
    "loudnorm_opts": "loudnorm=I=-14:TP=-1.5:LRA=8",
    "max_workers": 4,
    "auto_normalize": false
}
```

- `ffmpeg_path` — puste `""` = auto-detect przez `config.find_ffmpeg()` (PATH → /opt/homebrew → /usr/local → /usr)
- `loudnorm_opts` — pełny string opcji ffmpeg filtra loudnorm
- `max_workers` — liczba równoległych procesów ffmpeg
- `auto_normalize` — `true` = włącza watcher na katalogu mediów (nowe/zmienione pliki normalizowane automatycznie ~3s po dodaniu; debounce zbiera serie zapisów); domyślnie `false`; wymaga restartu Anki po zmianie

Edytowalne przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Normalizacja**. Zakładka zawiera przycisk **"Sprawdź"** przy polu ścieżki ffmpeg — testuje dostępność i wyświetla wersję przez `tooltip()`.

`config.py` zawiera wartości domyślne używane gdy klucz nie istnieje w konfiguracji profilu. `AUDIO_EXTENSIONS` (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`) nie jest konfigurowalny przez UI.

## Pliki danych (w katalogu modułu)

| Plik | Zawartość |
|---|---|
| `user_files/audio_normalizer_history.json` | `{"filename.mp3": mtime_float, ...}` |

Ścieżka wyznaczana przez `os.path.join(addon_dir, "user_files", HISTORY_FILE)` — katalog `user_files/` przeżywa aktualizacje wtyczki (katalogi modułów są nadpisywane). Legacy `processed_history.json` w katalogu modułu jest automatycznie migrowane. Błędy ffmpeg trafiają do standardowego loggera Python (`logging.getLogger(__name__)`).

## Logika skip (needs_processing)

Plik jest pomijany jeśli jest w historii **i** jego `mtime` zgadza się z zapisanym (tolerancja 1s). Po normalizacji ffmpeg zmienia mtime — nowy mtime jest zapisywany do historii.

## Jak gui.py czyta konfigurację

```python
from ..common import ADDON_NAME

def _get_normalizer_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("audio_normalizer", {})
```

Wartości konfiguracji są odczytane na głównym wątku w `run_normalization()` i przekazane do `task()` przez closure — worker (`logic.process_collection`) nie dotyka `addonManager` podczas pracy w tle. `task()` zwraca `(count, errors, modified_files)` przez `future`.

`on_done(fut)` woła `finish_progress()`, potem `_sync_media_files(modified_files)` przed podsumowaniem — każdy plik jest re-readowany przez `mw.col.media.write_data()`, aby zaktualizować hash w Anki media DB. Anulowanie: `should_cancel=lambda: cancel_flag["cancelled"]`; `cancel_flag` jest ustawiane przez `update_progress` (czyta `mw.progress.want_cancel()` na głównym wątku). Pliki dokończone przez ffmpeg po anulowaniu też trafiają do historii i `modified_files` (dozbierane po wyjściu z puli), więc są zsynchronizowane z media DB i nie będą normalizowane ponownie.

## Zależności

- Stdlib: `os`, `json`, `subprocess`, `concurrent.futures`, `shutil`, `time`
- Anki API: `mw.col.media.dir()`, `mw.col.media.write_data()`, `mw.addonManager.getConfig()`, `mw.taskman.run_in_background`, `mw.progress` (natywny pasek przez `common.progress`), `gui_hooks.profile_did_open`
- Własne: `common.ADDON_NAME`, `common.progress` (`start_progress`/`update_progress`/`finish_progress`)
- PyQt6: `QFileSystemWatcher`, `QTimer` (watcher), `QAction`, `QMessageBox` (menu/potwierdzenie)
- Wymaga zainstalowanego **ffmpeg** w systemie
- Brak pip packages
