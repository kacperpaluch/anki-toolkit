"""web_bridge — mostek HTTP: strona WWW → otwarte okno „Dodaj" w Anki.

Wystawia jeden endpoint POST na 127.0.0.1:8766, który wpisuje przysłane pola
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
except ImportError:  # pozwala odpalić self-check (__main__) bez Anki
    aqt = mw = None

logger = logging.getLogger(__name__)

HOST, PORT = "127.0.0.1", 8766
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


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True  # GM_xmlhttpRequest / curl / lokalne skrypty
    host = urllib.parse.urlparse(origin).hostname
    return host in ALLOWED_ORIGIN_HOSTS


def _join(existing: str, value: str, separator: str) -> str:
    """Doklej `value` do `existing` przez `separator`; puste `existing` → sama `value`."""
    base = existing.strip()
    return (base + separator + value) if base else value


def _apply_fields(fields: dict, append: bool = False, separator: str = "<br><br>") -> str | None:
    """Na WĄTKU GŁÓWNYM: wpisz pola do otwartego okna „Dodaj". Zwraca błąd lub None.

    append=True → dokleja do istniejącej treści pola przez `separator` (puste pole
    dostaje samą wartość). Inaczej nadpisuje.
    """
    entry = aqt.dialogs._dialogs.get("AddCards")
    addcards = entry[1] if entry else None
    if addcards is None:
        return 'Okno „Dodaj" nie jest otwarte'

    editor = addcards.editor
    note = editor.note
    if note is None:
        return "Edytor nie ma notatki"

    written = [name for name in fields if name in note]
    if not written:
        return "Żadne z podanych pól nie istnieje w tym typie notatki: " + ", ".join(fields)

    for name in written:
        if append:
            note[name] = _join(note[name], fields[name], separator)
        else:
            note[name] = fields[name]
    editor.loadNote()
    addcards.activateWindow()
    return None


def _run_on_main_sync(fn, timeout=5):
    """Odpal fn() na wątku głównym i zaczekaj na wynik (handler HTTP jest na wątku roboczym)."""
    box = {}
    done = threading.Event()

    def wrapper():
        try:
            box["value"] = fn()
        except Exception as e:  # noqa: BLE001 — złap wszystko, oddaj jako błąd HTTP
            box["error"] = str(e)
            logger.exception("web_bridge: apply failed")
        finally:
            done.set()

    mw.taskman.run_on_main(wrapper)
    if not done.wait(timeout):
        return "Anki nie odpowiedziało w czasie (zajęte?)"
    return box.get("error") or box.get("value")


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

    def do_POST(self):
        if not _origin_allowed(self.headers.get("Origin")):
            self.send_response(403)
            self.end_headers()
            return
        try:
            length = min(int(self.headers.get("Content-Length", 0)), MAX_BODY)
            body = json.loads(self.rfile.read(length) or b"{}")
            fields = body.get("fields")
            if not isinstance(fields, dict) or not fields:
                error = 'Body musi mieć {"fields": {"Nazwa pola": "wartość"}}'
            else:
                append = bool(body.get("append"))
                separator = body.get("separator") or "<br><br>"
                error = _run_on_main_sync(lambda: _apply_fields(fields, append, separator))
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


def start_server(*_args, **_kwargs):
    """Idempotentne — profile_did_open odpala się przy każdym przełączeniu profilu."""
    global _server
    if _server is not None:
        return
    try:
        _server = ThreadingHTTPServer((HOST, PORT), _Handler)
    except OSError as e:  # port zajęty — nie wysadzaj addonu
        logger.warning("web_bridge: nie mogę zająć %s:%s (%s)", HOST, PORT, e)
        return
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    logger.info("web_bridge: nasłuchuje na http://%s:%s", HOST, PORT)


if __name__ == "__main__":  # self-check logiki doklejania (bez Anki)
    SEP = "<br><br>"
    assert _join("", "ex1", SEP) == "ex1"                       # puste → sama wartość
    assert _join("ex1", "ex2", SEP) == "ex1<br><br>ex2"         # doklejenie
    assert _join("ex1<br><br>ex2", "ex3", SEP) == "ex1<br><br>ex2<br><br>ex3"
    assert _join("  ex1  ", "ex2", SEP) == "ex1<br><br>ex2"     # trim istniejącego
    print("web_bridge self-check OK")
