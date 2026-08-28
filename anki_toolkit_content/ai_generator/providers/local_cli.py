"""Wspólna obsługa dostawców uruchamiających lokalne CLI (Codex, Claude).

Dwie rzeczy, które muszą być zrobione tak samo dla każdego takiego dostawcy:
znalezienie binarki i zbudowanie środowiska procesu potomnego. Jedno i drugie
ma na macOS pułapkę, przez którą „u mnie działa" z terminala nie znaczy nic.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Sequence

# Aplikacja GUI na macOS nie dziedziczy PATH-u z powłoki: Anki uruchomione
# z Findera dostaje z launchd tylko /usr/bin:/bin:/usr/sbin:/sbin, więc
# `shutil.which()` nie znajdzie niczego z Homebrew, npm, bun ani MacPorts.
# Te katalogi dokładamy zarówno przy szukaniu binarki, jak i do PATH-u
# procesu potomnego — samo CLI też potrzebuje tam zajrzeć (node, ffmpeg).
EXTRA_BIN_DIRS = (
    "/opt/homebrew/bin",      # Homebrew (Apple Silicon)
    "/usr/local/bin",         # Homebrew (Intel), instalatory
    "/opt/local/bin",         # MacPorts
    "~/.local/bin",
    "~/.bun/bin",
    "~/.npm-global/bin",
    "~/bin",
)


def search_path() -> str:
    """PATH procesu wzbogacony o typowe katalogi instalacji."""
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    for extra in EXTRA_BIN_DIRS:
        resolved = os.path.expanduser(extra)
        if resolved not in parts:
            parts.append(resolved)
    return os.pathsep.join(parts)


def find_executable(name: str, configured: str = "",
                    extra_candidates: Sequence[str] = ()) -> Optional[str]:
    """Ścieżka do binarki: z konfiguracji, z rozszerzonego PATH-u, z kandydatów.

    `configured` jest wiążące — jeśli użytkownik podał ścieżkę, a jej tam nie
    ma, zwracamy None zamiast po cichu użyć innej instalacji.
    """
    configured = (configured or "").strip()
    if configured:
        resolved = os.path.expanduser(configured)
        return resolved if os.access(resolved, os.X_OK) else None
    found = shutil.which(name, path=search_path())
    if found:
        return found
    for candidate in extra_candidates:
        resolved = os.path.expanduser(candidate)
        if os.access(resolved, os.X_OK):
            return resolved
    return None


def clean_env(extra: Optional[dict] = None) -> dict:
    """Minimalne środowisko dla procesu potomnego.

    Bez odziedziczonych zmiennych: pozostałe klucze API z tej wtyczki nie
    trafiają w zasięg uruchamianego CLI. `USER`/`LOGNAME` muszą jednak zostać —
    bez nich odczyt keychaina na macOS zawodzi i zalogowane CLI raportuje brak
    logowania.
    """
    env = {
        "PATH": search_path(),
        "HOME": os.environ.get("HOME", str(Path.home())),
    }
    for passthrough in ("USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL",
                        "USERPROFILE", "SystemRoot", "APPDATA"):
        value = os.environ.get(passthrough)
        if value:
            env[passthrough] = value
    if extra:
        env.update(extra)
    return env
