"""Local dashboard with run history and an explicit controller trigger."""
import json
import fcntl
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer


def render(history, token="", running=False, settings=None, connection=None, mail=None, intervention=None):
    parts = ['''<!doctype html><html lang="pl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Workload — historia</title>
<style>body{font:16px system-ui;margin:40px auto;padding:0 20px;max-width:1000px;
background:#f5f7fa;color:#172533}article{background:white;padding:20px;margin:16px 0;
border-radius:12px}table{width:100%;text-align:left;border-collapse:collapse}
td,th{padding:8px;border-bottom:1px solid #ddd}code{overflow-wrap:anywhere}
.error{color:#b42318}.success{color:#157347}</style>
<h1>Workload</h1><p><a href="/">Odśwież historię</a></p><p>Historia automatu • ostatnie 200 przebiegów • odświeżanie ręczne</p>
<p>To synchronizacje usługi, nie potwierdzenia synchronizacji telefonu.
Historia pojawia się po zakończeniu przebiegu.</p>''']
    parts.append(f'<form method="post" action="/run"><input type="hidden" name="token" value="{escape(token)}">'
                 f'<button {"disabled" if running else ""}>Uruchom teraz</button></form>'
                 + ('<p>Przebieg trwa…</p>' if running else '<p>Pełny przebieg zgodny z apply: symulacja lub zapis limitów.</p>'))
    if intervention:
        parts.append('<article><h2>Wymagana interwencja</h2><p>Harmonogram wstrzymany: '
                     + escape(intervention.get("error", "")) + '</p></article>')
    parts.append(f'<details><summary>Napraw synchronizację</summary><form method="post" action="/download">'
                 f'<input type="hidden" name="token" value="{escape(token)}">'
                 '<p>Pobranie zastąpi kopię Workload na RPi. Powstanie kopia bezpieczeństwa. '
                 'Stan limitów zostanie zachowany i sprawdzony przed wznowieniem harmonogramu.</p>'
                 '<p><label><input type="checkbox" name="confirm" value="yes" required>'
                 'Potwierdzam, że serwer ma aktualną kolekcję po synchronizacji moich urządzeń.</label></p>'
                 f'<button {"disabled" if running else ""}>Pobierz kolekcję z serwera</button></form></details>')
    settings = settings or {}
    connection = connection or {}
    parts.append(f'<details><summary>Ustawienia i konto Anki</summary><form method="post" action="/settings">'
                 f'<input type="hidden" name="token" value="{escape(token)}">')
    fields = [("url", "Serwer (ankiweb lub URL)", connection.get("url", "ankiweb"), "text"),
              ("username", "Login Anki", connection.get("username", ""), "text"),
              ("password", "Hasło Anki (tylko przy pierwszym logowaniu / odnowieniu tokenu)", "", "password"),
              ("run_at", "Godzina (strefa TZ z Compose)", settings.get("run_at", "05:00"), "time"),
              ("minutes_per_day", "Cel minut", settings.get("minutes_per_day", 15), "number"),
              ("max_minutes_per_day", "Maksymalnie minut", settings.get("max_minutes_per_day", 30), "number"),
              ("new_cards_per_day", "Nowych kart dziennie łącznie", settings.get("new_cards_per_day", 3), "number")]
    for name, label, value, kind in fields:
        parts.append(f'<p><label>{label}<br><input name="{name}" type="{kind}" '
                     f'value="{escape(str(value), quote=True)}"></label></p>')
    decks = "\n".join(settings.get("decks", []))
    parts.append(f'<p><label>Talie (jedna pełna nazwa na linię)<br><textarea name="decks" rows="4">{escape(decks)}</textarea></label></p>'
                 f'<p><label><input type="checkbox" name="apply" {"checked" if settings.get("apply") else ""}>Zapisuj limity (odznaczone = symulacja)</label></p>'
                 '<button>Zapisz ustawienia / zaloguj</button></form>'
                 '<p>Przed pierwszą inicjalizacją wyślij kolekcję z aplikacji Anki na serwer. '
                 'Zmiana konta wymaga osobnego wolumenu. Zmiana zakresu zarządzanych talii wymaga restore. '
                 'Hasło nie jest zapisywane w ustawieniach.</p></details>')
    mail = mail or {}
    parts.append(f'<details><summary>Powiadomienia e-mail</summary><form method="post" action="/mail">'
                 f'<input type="hidden" name="token" value="{escape(token)}">'
                 f'<p><label><input type="checkbox" name="enabled" {"checked" if mail.get("enabled") else ""}>Wysyłaj raporty i powiadomienia o błędach</label></p>')
    for name, label, kind, default in [('host', 'Host SMTP', 'text', ''), ('port', 'Port SMTP', 'number', 587),
                                     ('username', 'Login SMTP (pusty = bez logowania)', 'text', ''),
                                     ('sender', 'Nadawca', 'email', ''), ('recipient', 'Odbiorca', 'email', '')]:
        parts.append(f'<p><label>{label}<br><input name="{name}" type="{kind}" value="{escape(str(mail.get(name, default)), quote=True)}"></label></p>')
    parts.append('<p><label>Szyfrowanie <select name="security">')
    for value, label in [('starttls', 'STARTTLS (zwykle 587)'), ('ssl', 'TLS (zwykle 465)'), ('none', 'Brak (lokalny relay)')]:
        parts.append(f'<option value="{value}" {"selected" if mail.get("security", "starttls") == value else ""}>{label}</option>')
    parts.append('</select></label></p><p><label>Hasło SMTP (puste = zachowaj zapisane)<br>'
                 '<input type="password" name="password" autocomplete="new-password"></label></p>'
                 '<p><label><input type="checkbox" name="clear_password">Usuń zapisane hasło SMTP</label></p>'
                 '<button>Zapisz powiadomienia</button></form>'
                 '<p>Raport po udanym run i restore, również w symulacji. Jeden alert dla powtarzającego się błędu do sukcesu lub zmiany błędu. '
                 'Wynik wysyłki pojawi się w historii.</p></details>')
    if not history:
        parts.append('<article>Brak historii. Uruchom init, a następnie run.</article>')
    for event in reversed(history):
        ok = event.get('status') == 'success'
        mode = ('Zastosowano' if event.get('apply') else 'Symulacja — bez zapisu limitów')
        if event.get("command") == "download":
            mode = "Pobranie kolekcji z serwera"
        if event.get('command') in ('init', 'login'):
            mode = 'Inicjalizacja' if event['command'] == 'init' else 'Odświeżenie logowania'
        status = 'Sukces' if ok else 'Błąd — zmiany mogły zostać częściowo wysłane'
        parts.append(f'<article><h2 class="{"success" if ok else "error"}">{status}</h2>'
                     f'<p>{escape(mode)} · {escape(event.get("command", ""))}</p>'
                     f'<p>Start: {escape(event.get("started", ""))}<br>'
                     f'Koniec: {escape(event.get("finished", ""))}</p>')
        for key in ('reason', 'error'):
            if event.get(key):
                parts.append(f'<p>{escape(event[key])}</p>')
        if event.get('email') and event['email'] != 'not_needed':
            parts.append('<p>E-mail: ' + escape('wysłano' if event['email'] == 'sent' else event['email']) + '</p>')
        changes = event.get('changes', [])
        if changes:
            parts.append('<p>Zmiany limitów' + (' potwierdzone synchronizacją' if ok and event.get('apply') else ' planowane') +
                         ':</p><table><tr><th>Talia</th><th>Przed</th><th>Po</th></tr>')
            for change in changes:
                values = [change['deck']]
                for key in ('before', 'after'):
                    limit = change[key]
                    base = limit.get('newLimit')
                    today = limit.get('newLimitToday')
                    values.append(f"Bazowy: {base if base is not None else 'z presetu'}; "
                                  f"limit dzienny: {today['limit'] if today else 'brak nadpisania'}")
                parts.append('<tr>' + ''.join(f'<td>{escape(str(value))}</td>' for value in values) + '</tr>')
            parts.append('</table>')
        else:
            parts.append('<p>Brak zaplanowanych zmian limitów.</p>')
        cost = event.get('card_costs', {})
        if cost.get('total_seconds', 0) > 0:
            parts.append(f'<p>Ostatnie 7 zakończonych dni: {cost["total_seconds"] / 60:.1f} min; '
                         f'niedawno wprowadzone karty: {cost["cohort_seconds"] / 60:.1f} min.</p>')
        parts.append('</article>')
    return ''.join(parts) + '</html>'


