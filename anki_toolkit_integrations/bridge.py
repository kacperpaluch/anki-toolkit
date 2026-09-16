"""web_bridge — mostek HTTP: strona WWW → otwarte okno „Dodaj" w Anki.

Wystawia jeden endpoint POST na 127.0.0.1 (port z `web_bridge.port`), który wpisuje przysłane pola
do JUŻ OTWARTEGO okna „Dodaj". Nie tworzy notatek, nie zapisuje — tylko
wypełnia pola edytora; zapis zatwierdzasz w Anki ręcznie (Enter).

Które pole dostaje jaką wartość decyduje strona wysyłająca (body: {"fields": {...}}),
więc moduł jest uniwersalny. Dołączony userscript `dictionaries-to-anki.user.js`
obsługuje diki.pl, Oxford Learner's i Longman (LDOCE). Okno „Dodaj" musi być
otwarte, inaczej endpoint zwraca błąd.
"""

import json
import logging
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import aqt
    from aqt import mw
    from aqt.qt import sip
    from aqt.utils import showWarning
except ImportError:  # pozwala odpalić self-check (__main__) bez Anki
    aqt = mw = None

logger = logging.getLogger(__name__)

HOST, DEFAULT_PORT = "127.0.0.1", 8767  # 8765/8766 to AnkiConnect i jego forki
MAX_BODY = 1_000_000  # 1 MB — pola słownikowe to kilobajty

# Strony z userscripta. GM_xmlhttpRequest nie wysyła nagłówka Origin (brak → OK);
# przeglądarka przy cross-origin POST wysyła go ZAWSZE, więc żądania fetch()
# z innych witryn są odrzucane — obca strona nie wstrzyknie pól do okna „Dodaj".
ALLOWED_ORIGIN_HOSTS = {
    "www.diki.pl",
    "www.oxfordlearnersdictionaries.com",
    "www.ldoceonline.com",
    "dictionary.cambridge.org",
}

_server = None  # trzyma referencję, żeby przetrwał między przełączeniami profilu
_bound_port = None  # port, na którym faktycznie stoimy — tylko ten origin wpuszczamy
_target = None  # immutable snapshot published by the main thread


def track_editor(editor):
    global _target
    if editor.addMode:
        _target = (editor, editor.note, mw.col)


def forget_editor(*_args):
    global _target
    _target = None


def _target_alive(target):
    if target is None or target is not _target:
        return False
    editor, note, col = target
    return (col is not None and mw.col is col and editor.note is note
            and note is not None and editor.web is not None
            and not sip.isdeleted(editor.web))


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True  # GM_xmlhttpRequest / curl / lokalne skrypty
    parsed = urllib.parse.urlparse(origin)
    # Czytnik słownika serwujemy sami — wpuszczamy DOKŁADNIE nasz port, nie cały
    # localhost. Inny lokalny serwer (dev, druga wtyczka) to obcy origin.
    if _bound_port is not None and (parsed.hostname, parsed.port) == (HOST, _bound_port):
        return True
    return parsed.hostname in ALLOWED_ORIGIN_HOSTS


def _join(existing: str, value: str, separator: str) -> str:
    """Doklej `value` do `existing` przez `separator`; puste `existing` → sama `value`."""
    base = existing.strip()
    return (base + separator + value) if base else value


def _apply_fields(fields: dict, target, append: bool = False, separator: str = "<br><br>") -> str | None:
    """Na WĄTKU GŁÓWNYM: wpisz pola do otwartego okna „Dodaj". Zwraca błąd lub None.

    append=True → dokleja do istniejącej treści pola przez `separator` (puste pole
    dostaje samą wartość). Inaczej nadpisuje.
    """
    if not _target_alive(target):
        return "Okno „Dodaj” lub notatka zmieniły się — wyślij dane ponownie."
    editor, note, _col = target

    written = [name for name in fields if name in note]
    if not written:
        return "Żadne z podanych pól nie istnieje w tym typie notatki: " + ", ".join(fields)

    for name in written:
        if append:
            note[name] = _join(note[name], fields[name], separator)
        else:
            note[name] = fields[name]
    editor.loadNote()
    editor.parentWindow.activateWindow()
    return None


