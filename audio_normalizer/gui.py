import logging
import os

from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo, showWarning

from ..common import ADDON_NAME, start_progress, update_progress, finish_progress

from . import logic

logger = logging.getLogger(__name__)


def _get_normalizer_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("audio_normalizer", {})


def _sync_media_files(filenames: list[str]):
    """Re-read modified files through Anki's media API so hashes are updated."""
    media = mw.col.media
    media_dir = media.dir()

    for filename in filenames:
        filepath = os.path.join(media_dir, filename)
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath, "rb") as f:
                media.write_data(filename, f.read())
        except Exception as e:
            logger.error(f"Failed to sync media '{filename}': {e}")


def run_normalization():
    from shutil import which
    from . import config as _defaults

    cfg = _get_normalizer_config()
    ffmpeg_path = cfg.get("ffmpeg_path", "").strip()
    ffmpeg_cmd = ffmpeg_path if ffmpeg_path else _defaults.FFMPEG_CMD
    loudnorm_opts = cfg.get("loudnorm_opts", _defaults.LOUDNORM_OPTS) or _defaults.LOUDNORM_OPTS
    max_workers = int(cfg.get("max_workers", _defaults.MAX_WORKERS))

    if which(ffmpeg_cmd) is None:
        showWarning(f"Nie znaleziono programu '{ffmpeg_cmd}' w systemie.\nUpewnij się, że ffmpeg jest zainstalowany i dodany do zmiennej PATH.")
        return

    # Natywny pasek Anki (mw.progress): trzyma Anki „busy", więc automatyczna
    # kopia zapasowa / sync nie wyskakuje NAD paskiem i nie blokuje Anuluj.
    cancel_flag = start_progress("Normalizacja audio", 0, "Normalizacja Audio")

    def progress_cb(processed, total, filename):
        update_progress(cancel_flag, "Przetwarzanie", processed, total)

    def task():
        return logic.process_collection(
            progress_callback=progress_cb,
            max_workers=max_workers,
            ffmpeg_cmd=ffmpeg_cmd,
            loudnorm_opts=loudnorm_opts,
            should_cancel=lambda: cancel_flag["cancelled"],
        )

    def on_done(fut):
        finish_progress()
        try:
            count, errors, modified_files = fut.result()
        except Exception as e:
            logger.error(f"Critical error in normalization: {e}")
            showWarning(f"Błąd normalizacji: {e}", parent=mw)
            return

        # ffmpeg zmienił zawartość plików na dysku — Anki musi zaktualizować
        # hashe w swojej bazie, inaczej przy synchronizacji z AnkiWeb pliki
        # mogą zostać nadpisane starą wersją lub oznaczone jako nieużywane.
        if modified_files:
            _sync_media_files(modified_files)

        msg = f"Zakończono normalizację.\nPrzetworzono plików: {count}"
        if errors > 0:
            msg += f"\nBłędy: {errors} (szczegóły w logach Anki — konsola / debug log)"
        if cancel_flag["cancelled"]:
            msg += "\n(przerwano)"
        if count == 0 and errors == 0 and not cancel_flag["cancelled"]:
            msg = "Wszystkie pliki są już znormalizowane."

        showInfo(msg, parent=mw)

    mw.taskman.run_in_background(task, on_done)

def init_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools
    action = QAction("Normalizuj Audio (ffmpeg)", mw)
    action.triggered.connect(_confirm_and_run)
    menu.addAction(action)


def _confirm_and_run():
    result = QMessageBox.question(
        mw,
        "Normalizacja Audio",
        "Normalizacja zmodyfikuje pliki audio w kolekcji.\n"
        "Proces może potrwać kilka minut.\n\n"
        "Kontynuować?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if result == QMessageBox.StandardButton.Yes:
        run_normalization()
