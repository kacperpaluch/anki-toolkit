import os
import shutil
import sys

# Funkcja pomocnicza do znalezienia ffmpeg
def find_ffmpeg():
    # 1. Sprawdź czy jest w PATH (dla pewności)
    path = shutil.which("ffmpeg")
    if path:
        return path
        
    # 2. Sprawdź typowe ścieżki na macOS/Linux
    common_paths = [
        "/opt/homebrew/bin/ffmpeg",  # macOS Apple Silicon
        "/usr/local/bin/ffmpeg",     # macOS Intel / Linux
        "/usr/bin/ffmpeg",           # Linux default
        "/bin/ffmpeg"
    ]
    
    for p in common_paths:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
            
    # 3. Jeśli nie znaleziono, zwróć po prostu "ffmpeg" i licz na cud (lub błąd w GUI)
    return "ffmpeg"

# Konfiguracja wtyczki

# Automatyczne wykrywanie ścieżki
FFMPEG_CMD = find_ffmpeg()

# Filtry (normalizacja EBU R128)
LOUDNORM_OPTS = "loudnorm=I=-14:TP=-1.5:LRA=8"

# Rozszerzenia plików do przetwarzania
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")

# Liczba wątków (None = automatycznie)
MAX_WORKERS = 4

# Auto-normalizacja (watcher na katalogu mediów)
AUTO_NORMALIZE = False
