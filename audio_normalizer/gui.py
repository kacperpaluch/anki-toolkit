import logging
import os

from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo, showWarning

from ..common import ADDON_NAME

from . import logic

logger = logging.getLogger(__name__)


def _get_normalizer_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("audio_normalizer", {})


class Worker(QThread):
    """Wątek roboczy wykonujący normalizację w tle."""
    progress_update = pyqtSignal(int, int, str) # processed, total, filename
    finished_processing = pyqtSignal(int, int, list) # processed_count, errors, modified_files

    def __init__(self, max_workers: int, ffmpeg_cmd: str, loudnorm_opts: str):
        super().__init__()
        self._max_workers = max_workers
        self._ffmpeg_cmd = ffmpeg_cmd
        self._loudnorm_opts = loudnorm_opts

    def run(self):
        def callback(processed, total, filename):
            self.progress_update.emit(processed, total, filename)

        try:
            count, errors, modified_files = logic.process_collection(
                progress_callback=callback,
                max_workers=self._max_workers,
                ffmpeg_cmd=self._ffmpeg_cmd,
                loudnorm_opts=self._loudnorm_opts,
            )
            self.finished_processing.emit(count, errors, modified_files)
        except Exception as e:
            logger.error(f"Critical error in worker: {e}")
            self.finished_processing.emit(0, 1, [])

class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Normalizacja Audio")
        self.setMinimumWidth(400)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        layout = QVBoxLayout()
        
        self.label = QLabel("Rozpoczynanie skanowania...")
        layout.addWidget(self.label)
        
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        
        self.setLayout(layout)
        
        self.worker = None

    def start_normalization(self, max_workers: int, ffmpeg_cmd: str, loudnorm_opts: str):
        if self.worker is not None and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        self.worker = Worker(max_workers, ffmpeg_cmd, loudnorm_opts)
        self.worker.progress_update.connect(self.on_progress)
        self.worker.finished_processing.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, processed, total, filename):
        if self.progress.maximum() != total:
            self.progress.setMaximum(total)

        self.progress.setValue(processed)
        self.label.setText(f"Przetwarzanie ({processed}/{total}): {filename}")

    def on_finished(self, count, errors, modified_files):
        self.close()

        # Synchronizacja zmodyfikowanych plików z Anki media DB.
        # ffmpeg zmienił zawartość plików na dysku — Anki musi zaktualizować
        # hashe w swojej bazie, inaczej przy synchronizacji z AnkiWeb pliki
        # mogą zostać nadpisane starą wersją lub oznaczone jako nieużywane.
        if modified_files:
            self._sync_media_files(modified_files)

        msg = f"Zakończono normalizację.\nPrzetworzono plików: {count}"
        if errors > 0:
            msg += f"\nBłędy: {errors} (sprawdź plik normalization.log w folderze dodatku)"

        if count == 0 and errors == 0:
            msg = "Wszystkie pliki są już znormalizowane."

        showInfo(msg, parent=mw)

    def _sync_media_files(self, filenames: list[str]):
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

    dlg = ProgressDialog(mw)
    dlg.show()
    dlg.start_normalization(max_workers=max_workers, ffmpeg_cmd=ffmpeg_cmd, loudnorm_opts=loudnorm_opts)

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
