"""Claude CLI provider — generuje przez lokalnie zainstalowanego Claude Code.

Bez klucza API: żądanie idzie przez oficjalną binarkę `claude`, zalogowaną
subskrypcją Claude (Pro/Max). Wtyczka nigdy nie dotyka tokenu — ten siedzi
w keychainie systemu, a status logowania czytamy z `claude auth status --json`,
które tokenu nie zwraca.

W odróżnieniu od Codeksa nie trzeba tu zamykać agenta w sandboksie: `--tools ""`
**usuwa wszystkie narzędzia**, więc treść pola notatki (dane niezaufane — talie
bywają pobierane z internetu) nie ma czego wywołać. To odebranie zdolności,
nie jej ograniczanie.
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import BaseProvider
from .local_cli import clean_env, find_executable

# Instalacja natywna Claude Code, gdy binarki nie ma w PATH.
LOCAL_BINARY = str(Path.home() / ".claude" / "local" / "claude")

# Domyślny system prompt. Zastępuje (nie rozszerza) prompt Claude Code, przez
# co wejście spada z ~2500 tokenów do ~280 na wywołanie — przy hurtowym
# generowaniu fiszek to różnica rzędu wielkości w zużyciu limitu planu.
DEFAULT_SYSTEM_PROMPT = (
    "Jesteś generatorem treści pól fiszek Anki. Odpowiadasz wyłącznie treścią "
    "pola — bez wstępu, komentarza, cudzysłowów i formatowania markdown."
)

# Aliasy modeli zawsze wskazują na najnowszą wersję z danej rodziny, więc się
# nie starzeją. Pełne nazwy (np. `claude-sonnet-5`) można wpisać ręcznie —
# pole modelu jest edytowalne.
MODEL_ALIASES = ["haiku", "sonnet", "opus", "fable"]

# `claude -p` bez narzędzi kończy się szybko, ale globalny request_timeout
# (domyślnie 30 s) jest liczony pod HTTP i bywa za krótki dla dłuższych pól.
MIN_TIMEOUT = 120

_RETRYABLE_MARKERS = (
    "429", "500", "502", "503", "504", "529",
    "timed out", "timeout", "connection", "overloaded", "temporarily",
)


# ----------------------------------------------------------------------
# Wykrywanie instalacji i logowania
# ----------------------------------------------------------------------

def find_binary(configured: str = "") -> Optional[str]:
    """Ścieżka do `claude`: z konfiguracji, z PATH-u, albo z instalacji natywnej."""
    return find_executable("claude", configured, (LOCAL_BINARY,))


def _clean_env() -> dict:
    """Środowisko procesu potomnego.

    Brak `ANTHROPIC_API_KEY` jest tu celowy — gwarantuje, że rozliczenie idzie
    na subskrypcję, a nie na płatne API.
    """
    return clean_env()


def login_status(binary: str = "") -> tuple[bool, str]:
    """(zalogowany subskrypcją, opis) — z `claude auth status --json`.

    Ta komenda nie zwraca tokenu, więc status da się pokazać bez zaglądania
    do poświadczeń.
    """
    resolved = find_binary(binary)
    if resolved is None:
        return False, "nie znaleziono binarki `claude`"
    try:
        proc = subprocess.run(
            [resolved, "auth", "status", "--json"],
            capture_output=True, text=True, timeout=30, env=_clean_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"nie udało się sprawdzić logowania: {e}"
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return False, "nieczytelna odpowiedź `claude auth status`"
    if not data.get("loggedIn"):
        return False, "niezalogowany — uruchom `claude auth login`"
    subscription = data.get("subscriptionType")
    email = data.get("email") or ""
    if not subscription:
        # Zalogowany przez klucz API — do tego służy dostawca `anthropic`.
        return False, f"logowanie bez subskrypcji ({data.get('authMethod')})"
    return True, f"subskrypcja {subscription}{f' — {email}' if email else ''}"


def fetch_models(binary: str = "") -> list[str]:
    """Aliasy modeli. CLI nie wystawia listy, a aliasy się nie starzeją."""
    return list(MODEL_ALIASES)


def _is_retryable(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _RETRYABLE_MARKERS)


# ----------------------------------------------------------------------
# Provider
# ----------------------------------------------------------------------

class ClaudeCLIProvider(BaseProvider):
    """Odpala `claude -p` raz na prompt i czyta pole `result` z JSON-a."""

    REQUIRES_API_KEY = False

    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None

        binary = find_binary(self.options.get("binary_path", ""))
        if binary is None:
            self.last_error = (
                "Nie znaleziono binarki `claude`. Zainstaluj Claude Code "
                "(https://claude.com/claude-code) albo podaj ścieżkę "
                "w Ustawienia → AI Generator → Dostawcy → Claude CLI."
            )
            self.logger.error(self.last_error)
            return None

        logged_in, detail = login_status(binary)
        if not logged_in:
            self.last_error = f"Claude CLI nie jest zalogowany: {detail}."
            self.logger.error(self.last_error)
            return None

        timeout = max(int(self.options.get("cli_timeout", 0) or 0),
                      self.timeout, MIN_TIMEOUT)
        for attempt in range(self.max_retries):
            text, error = self._run_once(binary, prompt, timeout)
            if text is not None:
                return text
            if attempt < self.max_retries - 1 and _is_retryable(error):
                delay = 2 ** (attempt + 1)
                self.logger.warning(
                    f"Claude CLI: {error} — ponawiam za {delay}s "
                    f"(próba {attempt + 1}/{self.max_retries})"
                )
                time.sleep(delay)
                continue
            self.last_error = f"Claude CLI: {error}"
            self.logger.error(self.last_error)
            return None
        return None

    def _build_args(self, binary: str) -> list:
        """Wiersz poleceń — parametry izolacji są tu nienegocjowalne."""
        system_prompt = (self.options.get("system_prompt") or "").strip() \
            or DEFAULT_SYSTEM_PROMPT
        args = [
            binary, "-p",
            "--tools", "",              # zero narzędzi: brak shella, plików, sieci
            "--strict-mcp-config",      # bez serwerów MCP użytkownika
            "--disable-slash-commands", # bez skilli z dysku
            "--no-session-persistence", # bez zapisu treści fiszek na dysk
            "--output-format", "json",
            "--system-prompt", system_prompt,
        ]
        if self.model:
            args += ["--model", self.model]
        return args

    def _run_once(self, binary: str, prompt: str,
                  timeout: int) -> tuple[Optional[str], str]:
        # Pusty katalog roboczy: bez niego Claude Code wciągnąłby CLAUDE.md
        # z katalogu, w którym akurat wystartowało Anki.
        with tempfile.TemporaryDirectory(prefix="anki-claude-") as workspace:
            try:
                proc = subprocess.run(
                    self._build_args(binary), input=prompt,
                    capture_output=True, text=True, timeout=timeout,
                    env=_clean_env(), cwd=workspace,
                )
            except subprocess.TimeoutExpired:
                return None, f"przekroczono limit czasu ({timeout}s)"
            except OSError as e:
                return None, f"nie udało się uruchomić procesu: {e}"

            try:
                data = json.loads(proc.stdout)
            except ValueError:
                stderr = (proc.stderr or "").strip()
                if stderr:
                    return None, stderr[-300:]
                return None, f"proces zakończył się kodem {proc.returncode}"

            if data.get("is_error"):
                return None, (data.get("result")
                              or data.get("subtype")
                              or "błąd zgłoszony przez CLI")
            text = (data.get("result") or "").strip()
            if not text:
                return None, f"pusta odpowiedź (subtype={data.get('subtype')})"
            return text, ""
