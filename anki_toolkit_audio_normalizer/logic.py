"""ffmpeg and history logic; workers receive media_dir and never access Anki."""
import concurrent.futures
import json
import logging
import os
import subprocess
from pathlib import Path

from .config import AUDIO_EXTENSIONS, LOUDNORM_OPTS, MAX_WORKERS

log = logging.getLogger(__name__)


def history_path() -> Path:
    return Path(__file__).parent / "user_files" / "audio_normalizer_history.json"


def load_history() -> dict:
    try:
        return json.loads(history_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_history(history: dict) -> None:
    path = history_path()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def needs_processing(path: str, filename: str, history: dict) -> bool:
    try:
        return filename not in history or abs(os.path.getmtime(path) - history[filename]) > 1.0
    except OSError:
        return True


def normalize_file(path: str, ffmpeg_cmd: str, loudnorm_opts: str) -> tuple[bool, float | None]:
    extension = os.path.splitext(path)[1] or ".mp3"
    temp_path = path + ".temp" + extension
    try:
        subprocess.run([ffmpeg_cmd, "-i", path, "-af", loudnorm_opts, "-y", temp_path], check=True, capture_output=True)
        os.replace(temp_path, path)
        return True, os.path.getmtime(path)
    except Exception as error:
        log.error("Audio normalizer failed for %s: %s", os.path.basename(path), error)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False, None


def process_media_dir(media_dir: str, progress_callback=None, max_workers: int = MAX_WORKERS,
                      ffmpeg_cmd: str = "ffmpeg", loudnorm_opts: str = LOUDNORM_OPTS,
                      should_cancel=None) -> tuple[int, int, list[str]]:
    """Normalize pending audio files. Safe to execute in a background worker."""
    history = load_history()
    files = [name for name in os.listdir(media_dir) if name.lower().endswith(AUDIO_EXTENSIONS)]
    history = {name: stamp for name, stamp in history.items() if name in set(files)}
    pending = [name for name in files if needs_processing(os.path.join(media_dir, name), name, history)]
    modified, errors, completed = [], 0, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as executor:
        futures = {executor.submit(normalize_file, os.path.join(media_dir, name), ffmpeg_cmd, loudnorm_opts): name for name in pending}
        for future in concurrent.futures.as_completed(futures):
            if should_cancel and should_cancel():
                for candidate in futures:
                    candidate.cancel()
                break
            name = futures[future]
            ok, stamp = future.result()
            completed += 1
            if ok:
                modified.append(name)
                history[name] = stamp
            else:
                errors += 1
            if progress_callback:
                progress_callback(completed, len(pending), name)
    save_history(history)
    return completed, errors, modified
