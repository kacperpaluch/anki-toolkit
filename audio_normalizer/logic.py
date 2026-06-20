import os
import json
import logging
import subprocess
import concurrent.futures
import time
from aqt import mw
from . import config

logger = logging.getLogger(__name__)

HISTORY_FILE = "audio_normalizer_history.json"
_LEGACY_HISTORY = os.path.join(os.path.dirname(__file__), "processed_history.json")

def get_history_path():
    # user_files/ survives addon updates — module dirs are wiped on update,
    # and losing the history would re-normalize (re-encode) every file.
    addon_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(addon_dir, "user_files", HISTORY_FILE)

def _migrate_legacy_history():
    path = get_history_path()
    try:
        if os.path.exists(_LEGACY_HISTORY) and not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            os.replace(_LEGACY_HISTORY, path)
    except OSError:
        pass

_migrate_legacy_history()

def load_history():
    """Ładuje historię przetworzonych plików."""
    path = get_history_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(history):
    """Zapisuje historię przetworzonych plików."""
    path = get_history_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

def needs_processing(file_path, filename, history):
    """Sprawdza, czy plik wymaga normalizacji (nie ma go w historii lub zmieniła się data modyfikacji)."""
    if filename not in history:
        return True
    
    try:
        current_mtime = os.path.getmtime(file_path)
        # Jeśli plik na dysku jest nowszy niż ten w historii (lub różni się znacząco), przetwarzamy
        # Uwaga: ffmpeg nadpisze plik, zmieniając mtime, więc musimy to uwzględnić po przetworzeniu.
        # Porównujemy czy zapisany mtime zgadza się z obecnym.
        last_processed_mtime = history[filename]
        
        # Mała tolerancja dla różnic systemów plików
        if abs(current_mtime - last_processed_mtime) > 1.0:
            return True
    except OSError:
        return True
        
    return False

def normalize_file(file_path, ffmpeg_cmd=None, loudnorm_opts=None):
    """
    Uruchamia ffmpeg dla pojedynczego pliku.
    Zwraca (success: bool, new_mtime: float | None).
    """
    ffmpeg_cmd = ffmpeg_cmd or config.FFMPEG_CMD
    loudnorm_opts = loudnorm_opts or config.LOUDNORM_OPTS

    # Keep the original extension — ffmpeg infers the output format from it.
    # A ".temp.mp3" suffix would silently re-encode .wav/.ogg/.flac to MP3.
    ext = os.path.splitext(file_path)[1] or ".mp3"
    temp_path = file_path + ".temp" + ext

    cmd = [
        ffmpeg_cmd,
        "-i", file_path,
        "-af", loudnorm_opts,
        "-y",
        temp_path
    ]

    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        subprocess.run(cmd, check=True, capture_output=True, startupinfo=startupinfo)

        os.replace(temp_path, file_path)
        new_mtime = os.path.getmtime(file_path)
        return True, new_mtime
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr output"
        logger.error(f"FFmpeg error for {os.path.basename(file_path)}: {error_msg}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False, None
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return False, None

def process_collection(progress_callback=None, max_workers=None, ffmpeg_cmd=None, loudnorm_opts=None):
    """
    Główna funkcja przetwarzająca.
    progress_callback(processed_count, total_count, current_filename)

    Returns:
        (processed_count, errors, modified_files) — modified_files to lista nazw plików
        które zostały znormalizowane (do synchronizacji z Anki media DB).
    """
    max_workers = max_workers or config.MAX_WORKERS
    ffmpeg_cmd = ffmpeg_cmd or config.FFMPEG_CMD
    loudnorm_opts = loudnorm_opts or config.LOUDNORM_OPTS

    media_dir = mw.col.media.dir()
    history = load_history()

    all_files = os.listdir(media_dir)
    audio_files = [f for f in all_files if f.lower().endswith(config.AUDIO_EXTENSIONS)]

    # ponytail: prune stale entries — files deleted from media dir stay in
    # history forever without this. Re-downloads are already caught by mtime
    # mismatch, but stale entries bloat the file. Upgrade: content hash if
    # mtime collisions ever become a real problem.
    existing = set(audio_files)
    history = {k: v for k, v in history.items() if k in existing}

    files_to_process = []
    for f in audio_files:
        full_path = os.path.join(media_dir, f)
        if needs_processing(full_path, f, history):
            files_to_process.append(f)

    total = len(files_to_process)
    if total == 0:
        return 0, 0, []

    processed_count = 0
    errors = 0
    modified_files = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(normalize_file, os.path.join(media_dir, f), ffmpeg_cmd, loudnorm_opts): f
            for f in files_to_process
        }

        for i, future in enumerate(concurrent.futures.as_completed(future_to_file)):
            filename = future_to_file[future]
            success, new_mtime = future.result()

            if success:
                modified_files.append(filename)
                history[filename] = new_mtime
            else:
                errors += 1

            processed_count += 1
            if progress_callback:
                progress_callback(processed_count, total, filename)

    save_history(history)
    return processed_count, errors, modified_files
