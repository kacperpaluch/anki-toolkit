"""Audio Normalizer — ffmpeg loudnorm for the media folder, manual or watched."""
import logging
import os
import threading
from shutil import which

from aqt import gui_hooks, mw
from aqt.qt import QFileSystemWatcher, QMessageBox, QTimer
from aqt.utils import showInfo, showWarning, tooltip

from ..common import get_module_config
from .config import LOUDNORM_OPTS, MAX_WORKERS, find_ffmpeg
from .logic import process_media_dir

log = logging.getLogger(__name__)
_DEFAULTS = {"ffmpeg_path":"", "loudnorm_opts":LOUDNORM_OPTS, "max_workers":MAX_WORKERS, "auto_normalize":False, "show_tooltip":True}
_watcher = None
_timer = None
_normalizing = False
_rescan = False
_cancel = None

def get_config(): return get_module_config("audio_normalizer", _DEFAULTS)
def _ffmpeg(cfg): return cfg["ffmpeg_path"].strip() or find_ffmpeg()

def _sync_media(collection, filenames):
    if mw.col is not collection:
        return
    media = collection.media
    for name in filenames:
        path = os.path.join(media.dir(), name)
        if os.path.exists(path):
            try:
                with open(path, "rb") as file: media.write_data(name, file.read())
            except Exception as error: log.error("Media sync failed for %s: %s", name, error)

def run_normalization(automatic=False):
    global _normalizing, _rescan, _cancel
    if mw.col is None:
        return
    if _normalizing:
        _rescan = True
        return
    cfg = get_config(); command = _ffmpeg(cfg)
    if which(command) is None:
        if not automatic: showWarning(f"Nie znaleziono programu '{command}'.")
        else: log.warning("ffmpeg not found: %s", command)
        return
    collection = mw.col
    media_dir = collection.media.dir()  # collection access stays on the main thread
    _normalizing = True
    _rescan = False
    cancel = _cancel = threading.Event()
    def task(): return process_media_dir(media_dir, max_workers=cfg["max_workers"], ffmpeg_cmd=command, loudnorm_opts=cfg["loudnorm_opts"], should_cancel=cancel.is_set)
    def done(future):
        global _normalizing
        try:
            count, errors, modified = future.result()
            if mw.col is not collection or cancel.is_set():
                return
            _sync_media(collection, modified)
            if automatic:
                if cfg["show_tooltip"] and count: tooltip(f"Znormalizowano {count} plik(ów) audio.", parent=mw, period=4000)
            else:
                showInfo(f"Zakończono normalizację.\nPrzetworzono plików: {count}" + (f"\nBłędy: {errors}" if errors else ""), parent=mw)
        except Exception as error:
            log.exception("Normalization failed")
            if not automatic and mw.col is collection and not cancel.is_set():
                showWarning(f"Błąd normalizacji: {error}", parent=mw)
        finally:
            _normalizing = False
            if _rescan and _timer is not None and mw.col is not None:
                _timer.start()
    try:
        mw.taskman.run_in_background(task, done)
    except Exception:
        _normalizing = False
        raise

def confirm_normalization():
    if QMessageBox.question(mw, "Normalizacja Audio", "Normalizacja zmodyfikuje pliki audio w kolekcji. Kontynuować?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: run_normalization()

def _changed(_path):
    global _rescan
    if _normalizing:
        _rescan = True  # includes our own writes; the history makes the next scan cheap
    elif _timer is not None:
        _timer.start()

def _stop_watcher(*_args):
    global _watcher, _timer, _rescan
    if _cancel is not None:
        _cancel.set()
    if _timer is not None:
        _timer.stop()
        _timer.deleteLater()
    if _watcher is not None:
        _watcher.blockSignals(True)
        _watcher.deleteLater()
    _watcher = _timer = None
    _rescan = False

def _start_watcher(*_args):
    global _watcher, _timer
    if _watcher is not None or mw.col is None or not get_config()["auto_normalize"]: return
    _watcher = QFileSystemWatcher(); _watcher.addPath(mw.col.media.dir()); _watcher.directoryChanged.connect(_changed)
    _timer = QTimer(); _timer.setSingleShot(True); _timer.setInterval(3000); _timer.timeout.connect(lambda: run_normalization(automatic=True))

gui_hooks.profile_did_open.append(_start_watcher)
gui_hooks.profile_will_close.append(_stop_watcher)