def _run_on_main_sync(fields, append=False, separator="<br><br>", timeout=5):
    """Save the captured editor before applying; timeout cancels pending callbacks."""
    box = {}
    done = threading.Event()
    lock = threading.Lock()
    target = _target

    def apply():
        with lock:
            if done.is_set():
                return
            try:
                box["error"] = _apply_fields(fields, target, append, separator)
            except Exception as error:
                box["error"] = str(error)
                logger.exception("web_bridge: apply failed")
            done.set()

    def start():
        with lock:
            if done.is_set():
                return
            if not _target_alive(target):
                box["error"] = "Otwórz okno „Dodaj” i wyślij dane ponownie."
                done.set()
                return
        try:
            target[0].saveNow(apply)
        except Exception as error:
            with lock:
                if not done.is_set():
                    box["error"] = str(error)
                    done.set()

    mw.taskman.run_on_main(start)
    done.wait(timeout)
    with lock:
        if not done.is_set():
            box["error"] = "Anki nie odpowiedziało w czasie — operacja anulowana."
            done.set()
        return box.get("error")


class _Handler(BaseHTTPRequestHandler):
    def _cors(self):
        # Nagłówki CORS tylko dla dozwolonych originów — ale to walidacja
        # w do_POST faktycznie blokuje (simple request text/plain omija preflight).
        origin = self.headers.get("Origin")
        if origin and _origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):  # preflight
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        """Mostek przyjmuje wyłącznie POST-y z polami notatki."""
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not _origin_allowed(self.headers.get("Origin")):
            self.send_response(403)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY:
                raise ValueError("Niepoprawny rozmiar żądania (limit 1 MB).")
            body = json.loads(self.rfile.read(length) or b"{}")
            fields = body.get("fields")
            if not isinstance(fields, dict) or not fields:
                error = 'Body musi mieć {"fields": {"Nazwa pola": "wartość"}}'
            else:
                append = bool(body.get("append"))
                separator = body.get("separator") or "<br><br>"
                if not all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items()) or not isinstance(separator, str):
                    raise ValueError("Nazwy pól, wartości i separator muszą być tekstem.")
                error = _run_on_main_sync(fields, append, separator)
        except Exception as e:  # noqa: BLE001
            error = str(e)
            logger.exception("web_bridge: bad request")

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": not error, "error": error}).encode())

    def log_message(self, *_):  # cisza w konsoli Anki
        pass


def _port() -> int:
    config = (mw.addonManager.getConfig(__package__) or {}).get("web_bridge") or {}
    try:
        return int(config.get("port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def start_server(*_args, **_kwargs):
    """Idempotentne — profile_did_open odpala się przy każdym przełączeniu profilu."""
    global _server
    if _server is not None:
        return
    port = _port()
    try:
        _server = ThreadingHTTPServer((HOST, port), _Handler)
    except OSError as e:  # zajęty port to cicha śmierć mostka — powiedz to głośno
        logger.warning("web_bridge: nie mogę zająć %s:%s (%s)", HOST, port, e)
        showWarning(
            f"Anki Toolkit: mostek słownikowy nie wystartował — port {port} jest zajęty "
            f"przez inny dodatek ({e}).\n\nZmień „web_bridge.port” w konfiguracji "
            "Integrations i ten sam port w userscripcie.")
        return
    global _bound_port
    _bound_port = port
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    logger.info("web_bridge: nasłuchuje na http://%s:%s", HOST, port)


if __name__ == "__main__":  # self-check logiki doklejania (bez Anki)
    SEP = "<br><br>"
    assert _join("", "ex1", SEP) == "ex1"                       # puste → sama wartość
    assert _join("ex1", "ex2", SEP) == "ex1<br><br>ex2"         # doklejenie
    assert _join("ex1<br><br>ex2", "ex3", SEP) == "ex1<br><br>ex2<br><br>ex3"
    assert _join("  ex1  ", "ex2", SEP) == "ex1<br><br>ex2"     # trim istniejącego
    print("web_bridge self-check OK")
