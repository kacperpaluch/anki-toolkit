"""Codex CLI provider — generuje przez lokalnie zainstalowanego Codeksa.

Bez klucza API: żądanie idzie przez oficjalną binarkę `codex` OpenAI, która
jest już zalogowana subskrypcją ChatGPT użytkownika. Nigdy nie czytamy ani nie
kopiujemy tokenu z `auth.json` — zaglądamy tam wyłącznie po `auth_mode`, żeby
pokazać status logowania w Ustawieniach.

Każde uruchomienie jest utwardzone tak samo, jak konektor Shotlumy utwardza
swoje wywołania app-servera: sandbox read-only, brak sieci, pusty katalog
roboczy i wycięte środowisko. Treść pól notatki to dane niezaufane (talie
bywają pobierane z internetu), a Codex jest agentem z dostępem do powłoki —
nie zwykłym endpointem czatowym.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import BaseProvider

# Binarka Codeksa spoza PATH-u — ChatGPT.app wozi własną kopię.
CHATGPT_APP_BINARY = "/Applications/ChatGPT.app/Contents/Resources/codex"

# `codex exec` bez modelu trwa tyle, ile trwa rozumowanie — globalny
# request_timeout (domyślnie 30 s) jest liczony pod HTTP i bywa za krótki.
MIN_TIMEOUT = 120

# Błędy, po których warto ponowić. Reszta (zły model, brak logowania,
# wyczerpany limit) nie naprawi się przez powtórzenie.
_RETRYABLE_MARKERS = (
    "429", "500", "502", "503", "504",
    "timed out", "timeout", "connection", "temporarily",
)


# ----------------------------------------------------------------------
# Wykrywanie instalacji
# ----------------------------------------------------------------------

def find_binary(configured: str = "") -> Optional[str]:
    """Ścieżka do `codex`: z konfiguracji, z PATH-u, albo z ChatGPT.app."""
    configured = (configured or "").strip()
    if configured:
        return configured if os.access(configured, os.X_OK) else None
    found = shutil.which("codex")
    if found:
        return found
    if os.access(CHATGPT_APP_BINARY, os.X_OK):
        return CHATGPT_APP_BINARY
    return None


def codex_home(configured: str = "") -> Path:
    """Katalog CODEX_HOME.

    Musi być podany jawnie: binarka odpalona samodzielnie potrafi użyć
    prywatnego home'a, w którym nie ma logowania z aplikacji ChatGPT.
    """
    configured = (configured or "").strip()
    if configured:
        return Path(configured).expanduser()
    env = os.environ.get("CODEX_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".codex"


def login_status(home: Optional[Path] = None) -> tuple[bool, str]:
    """(zalogowany subskrypcją, opis) — czyta wyłącznie `auth_mode`."""
    auth_file = (home or codex_home()) / "auth.json"
    if not auth_file.exists():
        return False, "brak auth.json — uruchom `codex login`"
    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            mode = json.load(f).get("auth_mode")
    except (OSError, ValueError) as e:
        return False, f"nie można odczytać auth.json: {e}"
    if mode == "chatgpt":
        return True, "zalogowany kontem ChatGPT"
    if mode:
        return False, f"tryb logowania '{mode}' — wymagane `codex login` przez ChatGPT"
    return False, "auth.json bez auth_mode — uruchom `codex login`"


def _clean_env(home: Path) -> dict:
    """Minimalne środowisko dla procesu potomnego.

    Codex nie dostaje odziedziczonych zmiennych, więc pozostałe klucze API
    z tej wtyczki nie trafiają w zasięg agenta.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(Path.home())),
        "CODEX_HOME": str(home),
    }
    for passthrough in ("TMPDIR", "LANG", "LC_ALL", "USERPROFILE", "SystemRoot"):
        value = os.environ.get(passthrough)
        if value:
            env[passthrough] = value
    return env


def _is_retryable(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _RETRYABLE_MARKERS)


# ----------------------------------------------------------------------
# App-server (JSON-RPC po stdio) — lista modeli i limity planu
# ----------------------------------------------------------------------

