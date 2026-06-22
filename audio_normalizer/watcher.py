"""Auto-normalization — watches the media dir and normalizes new audio files.

Trigger: any file change in mw.col.media.dir() (TTS generation, dictionary
fetch, AI workflow, manual add, AnkiWeb sync).
Debounce: 3s from the last event — batches bursts of writes (e.g. TTS
generates dozens of files in a few seconds).
Feedback-loop guard: while normalizing, directoryChanged is ignored so the
ffmpeg temp-write + os.replace + media.write_data sync don't re-trigger.
"""

import logging
import os
from shutil import which

from aqt import mw
from aqt.qt import QFileSystemWatcher, QTimer
from aqt.utils import tooltip

from . import config as _defaults
from . import logic

logger = logging.getLogger(__name__)

_watcher: QFileSystemWatcher | None = None
_debounce: QTimer | None = None
_normalizing = False  # ponytail: single global lock; per-file locks if throughput matters

_DEBOUNCE_MS = 3000


def start_watcher() -> None:
    global _watcher, _debounce
    if _watcher is not None:
        return
    media_dir = mw.col.media.dir()
    _watcher = QFileSystemWatcher()
    _watcher.addPath(media_dir)
    _watcher.directoryChanged.connect(_on_media_changed)
    _debounce = QTimer()
    _debounce.setSingleShot(True)
    _debounce.setInterval(_DEBOUNCE_MS)
    _debounce.timeout.connect(_run_auto_normalize)
    logger.info(f"Audio normalizer watcher started on {media_dir}")


def stop_watcher() -> None:
    global _watcher, _debounce
    if _watcher is not None:
        _watcher.deleteLater()
        _watcher = None
    if _debounce is not None:
        _debounce.stop()
        _debounce.deleteLater()
        _debounce = None


def _on_media_changed(_path: str) -> None:
    if _normalizing:
        return  # own ffmpeg/sync writes — ignore
    if _debounce is not None:
        _debounce.start()  # (re)start debounce window


def _run_auto_normalize() -> None:
    global _normalizing
    if _normalizing:
        return
    _normalizing = True
    try:
        from ..common import ADDON_NAME
        full = mw.addonManager.getConfig(ADDON_NAME) or {}
        cfg = full.get("audio_normalizer", {})
        ffmpeg_path = cfg.get("ffmpeg_path", "").strip()
        ffmpeg_cmd = ffmpeg_path if ffmpeg_path else _defaults.FFMPEG_CMD
        loudnorm_opts = cfg.get("loudnorm_opts", _defaults.LOUDNORM_OPTS) or _defaults.LOUDNORM_OPTS
        max_workers = int(cfg.get("max_workers", _defaults.MAX_WORKERS))
        if which(ffmpeg_cmd) is None:
            logger.warning(f"Auto-normalize: ffmpeg '{ffmpeg_cmd}' not found — skipping")
            return
        count, errors, modified_files = logic.process_collection(
            max_workers=max_workers,
            ffmpeg_cmd=ffmpeg_cmd,
            loudnorm_opts=loudnorm_opts,
        )
        # Sync media DB (same as gui.ProgressDialog._sync_media_files) so Anki
        # updates hashes and AnkiWeb sync doesn't overwrite with old versions.
        if modified_files:
            media = mw.col.media
            media_dir = media.dir()
            for fname in modified_files:
                fpath = os.path.join(media_dir, fname)
                if os.path.exists(fpath):
                    try:
                        with open(fpath, "rb") as f:
                            media.write_data(fname, f.read())
                    except Exception as e:
                        logger.error(f"Media sync failed for '{fname}': {e}")
        # Tooltip — gated by show_tooltip so users who find it noisy can disable.
        if cfg.get("show_tooltip", True) and count > 0:
            msg = f"Znormalizowano {count} plik(ów) audio."
            if errors:
                msg += f" Błędy: {errors} (szczegóły w logach)."
            tooltip(msg, parent=mw, period=4000)
    except Exception as e:
        logger.error(f"Auto-normalize failed: {e}")
    finally:
        _normalizing = False


def init_auto_normalize() -> None:
    """Register profile_did_open hook to start the watcher if enabled."""
    from aqt import gui_hooks

    def _on_profile_open():
        from ..common import ADDON_NAME
        full = mw.addonManager.getConfig(ADDON_NAME) or {}
        cfg = full.get("audio_normalizer", {})
        if cfg.get("auto_normalize", False):
            start_watcher()

    # If the profile is already open (e.g. addon reload), start now; otherwise
    # wait for the hook. Same pattern as nbsp_remover.
    if mw.col is not None:
        _on_profile_open()
    else:
        gui_hooks.profile_did_open.append(_on_profile_open)
