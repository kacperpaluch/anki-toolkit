import os
import shutil

AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")
LOUDNORM_OPTS = "loudnorm=I=-14:TP=-1.5:LRA=8"
MAX_WORKERS = 4


def find_ffmpeg() -> str:
    detected = shutil.which("ffmpeg")
    if detected:
        return detected
    for path in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", "/bin/ffmpeg"):
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
    return "ffmpeg"