def app_server_call(methods: list[tuple[str, dict]], binary: str = "",
                    home: Optional[Path] = None,
                    timeout: int = 25) -> dict[int, dict]:
    """Jednorazowa sesja `codex app-server --listen stdio://`.

    Zwraca {id żądania: result}. Transport stdio jest tu celowy — dziecko
    kończy się samo po zamknięciu stdin, więc nie ma osieroconych procesów.
    """
    resolved = find_binary(binary)
    if resolved is None:
        raise RuntimeError("nie znaleziono binarki `codex`")
    resolved_home = home or codex_home()

    proc = subprocess.Popen(
        [resolved, "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=_clean_env(resolved_home), text=True, bufsize=1,
    )
    results: dict[int, dict] = {}
    wanted = set(range(2, 2 + len(methods)))
    try:
        payload = [{
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "clientInfo": {"name": "anki-toolkit", "title": "Anki Toolkit",
                               "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        }]
        for i, (method, params) in enumerate(methods):
            payload.append({"jsonrpc": "2.0", "id": 2 + i,
                            "method": method, "params": params})
        proc.stdin.write("".join(json.dumps(m) + "\n" for m in payload))
        proc.stdin.flush()

        deadline = time.monotonic() + timeout
        while wanted and time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except ValueError:
                continue  # zdarzenia serwera, nie odpowiedzi
            msg_id = message.get("id")
            if msg_id in wanted and "result" in message:
                results[msg_id] = message["result"]
                wanted.discard(msg_id)
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return results


def fetch_models(binary: str = "", home: Optional[Path] = None) -> list[str]:
    """Modele dostępne dla zalogowanego konta (`model/list`)."""
    results = app_server_call([("model/list", {})], binary, home)
    data = (results.get(2) or {}).get("data") or []
    return [m["id"] for m in data
            if isinstance(m, dict) and m.get("id") and not m.get("hidden")]


def fetch_rate_limits(binary: str = "", home: Optional[Path] = None) -> dict:
    """Zużycie okien limitów planu (`account/rateLimits/read`)."""
    results = app_server_call([("account/rateLimits/read", {})], binary, home)
    return (results.get(2) or {}).get("rateLimits") or {}


# ----------------------------------------------------------------------
# Provider
# ----------------------------------------------------------------------

class CodexCLIProvider(BaseProvider):
    """Odpala `codex exec` raz na prompt i czyta ostatnią wiadomość agenta."""

    REQUIRES_API_KEY = False

    def call_api(self, prompt: str) -> Optional[str]:
        self.last_error = None

        binary = find_binary(self.options.get("binary_path", ""))
        if binary is None:
            self.last_error = (
                "Nie znaleziono binarki `codex`. Zainstaluj Codex CLI "
                "(https://developers.openai.com/codex) albo podaj ścieżkę "
                "w Ustawienia → AI Generator → Dostawcy → Codex CLI."
            )
            self.logger.error(self.last_error)
            return None

        home = codex_home(self.options.get("codex_home", ""))
        logged_in, detail = login_status(home)
        if not logged_in:
            self.last_error = f"Codex CLI nie jest zalogowany: {detail}."
            self.logger.error(self.last_error)
            return None

        timeout = max(int(self.options.get("cli_timeout", 0) or 0),
                      self.timeout, MIN_TIMEOUT)
        for attempt in range(self.max_retries):
            text, error = self._run_once(binary, home, prompt, timeout)
            if text is not None:
                return text
            if attempt < self.max_retries - 1 and _is_retryable(error):
                delay = 2 ** (attempt + 1)
                self.logger.warning(
                    f"Codex CLI: {error} — ponawiam za {delay}s "
                    f"(próba {attempt + 1}/{self.max_retries})"
                )
                time.sleep(delay)
                continue
            self.last_error = f"Codex CLI: {error}"
            self.logger.error(self.last_error)
            return None
        return None

    def _build_args(self, binary: str, workspace: str, outfile: str) -> list:
        """Wiersz poleceń — parametry utwardzenia są tu nienegocjowalne."""
        args = [
            binary, "exec",
            "--skip-git-repo-check",   # katalog roboczy nie jest repo
            "--ephemeral",             # bez zapisu sesji z treścią fiszek
            "--ignore-user-config",    # bez cudzych hooków/MCP; auth dalej z CODEX_HOME
            "--ignore-rules",          # bez plików .rules z dysku
            "--sandbox", "read-only",  # brak zapisu i brak sieci dla agenta
            "-C", workspace,           # pusty katalog, nie repozytorium użytkownika
            "-o", outfile,
        ]
        if self.model:
            args += ["-m", self.model]
        if self.reasoning_effort:
            args += ["-c", f"model_reasoning_effort={self.reasoning_effort}"]
        args.append("-")  # prompt idzie przez stdin, nie przez argv
        return args

    def _run_once(self, binary: str, home: Path, prompt: str,
                  timeout: int) -> tuple[Optional[str], str]:
        with tempfile.TemporaryDirectory(prefix="anki-codex-") as tmp:
            workspace = os.path.join(tmp, "workspace")
            outfile = os.path.join(tmp, "message.txt")
            os.mkdir(workspace, mode=0o700)
            args = self._build_args(binary, workspace, outfile)
            try:
                proc = subprocess.run(
                    args, input=prompt, capture_output=True, text=True,
                    timeout=timeout, env=_clean_env(home), cwd=workspace,
                )
            except subprocess.TimeoutExpired:
                return None, f"przekroczono limit czasu ({timeout}s)"
            except OSError as e:
                return None, f"nie udało się uruchomić procesu: {e}"

            if proc.returncode != 0:
                return None, self._describe_failure(proc)
            try:
                with open(outfile, "r", encoding="utf-8") as f:
                    text = f.read().strip()
            except OSError as e:
                return None, f"brak odpowiedzi w pliku wyjściowym: {e}"
            if not text:
                return None, self._describe_failure(proc) or "pusta odpowiedź"
            return text, ""

    @staticmethod
    def _describe_failure(proc: subprocess.CompletedProcess) -> str:
        """Wyciąga komunikat błędu — Codex loguje `ERROR: {...}` na stderr."""
        stderr = (proc.stderr or "").strip()
        for line in reversed(stderr.splitlines()):
            if line.startswith("ERROR:"):
                detail = line[len("ERROR:"):].strip()
                try:  # błędy API przychodzą jako JSON
                    parsed = json.loads(detail)
                    message = parsed.get("error", {}).get("message")
                    if message:
                        return message
                except ValueError:
                    pass
                return detail
        if stderr:
            return stderr[-300:]
        return f"proces zakończył się kodem {proc.returncode}"
