"""Local dashboard with run history and an explicit controller trigger."""
import json
import fcntl
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs
from html import escape
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer


def display_time(value):
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y · %H:%M:%S")
    except ValueError:
        return value


def render(history, token="", running=False, settings=None, connection=None, mail=None, intervention=None):
    settings = settings or {}
    latest = history[-1] if history else {}
    status = ("Wymagana interwencja" if intervention else "Przebieg trwa…" if running
              else "Ostatnia operacja udana" if latest.get("status") == "success"
              else "Ostatnia operacja nieudana" if latest else "Gotowy do konfiguracji")
    tone = "error" if intervention or (not running and latest.get("status") == "error") else "success" if latest.get("status") == "success" and not running else "neutral"
    parts = ['''<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Workload — panel</title>
<style>
:root{color-scheme:light;--ink:#22352e;--muted:#65756d;--line:#dfe6df;--green:#25634b;--paper:#fff;--bg:#f5f6f2}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--green);text-underline-offset:4px}button,input,select,textarea{font:inherit}button,.button{min-height:44px;border:1px solid var(--green);border-radius:9px;padding:10px 17px;background:var(--green);color:white;font-weight:600;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
button:hover,.button:hover{background:#194d39}button:disabled{opacity:.5;cursor:wait}.secondary{background:white;color:var(--ink);border-color:var(--line)}.secondary:hover{background:#edf1eb}
:focus-visible{outline:3px solid #77a991;outline-offset:3px}h1,h2,p{margin:0}h1{font-size:34px;line-height:1.2;letter-spacing:-1.3px}h2{font-size:19px;letter-spacing:-.4px}p+p{margin-top:12px}.muted,small{color:var(--muted)}.eyebrow{font-size:11px;letter-spacing:1.8px;font-weight:700;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.shell{max-width:1180px;margin:auto;padding:0 32px}.topbar{border-bottom:1px solid var(--line);background:#fff}.topbar .shell{height:76px;display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{display:flex;align-items:center;gap:12px;font-weight:700;letter-spacing:-.4px;font-size:18px}.mark{display:grid;place-items:center;background:var(--green);color:white;width:34px;height:34px;border-radius:10px;font-size:18px}.topbar small{font-size:12px}
main{padding-top:40px!important;padding-bottom:48px!important}.hero{display:flex;justify-content:space-between;gap:24px;align-items:center;margin-bottom:26px}.hero p{margin-top:10px;color:var(--muted)}.actions{display:flex;gap:10px;flex-wrap:wrap}.actions form{margin:0}
.overview{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-bottom:30px}.metric{background:white;padding:22px 24px}.metric .label{display:block;font-size:12px;color:var(--muted);margin-bottom:9px}.metric strong{display:block;font-size:24px;letter-spacing:-.6px;line-height:1.4}.metric small{display:block;margin-top:6px;font-size:12px}.badge{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;padding:5px 10px;border-radius:6px;background:#edf2ed;color:#42594b}.success{color:#216244;background:#eaf4ed}.error{color:#a1382c;background:#fbeeea}.neutral{color:#5c6246;background:#f1f0e4}.badge:before{content:"";width:6px;height:6px;background:currentColor;border-radius:50%;flex-shrink:0}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:28px;align-items:start}.history{grid-column:1;grid-row:1;min-width:0}.settings{grid-column:2;grid-row:1;min-width:0}.section-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;gap:12px}.section-head small{font-size:12px}.settings>p{font-size:13px;margin-bottom:16px}
details{border:1px solid var(--line);background:white;border-radius:12px;margin-bottom:12px;overflow:hidden}summary{cursor:pointer;min-height:56px;padding:17px 20px;font-weight:600;font-size:14px}summary::marker{color:#799384}details[open]>summary{border-bottom:1px solid var(--line)}.settings details>form,.settings details>p{padding:18px 20px}.settings details>p{padding-top:0;font-size:12px;color:var(--muted)}.settings form p{margin:0 0 16px}.settings label{font-size:13px;font-weight:500;display:block}.settings input:not([type=checkbox]):not([type=hidden]),textarea,select{width:100%;min-width:0;border:1px solid #cfdacf;background:#fcfdfb;color:var(--ink);border-radius:7px;padding:9px 11px;margin-top:6px;min-height:42px}textarea{resize:vertical}input[type=checkbox]{accent-color:var(--green);width:17px;height:17px;vertical-align:middle;margin-right:7px}.settings button{width:100%;font-size:13px}
.event>summary{display:flex;gap:12px;align-items:center;list-style:none;padding:18px 20px}.event>summary::-webkit-details-marker{display:none}.event>summary:after{content:"+";color:var(--muted);font-size:20px;margin-left:auto}.event[open]>summary:after{content:"−"}.event-title{display:flex;flex-direction:column;gap:3px;min-width:0}.event-title small{font-size:12px;font-weight:400}.event-body{padding:22px}.event-body p{font-size:14px;overflow-wrap:anywhere}.event-body .meta{font-size:12px;margin-bottom:18px;color:var(--muted)}.event-body .reason{border-left:3px solid #bdd5c4;padding-left:14px;margin-bottom:18px}.event-body .warning{color:#a1382c;margin:14px 0}.event-body .email{font-size:12px;color:var(--muted);margin:16px 0}
table{width:100%;border-collapse:collapse;table-layout:fixed;margin:12px 0 0}th,td{padding:13px 8px;border-bottom:1px solid #e9ede7;text-align:left;overflow-wrap:anywhere;font-size:13px}th{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}th:first-child{width:44%}td small{display:block;font-size:11px}td strong{font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}.alert{padding:20px;border:1px solid #efd4ca;border-radius:12px;background:#fff3ed;margin-bottom:24px}.alert p{margin-top:8px;overflow-wrap:anywhere;font-size:14px}.empty{padding:32px;border:1px dashed #cad5c9;border-radius:12px;color:var(--muted)}footer{border-top:1px solid var(--line);margin-top:28px;padding-top:18px;font-size:12px;color:var(--muted)}
@media(max-width:900px){.layout{grid-template-columns:minmax(0,1fr)}.settings{grid-column:1;grid-row:1}.history{grid-row:2}.overview{grid-template-columns:1fr 1fr}.metric:first-child{grid-column:1/-1}.hero{align-items:flex-start}.actions{justify-content:flex-end}}@media(max-width:560px){.shell{padding:0 18px}.topbar .shell{height:64px}.topbar small{display:none}main{padding-top:26px!important}.hero{display:block}h1{font-size:29px}.actions{justify-content:flex-start;margin-top:20px}.overview{margin-bottom:24px}.metric{padding:18px}.metric strong{font-size:22px}.event>summary{padding:15px 14px;gap:9px}.event-body{padding:16px}.badge{font-size:11px}.event-title{font-size:13px}.section-head{align-items:baseline}th,td{padding:12px 4px}}
</style></head><body><header class="topbar"><div class="shell"><div class="brand"><span class="mark" aria-hidden="true">w</span>Workload</div><small>ANKI TOOLKIT / TWÓJ PLAN NAUKI</small></div></header><main class="shell">
<section class="hero"><div><p class="eyebrow">Panel sterowania</p><h1>Nauka w Twoim tempie.</h1><p>Plan, synchronizacja i historia — w jednym miejscu.</p></div><div class="actions">''']
    parts.append(f'<a class="button secondary" href="/">Odśwież historię</a><form method="post" action="/run"><input type="hidden" name="token" value="{escape(token)}">'
                 f'<button {"disabled" if running else ""}>Uruchom teraz</button></form></div></section>'
                 '<section class="overview" aria-label="Podsumowanie">'
                 f'<div class="metric"><span class="label">Status</span><span class="badge {tone}">{status}</span>'
                 f'<small>{"Odśwież historię, aby sprawdzić wynik." if running else "Zapis limitów włączony" if settings.get("apply") else "Tryb symulacji · bez zapisu limitów"}</small></div>'
                 f'<div class="metric"><span class="label">Budżet nauki</span><strong>{escape(str(settings.get("minutes_per_day", 15)))} <small style="display:inline;font-size:15px">min / dzień</small></strong>'
                 f'<small>Maksymalnie {escape(str(settings.get("max_minutes_per_day", 30)))} min</small></div>'
                 f'<div class="metric"><span class="label">Godzina harmonogramu</span><strong>{escape(str(settings.get("run_at", "05:00")))}</strong>'
                 f'<small>Pułap nowych kart: {escape(str(settings.get("new_cards_per_day", 3)))}</small></div></section>')
    if intervention:
        parts.append('<article class="alert"><h2>Wymagana interwencja</h2><p>Harmonogram wstrzymany: '
                     + escape(intervention.get("error", "")) + '</p></article>')
    parts.append('<div class="layout"><aside class="settings"><div class="section-head"><h2>Ustawienia</h2></div><p class="muted">Dostosuj plan i połączenie z Anki.</p>')
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
    parts.append(f'<details><summary>Napraw synchronizację</summary><form method="post" action="/download">'
                 f'<input type="hidden" name="token" value="{escape(token)}">'
                 '<p>Pobranie zastąpi kopię Workload na RPi. Powstanie kopia bezpieczeństwa. '
                 'Stan limitów zostanie zachowany i sprawdzony przed wznowieniem harmonogramu.</p>'
                 '<p><label><input type="checkbox" name="confirm" value="yes" required>'
                 'Potwierdzam, że serwer ma aktualną kolekcję po synchronizacji moich urządzeń.</label></p>'
                 f'<button {"disabled" if running else ""}>Pobierz kolekcję z serwera</button></form></details>')
    parts.append('</aside><section class="history" aria-label="Historia przebiegów"><div class="section-head"><h2>Historia przebiegów</h2>'
                 f'<small>Ostatnie wpisy: {len(history)}</small></div>')
    if not history:
        parts.append('<div class="empty"><h2>Zacznij od połączenia z Anki</h2><p>Rozwiń Ustawienia i konto Anki, aby skonfigurować kolekcję. Tutaj pojawi się wynik pierwszego przebiegu.</p></div>')
    for index, event in enumerate(reversed(history)):
        ok = event.get('status') == 'success'
        mode = ('Zapis limitów' if event.get('apply') else 'Symulacja — bez zapisu limitów')
        if event.get("command") == "download":
            mode = "Pobranie kolekcji z serwera"
        if event.get('command') in ('init', 'login'):
            mode = 'Inicjalizacja' if event['command'] == 'init' else 'Odświeżenie logowania'
        status = 'Sukces' if ok else 'Błąd'
        stamp = event.get("finished", event.get("started", ""))
        parts.append(f'<details class="event" {"open" if index == 0 else ""}><summary>'
                     f'<span class="badge {"success" if ok else "error"}">{status}</span>'
                     f'<span class="event-title">{escape(mode)}<small>{escape(display_time(stamp))}</small></span></summary>'
                     '<div class="event-body">'
                     f'<p class="meta">Start: {escape(display_time(event.get("started", "")))}<br>'
                     f'Koniec: {escape(display_time(event.get("finished", "")))}</p>')
        if not ok and event.get("command") in ("run", "restore"):
            parts.append('<p class="warning">Zmiany nie są potwierdzone; część mogła zostać wysłana.</p>')
        for key in ('reason', 'error'):
            if event.get(key):
                parts.append(f'<p class="reason">{escape(event[key])}</p>')
        if event.get('email') and event['email'] != 'not_needed':
            parts.append('<p class="email">E-mail: ' + escape({'sent': 'wysłano', 'suppressed_duplicate': 'pominięto powtórzony alert'}.get(event['email'], event['email'])) + '</p>')
        changes = event.get('changes', [])
        if changes:
            parts.append('<p>Zmiany limitów' + (' potwierdzone synchronizacją' if ok and event.get('apply') else ' planowane') +
                         ':</p><table><tr><th>Talia</th><th>Przed</th><th>Po</th></tr>')
            for change in changes:
                values = [escape(change['deck'])]
                for key in ('before', 'after'):
                    limit = change[key]
                    base = limit.get('newLimit')
                    today = limit.get('newLimitToday')
                    values.append(f"<strong>{escape(str(today['limit'])) if today else '—'}</strong>"
                                  f"<small>{'Limit dzienny' if today else 'Brak nadpisania'} · bazowy: {escape(str(base)) if base is not None else 'z presetu'}</small>")
                parts.append('<tr>' + ''.join(f'<td>{value}</td>' for value in values) + '</tr>')
            parts.append('</table>')
        else:
            parts.append('<p>Brak zaplanowanych zmian limitów.</p>')
        cost = event.get('card_costs', {})
        if cost.get('total_seconds', 0) > 0:
            parts.append(f'<p>Ostatnie 7 zakończonych dni: {cost["total_seconds"] / 60:.1f} min; '
                         f'niedawno wprowadzone karty: {cost["cohort_seconds"] / 60:.1f} min.</p>')
        parts.append('</div></details>')
    return ''.join(parts) + '</section></div><footer>Historia synchronizacji Workload, nie potwierdzenie synchronizacji telefonu. Ostatnie 200 przebiegów · odświeżanie ręczne.</footer></main></body></html>'


def serve(data_dir, config_path=Path("/config/workload.json")):
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
                        config = worker.settings_from(config_path, data_dir, config)
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
                                            command, "--data", str(data_dir), "--config", str(config_path)], env=env)
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
                                worker.settings_from(config_path, data_dir) if (data_dir / "settings.json").exists() else json.loads(os.environ.get("WORKLOAD_CONFIG", "{}")),
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
