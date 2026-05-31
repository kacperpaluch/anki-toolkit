"""Audio Normalizer tab — ffmpeg path, loudnorm opts, workers."""

from shutil import which
import subprocess

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QSpinBox, QPushButton,
)
from aqt.utils import tooltip

from ..common.ui import _expanding_line_edit


class AudioNormalizerTab(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        a = cfg.get("audio_normalizer", {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        ffmpeg_row = QWidget()
        ffmpeg_row_layout = QHBoxLayout(ffmpeg_row)
        ffmpeg_row_layout.setContentsMargins(0, 0, 0, 0)
        ffmpeg_row_layout.setSpacing(4)
        self._ffmpeg_path = _expanding_line_edit(a.get("ffmpeg_path", ""))
        self._ffmpeg_path.setPlaceholderText("Puste = wykryj automatycznie")
        test_btn = QPushButton("Sprawdź")
        test_btn.setFixedWidth(75)
        test_btn.clicked.connect(self._test_ffmpeg)
        ffmpeg_row_layout.addWidget(self._ffmpeg_path)
        ffmpeg_row_layout.addWidget(test_btn)

        self._loudnorm_opts = _expanding_line_edit(
            a.get("loudnorm_opts", "loudnorm=I=-14:TP=-1.5:LRA=8")
        )
        self._max_workers = QSpinBox()
        self._max_workers.setRange(1, 32)
        self._max_workers.setValue(a.get("max_workers", 4))
        self._max_workers.setToolTip("Liczba równoległych wątków ffmpeg")

        form.addRow("Ścieżka do ffmpeg:", ffmpeg_row)
        form.addRow("Opcje loudnorm:", self._loudnorm_opts)
        form.addRow("Maks. wątków:", self._max_workers)
        layout.addLayout(form)
        layout.addSpacing(8)

        hint = QLabel(
            "Domyślne opcje loudnorm: loudnorm=I=-14:TP=-1.5:LRA=8  (standard EBU R128)\n"
            "Zmień I= (głośność docelowa LUFS), TP= (true peak dB), LRA= (rozpiętość dynamiczna LU)."
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    def _test_ffmpeg(self) -> None:
        from ..audio_normalizer import config as _defaults

        path = self._ffmpeg_path.text().strip()
        cmd = path if path else _defaults.FFMPEG_CMD
        found = which(cmd)
        if not found:
            tooltip(f"Nie znaleziono '{cmd}' w systemie.")
            return
        try:
            result = subprocess.run(
                [found, "-version"], capture_output=True, text=True, timeout=5
            )
            first_line = (result.stdout or result.stderr or "").split("\n")[0]
            tooltip(f"OK: {found}<br>{first_line}", period=5000)
        except Exception as e:
            tooltip(f"Błąd testu ffmpeg: {e}")

    def apply(self, cfg: dict) -> None:
        cfg.setdefault("audio_normalizer", {})
        a = cfg["audio_normalizer"]
        a["ffmpeg_path"] = self._ffmpeg_path.text().strip()
        a["loudnorm_opts"] = self._loudnorm_opts.text().strip()
        a["max_workers"] = self._max_workers.value()