def serve(data_dir):
    try:
        from . import worker, notifications
    except ImportError:
        import worker
        import notifications
    import os
    token = secrets.token_urlsafe(32)
    process = None

    def busy():
        path = data_dir / "worker.lock"
        if not path.exists():
            return False
        with path.open("r") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal process
            if self.path not in ("/run", "/settings", "/mail", "/download"):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                self.send_error(400)
                return
            form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            value = form.get("token", [""])[0]
            if not secrets.compare_digest(value, token):
                self.send_error(403)
                return
            if busy() or (process is not None and process.poll() is None):
                self.send_error(409, "Przebieg trwa; poczekaj na wynik")
                return
            command, env = "run", os.environ.copy()
            if self.path == "/download":
                if form.get("confirm") != ["yes"]:
                    self.send_error(400, "Potwierdz aktualnosc kolekcji na serwerze")
                    return
                command = "download"
            if self.path == "/mail":
                try:
                    config = notifications.settings_from(form, worker.read_json(data_dir / "mail.json", {}))
                    data_dir.mkdir(parents=True, exist_ok=True)
                    worker.write_json(data_dir / "mail.json", config)
                    (data_dir / "mail.json").chmod(0o600)
                    command = None
                except ValueError as error:
                    self.send_error(400, str(error))
                    return
            if self.path == "/settings":
                data_dir.mkdir(parents=True, exist_ok=True)
                with (data_dir / "worker.lock").open("a") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        get = lambda name: form.get(name, [""])[0]
                        config = {}
                        config.update({name: int(get(name)) for name in
                                       ("minutes_per_day", "max_minutes_per_day", "new_cards_per_day")})
                        config.update(run_at=get("run_at"), apply="apply" in form,
                                      decks=[name.strip() for name in get("decks").splitlines() if name.strip()])
                        config = worker.settings_from(Path("/config/workload.json"), data_dir, config)
                        endpoint, username = worker.credentials(get("url"), get("username"))
                        identity = worker.read_json(data_dir / "identity.json")
                        if identity and identity != {"endpoint": endpoint, "username": username}:
                            raise worker.WorkloadError("Zmiana konta/serwera wymaga nowego wolumenu")
                        previous = worker.read_json(data_dir / "settings.json", json.loads(os.environ.get("WORKLOAD_CONFIG", "{}")))
                        if worker.read_json(data_dir / "state.json", {}).get("managed") and config["decks"] != previous.get("decks"):
                            raise worker.WorkloadError("Przed zmiana zakresu talii wykonaj restore")
                        worker.write_json(data_dir / "settings.json", config)
                        worker.write_json(data_dir / "connection.json", {"url": get("url"), "username": username})
                        password = get("password")
                        if password:
                            env["ANKI_SYNC_PASSWORD"] = password
                            env.pop("ANKI_SYNC_PASSWORD_FILE", None)
                            command = "login" if identity else "init"
                        else:
                            command = None
                    except (ValueError, worker.WorkloadError, BlockingIOError) as error:
                        self.send_error(400, str(error))
                        return
            if command:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("worker.py")),
                                            command, "--data", str(data_dir)], env=env)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def do_GET(self):
            if self.path not in ('/', '/history.json'):
                self.send_error(404)
                return
            path = data_dir / 'history.json'
            history = json.loads(path.read_text()) if path.exists() else []
            body = (json.dumps(history, ensure_ascii=False) if self.path == '/history.json'
                    else render(history, token, busy() or (process is not None and process.poll() is None),
                                worker.settings_from(Path("/config/workload.json"), data_dir) if (data_dir / "settings.json").exists() else json.loads(os.environ.get("WORKLOAD_CONFIG", "{}")),
                                worker.read_json(data_dir / "connection.json", {"url": os.environ.get("ANKI_SYNC_URL", "ankiweb"), "username": os.environ.get("ANKI_SYNC_USERNAME", "")}),
                                worker.read_json(data_dir / "mail.json", {}),
                                worker.read_json(data_dir / "intervention.json"))).encode()
            self.send_response(200)
            self.send_header('Content-Type', ('application/json' if self.path == '/history.json' else 'text/html') + '; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
