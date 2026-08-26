"""Anki Toolkit: Audio Normalizer."""
import logging
import os
from shutil import which

from aqt import gui_hooks, mw
from aqt.qt import QAction, QFileSystemWatcher, QMessageBox, QTimer
from aqt.utils import showInfo, showWarning, tooltip

from .config import LOUDNORM_OPTS, MAX_WORKERS, find_ffmpeg
from .logic import process_media_dir

log = logging.getLogger(__name__)
_DEFAULTS = {"ffmpeg_path":"", "loudnorm_opts":LOUDNORM_OPTS, "max_workers":MAX_WORKERS, "auto_normalize":False, "show_tooltip":True}
_watcher = None
_timer = None
_normalizing = False

def _addon_name(): return __name__.split(".")[0]
def get_config(): return {**_DEFAULTS, **(mw.addonManager.getConfig(_addon_name()) or {})}
def save_config(changes):
    cfg = mw.addonManager.getConfig(_addon_name()) or {}; cfg.update(changes); mw.addonManager.writeConfig(_addon_name(), cfg)
def _ffmpeg(cfg): return cfg["ffmpeg_path"].strip() or find_ffmpeg()

def _sync_media(filenames):
    media = mw.col.media
    for name in filenames:
        path = os.path.join(media.dir(), name)
        if os.path.exists(path):
            try:
                with open(path, "rb") as file: media.write_data(name, file.read())
            except Exception as error: log.error("Media sync failed for %s: %s", name, error)

def run_normalization(automatic=False):
    global _normalizing
    if _normalizing: return
    cfg = get_config(); command = _ffmpeg(cfg)
    if which(command) is None:
        if not automatic: showWarning(f"Nie znaleziono programu '{command}'.")
        else: log.warning("ffmpeg not found: %s", command)
        return
    media_dir = mw.col.media.dir()  # collection access stays on the main thread
    _normalizing = True
    def task(): return process_media_dir(media_dir, max_workers=cfg["max_workers"], ffmpeg_cmd=command, loudnorm_opts=cfg["loudnorm_opts"])
    def done(future):
        global _normalizing
        try:
            count, errors, modified = future.result(); _sync_media(modified)
            if automatic:
                if cfg["show_tooltip"] and count: tooltip(f"Znormalizowano {count} plik(ów) audio.", parent=mw, period=4000)
            else:
                showInfo(f"Zakończono normalizację.\nPrzetworzono plików: {count}" + (f"\nBłędy: {errors}" if errors else ""), parent=mw)
        except Exception as error:
            log.exception("Normalization failed")
            if not automatic: showWarning(f"Błąd normalizacji: {error}", parent=mw)
        finally: _normalizing = False
    mw.taskman.run_in_background(task, done)

def _confirm():
    if QMessageBox.question(mw, "Normalizacja Audio", "Normalizacja zmodyfikuje pliki audio w kolekcji. Kontynuować?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: run_normalization()

def _changed(_path):
    if not _normalizing and _timer is not None: _timer.start()
def _start_watcher(*_args):
    global _watcher, _timer
    if _watcher is not None or not get_config()["auto_normalize"]: return
    _watcher = QFileSystemWatcher(); _watcher.addPath(mw.col.media.dir()); _watcher.directoryChanged.connect(_changed)
    _timer = QTimer(); _timer.setSingleShot(True); _timer.setInterval(3000); _timer.timeout.connect(lambda: run_normalization(automatic=True))

def _setup_menu(*_args):
    from .settings import open_settings
    menu = mw.form.menuTools.addMenu("Anki Toolkit: Audio Normalizer")
    configure = QAction("Ustawienia…", menu); configure.triggered.connect(open_settings); menu.addAction(configure); menu.addSeparator()
    run = QAction("Normalizuj audio (ffmpeg)…", menu); run.triggered.connect(_confirm); menu.addAction(run)
    mw.addonManager.setConfigAction(_addon_name(), open_settings)

gui_hooks.profile_did_open.append(_start_watcher)
if hasattr(gui_hooks, "main_window_did_init"): gui_hooks.main_window_did_init.append(_setup_menu)
else: QTimer.singleShot(0, _setup_menu)
