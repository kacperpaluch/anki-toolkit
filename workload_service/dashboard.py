"""Local dashboard: today's plan, settings (the only place they are edited) and run history."""
import fcntl
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

try:
    from . import notifications, worker
except ImportError:  # run as a script inside the image
    import notifications
    import worker

# Fixed messages after a redirect; the query string never reaches the page as text.
DONE = {
    "plan": "Zapisano ustawienia planu.",
    "mail": "Zapisano powiadomienia.",
    "run": "Uruchomiono przebieg.",
    "init": "Łączenie z Anki i pobieranie kolekcji — może potrwać kilka minut.",
    "login": "Odnawianie logowania…",
    "restore": "Przywracanie limitów… Zapis limitów został wyłączony.",
    "download": "Pobieranie kolekcji z serwera…",
}
COMMANDS = {"init": "Połączenie z Anki", "login": "Odnowienie logowania", "restore": "Przywrócenie limitów",
            "download": "Pobranie kolekcji z serwera"}
EMAIL = {"sent": "wysłano", "suppressed_duplicate": "pominięto powtórzony alert"}


def e(value):
    return escape(str(value), quote=True)


def display_time(value):
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y · %H:%M:%S")
    except ValueError:
        return value


def short_date(value):
    try:
        return datetime.fromisoformat(value).strftime("%d.%m")
    except ValueError:
        return value


def runs_with_plan(history):
    return [event for event in history if event.get("command") == "run"
            and event.get("status") == "success" and event.get("plan")]


def next_run(history, settings, ready, now):
    if not ready:
        return "po konfiguracji"
    today = now.date().isoformat()
    done = any(event.get("started", "").startswith(today) for event in runs_with_plan(history))
    if done:
        return "jutro " + settings["run_at"]
    return ("dziś " + settings["run_at"]) if now.strftime("%H:%M") < settings["run_at"] else "za chwilę"


CSS = """
:root{color-scheme:light dark;--bg:#f4f5f1;--paper:#fff;--ink:#1f2d27;--muted:#63716a;--line:#dfe5de;
--accent:#25634b;--accent-ink:#fff;--soft:#eaf3ed;--warn:#9a3a2c;--warn-bg:#fbeee9;--field:#fbfcfa;--bar-sim:#b7cfc1}
@media(prefers-color-scheme:dark){:root{--bg:#141a17;--paper:#1c2420;--ink:#e3ebe6;--muted:#9aa9a1;--line:#2d3833;
--accent:#6fc19a;--accent-ink:#0f1a15;--soft:#22342b;--warn:#f0a393;--warn-bg:#3a2320;--field:#18201c;--bar-sim:#3d5a4b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
h1,h2,h3,p{margin:0}h2{font-size:17px}p+p{margin-top:10px}small,.muted{color:var(--muted)}a{color:var(--accent)}
button,input,select{font:inherit;color:inherit}
button{min-height:42px;border:1px solid var(--accent);border-radius:9px;padding:9px 16px;background:var(--accent);color:var(--accent-ink);font-weight:600;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}button.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
button.danger{background:var(--warn);border-color:var(--warn);color:var(--paper)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.shell{max-width:1120px;margin:auto;padding:0 20px}
header{background:var(--paper);border-bottom:1px solid var(--line)}header .shell{display:flex;gap:14px;align-items:center;justify-content:space-between;min-height:68px;flex-wrap:wrap;padding-block:10px}
.brand{display:flex;gap:10px;align-items:center;font-weight:700;font-size:18px}.mark{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:var(--accent);color:var(--accent-ink)}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.bar form{margin:0}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;padding:4px 10px;border-radius:99px;background:var(--soft)}
.pill:before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}.pill.error{color:var(--warn);background:var(--warn-bg)}.pill.ok{color:var(--accent)}
main{padding-block:26px 48px}.notice{padding:12px 16px;border-radius:10px;margin-bottom:18px;background:var(--soft)}.notice.error{background:var(--warn-bg);color:var(--warn)}
.card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:20px}.card+.card,.stack>*+*{margin-top:16px}
.alert{border-color:var(--warn);background:var(--warn-bg)}.alert h2{color:var(--warn)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:22px;align-items:start}
.steps{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:8px}.steps li{display:flex;gap:10px;align-items:baseline}
.steps li:before{content:"○";color:var(--muted)}.steps li.done{color:var(--muted);text-decoration:line-through}.steps li.done:before{content:"✓";color:var(--accent)}
.today{display:grid;grid-template-columns:auto 1fr;gap:6px 24px;align-items:center}
.big{font-size:56px;line-height:1;font-weight:700;letter-spacing:-2px;font-variant-numeric:tabular-nums}
.facts{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:14px}.facts strong{display:block;font-size:20px}
.reason{border-left:3px solid var(--accent);padding-left:12px;margin-top:14px}
.decks{list-style:none;margin:14px 0 0;padding:0}.decks li{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-top:1px solid var(--line);font-size:14px}
.decks li.child{padding-left:18px;color:var(--muted)}
.chart{display:flex;align-items:flex-end;gap:6px;height:120px;margin-top:14px}
.chart div{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:4px;height:100%;font-size:11px;color:var(--muted);min-width:0}
.chart i{display:block;width:100%;max-width:34px;border-radius:5px 5px 2px 2px;background:var(--accent);min-height:3px}.chart i.sim{background:var(--bar-sim)}
details{background:var(--paper);border:1px solid var(--line);border-radius:12px}details+details{margin-top:10px}
summary{cursor:pointer;padding:14px 18px;font-weight:600}details[open]>summary{border-bottom:1px solid var(--line)}
details>form,details>.body{padding:16px 18px}form p{margin:0 0 14px}
label{display:block;font-size:13px;font-weight:500}
input:not([type=checkbox]),select{width:100%;margin-top:5px;min-height:40px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--field)}
input[type=checkbox]{accent-color:var(--accent);width:17px;height:17px;vertical-align:-3px;margin-right:8px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.picker{max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--field)}
.picker label{font-weight:400;padding:4px 0}.hint{font-size:12px;color:var(--muted);margin-top:4px}
.event summary{display:flex;gap:10px;align-items:center;font-weight:500}.event summary small{margin-left:auto}
.event .body p{font-size:14px;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse;table-layout:fixed;margin-top:10px;font-size:13px}th,td{text-align:left;padding:8px 4px;border-top:1px solid var(--line);overflow-wrap:anywhere}th{font-size:11px;color:var(--muted);text-transform:uppercase}
footer{margin-top:28px;font-size:12px;color:var(--muted)}
@media(max-width:900px){.layout{grid-template-columns:1fr}}
@media(max-width:520px){.big{font-size:44px}.row{grid-template-columns:1fr}header .shell{min-height:60px}}
"""


def token_field(token):
    return f'<input type="hidden" name="token" value="{e(token)}">'


def render(history, token="", running=False, settings=None, identity=None, mail=None,
           intervention=None, decks=None, notice=None, managed=False, now=None):
    settings = {**worker.default_settings(), **(settings or {})}
    mail = mail or {}
    now = now or datetime.now()
    latest = history[-1] if history else {}
    planned = runs_with_plan(history)
    ready = bool(identity and settings["decks"])
    if intervention:
        status, tone = "Wymagana interwencja", "error"
    elif running:
        status, tone = "Przebieg trwa…", ""
    elif latest.get("status") == "error":
        status, tone = "Ostatnia operacja nieudana", "error"
    elif latest:
        status, tone = "Ostatnia operacja udana", "ok"
    else:
        status, tone = "Gotowy do konfiguracji", ""
    parts = ['<!doctype html><html lang="pl"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Workload</title>'
             f'<style>{CSS}</style></head><body><header><div class="shell">'
             '<div class="brand"><span class="mark" aria-hidden="true">w</span>Workload</div><div class="bar">'
             f'<span class="pill {tone}">{e(status)}</span>'
             f'<form method="post" action="/run">{token_field(token)}'
             f'<button {"disabled" if running or not ready else ""}>Uruchom teraz</button></form>'
             '</div></div></header><main class="shell">']
    if notice:
        parts.append(f'<p class="notice {e(notice[0])}" role="status">{e(notice[1])}</p>')
    if intervention:
        parts.append('<section class="card alert"><h2>Wymagana interwencja</h2>'
                     f'<p>Harmonogram wstrzymany: {e(intervention.get("error", ""))}</p>'
                     + download_form(token, running) + '</section>')

    steps = [("Połącz konto Anki", bool(identity)), ("Wybierz talie", bool(settings["decks"])),
             ("Sprawdź wynik symulacji", bool(planned)), ("Włącz zapis limitów", settings["apply"])]
    if not all(done for _, done in steps):
        parts.append('<section class="card"><h2>Pierwsze kroki</h2><ol class="steps">'
                     + "".join(f'<li class="{"done" if done else ""}">{e(label)}</li>' for label, done in steps)
                     + '</ol><p class="hint">Ustawienia są w panelu obok. Zapis limitów włącz dopiero, '
                     'gdy symulacja wygląda rozsądnie.</p></section>')

    parts.append('<div class="layout"><div class="stack">')
    parts.append(today_card(planned[-1] if planned else None, settings, now, next_run(history, settings, ready, now)))
    parts.append(chart(planned))
    parts.append('<section><h2 style="margin:6px 0 12px">Historia przebiegów</h2>')
    if not history:
        parts.append('<p class="card muted">Tu pojawi się wynik pierwszego przebiegu.</p>')
    for index, event in enumerate(reversed(history)):
        parts.append(event_block(event, index == 0))
    parts.append('</section></div><aside>')
    parts.append(plan_form(token, settings, decks, managed, open_=bool(identity) and not settings["decks"]))
    parts.append(account_form(token, identity))
    parts.append(mail_form(token, mail))
    parts.append('<details><summary>Konserwacja</summary><div class="body">'
                 f'<form method="post" action="/restore">{token_field(token)}'
                 '<p>Wyłącza zapis limitów i przywraca limity nowych kart sprzed pierwszego przebiegu. '
                 'Potrzebne przed zmianą talii albo przy rezygnacji z automatu.</p>'
                 '<p><label><input type="checkbox" name="confirm" value="yes" required>'
                 'Rozumiem — automat przestanie ustawiać limity.</label></p>'
                 f'<button class="danger" {"disabled" if running or not managed else ""}>Przywróć limity</button></form>'
                 '<hr style="border:0;border-top:1px solid var(--line);margin:18px 0">'
                 + download_form(token, running) + '</div></details>')
    parts.append('</aside></div><footer>Historia przebiegów usługi — nie potwierdza synchronizacji telefonu. '
                 'Ostatnie 200 wpisów. Panel nie ma logowania: udostępniaj go tylko w zaufanej sieci.</footer></main>')
    if running:
        # Reload once the run finishes; forms are locked while it runs anyway.
        parts.append('<script>setInterval(()=>fetch("/status").then(r=>r.json())'
                     '.then(s=>{if(!s.running)location.replace("/")}).catch(()=>{}),3000)</script>')
    return "".join(parts) + '</body></html>'


def today_card(event, settings, now, upcoming):
    mode = "Zapis limitów włączony" if settings["apply"] else "Symulacja — limity nie są zmieniane"
    head = f'<p class="muted" style="margin-top:4px">{e(mode)} · następny przebieg: {e(upcoming)}</p>'
    if not event:
        return ('<section class="card"><h2>Dziś</h2>' + head
                + '<p style="margin-top:14px">Brak planu. Po pierwszym przebiegu zobaczysz tu porcję nowych kart.</p></section>')
    plan = event["plan"]
    today = event.get("started", "").startswith(now.date().isoformat())
    title = "Dziś" if today else "Ostatni plan · " + short_date(event.get("started", ""))
    word = "nowa karta" if plan["new_today"] == 1 else "nowe karty" if plan["new_today"] % 10 in (2, 3, 4) and plan["new_today"] % 100 not in (12, 13, 14) else "nowych kart"
    parts = [f'<section class="card"><h2>{e(title)}</h2>{head}<div class="today" style="margin-top:14px">'
             f'<div class="big">{e(plan["new_today"])}</div><div><strong>{e(word)}</strong>'
             '<br><small>łącznie z już wprowadzonymi dziś</small></div></div>'
             '<div class="facts">'
             f'<div><small>Powtórki i nauka</small><strong>{e(plan["due_cards"])}</strong></div>'
             f'<div><small>Szacowany czas</small><strong>~{e(round(plan["due_minutes"]))} min</strong></div>'
             f'<div><small>Budżet</small><strong>{e(settings["minutes_per_day"])}–{e(settings["max_minutes_per_day"])} min</strong></div>'
             f'<div><small>Tempo tygodnia</small><strong>{e(plan["pace"])}/dzień</strong></div></div>'
             f'<p class="reason">{e(event.get("reason", ""))}</p>'
             f'<p class="muted" style="margin-top:8px">{e(plan["pace_reason"])}</p><ul class="decks">']
    for row in plan["decks"]:
        name = row["deck"] if row["root"] else "↳ " + row["deck"].rpartition("::")[2]
        parts.append(f'<li class="{"" if row["root"] else "child"}"><span>{e(name)}</span><strong>{e(row["limit"])}</strong></li>')
    return "".join(parts) + '</ul></section>'


def chart(planned):
    days = {}
    for event in planned:
        days[event["started"][:10]] = event
    days = list(days.values())[-14:]
    if len(days) < 2:
        return ""
    top = max(max(event["plan"]["new_today"] for event in days), 1)
    bars = "".join(
        f'<div title="{e(short_date(event["started"]))}: {e(event["plan"]["new_today"])}'
        f'{" (symulacja)" if not event.get("apply") else ""}">{e(event["plan"]["new_today"])}'
        f'<i class="{"" if event.get("apply") else "sim"}" style="height:{max(3, round(90 * event["plan"]["new_today"] / top))}%"></i>'
        f'{e(short_date(event["started"]))}</div>' for event in days)
    return ('<section class="card"><h2>Nowe karty — ostatnie dni</h2>'
            '<p class="hint">Jaśniejsze słupki to symulacja.</p>'
            f'<div class="chart" aria-label="Porcje nowych kart w ostatnich dniach">{bars}</div></section>')


def event_block(event, open_):
    ok = event.get("status") == "success"
    if event.get("command") == "run":
        mode = "Zapis limitów" if event.get("apply") else "Symulacja"
    else:
        mode = COMMANDS.get(event.get("command"), event.get("command", ""))
    summary = mode + (f' · {event["plan"]["new_today"]} nowych' if ok and event.get("plan") else "")
    parts = [f'<details class="event" {"open" if open_ else ""}><summary>'
             f'<span class="pill {"ok" if ok else "error"}">{"Sukces" if ok else "Błąd"}</span>{e(summary)}'
             f'<small>{e(display_time(event.get("finished", event.get("started", ""))))}</small></summary><div class="body">'
             f'<p class="muted">Start {e(display_time(event.get("started", "")))} · koniec {e(display_time(event.get("finished", "")))}</p>']
    if not ok and event.get("command") in ("run", "restore"):
        parts.append('<p style="color:var(--warn)">Zmiany nie są potwierdzone; część mogła zostać wysłana.</p>')
    for key in ("reason", "error"):
        if event.get(key):
            parts.append(f'<p class="reason">{e(event[key])}</p>')
    if event.get("email") and event["email"] != "not_needed":
        parts.append(f'<p class="muted">E-mail: {e(EMAIL.get(event["email"], event["email"]))}</p>')
    changes = event.get("changes", [])
    if changes:
        parts.append('<p>Zmiany limitów ' + ("potwierdzone synchronizacją" if ok and event.get("apply") else "planowane")
                     + ':</p><table><tr><th>Talia</th><th>Przed</th><th>Po</th></tr>')
        for change in changes:
            cells = [e(change["deck"])]
            for key in ("before", "after"):
                today = change[key].get("newLimitToday")
                base = change[key].get("newLimit")
                cells.append(f'<strong>{e(today["limit"]) if today else "—"}</strong><br><small>bazowy: '
                             f'{e(base) if base is not None else "z presetu"}</small>')
            parts.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        parts.append("</table>")
    elif event.get("command") in ("run", "restore"):
        parts.append('<p class="muted">Brak zmian limitów.</p>')
    cost = event.get("card_costs", {})
    if cost.get("total_seconds", 0) > 0:
        parts.append(f'<p class="muted">Ostatnie 7 zakończonych dni: {cost["total_seconds"] / 60:.1f} min odpowiedzi; '
                     f'karty wprowadzone w 14 dniach: {cost["cohort_seconds"] / 60:.1f} min.</p>')
        tops = ", ".join(f'cid:{row["cid"]} ({row["seconds"] / 60:.1f} min, {row["again"]}× Ponownie)'
                         for row in cost.get("top", []))
        if tops:
            parts.append(f'<p class="muted">Najwięcej czasu: {e(tops)}</p>')
    return "".join(parts) + "</div></details>"


def plan_form(token, settings, decks, managed, open_):
    selected = set(settings["decks"])
    known = decks or []
    names = known + sorted(selected - set(known))
    if names:
        picker = '<div class="picker">' + "".join(
            f'<label style="padding-left:{16 * name.count("::")}px"><input type="checkbox" name="deck" value="{e(name)}"'
            f'{" checked" if name in selected else ""}>{e(name.rpartition("::")[2])}'
            f'{" <small>(nie ma w kolekcji)</small>" if name not in known else ""}</label>' for name in names) + '</div>'
    else:
        picker = '<p class="hint">Lista talii pojawi się po połączeniu konta Anki.</p>'
    number = lambda name, label, low, high: (
        f'<label>{label}<input name="{name}" type="number" min="{low}" max="{high}" required value="{e(settings[name])}"></label>')
    measured = lambda name, label: (
        f'<p><label>{label}<input name="{name}" type="number" min="0" step="any" value="{e(settings[name])}"></label></p>')
    return (f'<details {"open" if open_ else ""}><summary>Plan nauki</summary>'
            f'<form method="post" action="/plan">{token_field(token)}'
            f'<p><label>Talie</label>{picker}<span class="hint">Talia nadrzędna obejmuje podtalie.'
            f'{" Zmiana talii wymaga najpierw przywrócenia limitów (Konserwacja)." if managed else ""}</span></p>'
            f'<p class="row">{number("minutes_per_day", "Zwykły czas (min)", 5, 240)}'
            f'{number("max_minutes_per_day", "Górna granica (min)", 5, 240)}</p>'
            f'<p class="row">{number("new_cards_per_day", "Pułap nowych kart / dzień", 0, 100)}'
            f'<label>Godzina przebiegu<input name="run_at" type="time" required value="{e(settings["run_at"])}"></label></p>'
            f'<p><label><input type="checkbox" name="apply"{" checked" if settings["apply"] else ""}>'
            'Zapisuj limity w Anki</label><span class="hint">Wyłączone = symulacja: plan jest liczony, '
            'ale limity się nie zmieniają.</span></p>'
            '<details style="margin-bottom:14px"><summary>Zaawansowane</summary><div class="body">'
            '<p><label>Podział między talie<select name="split_strategy">'
            + "".join(f'<option value="{value}"{" selected" if settings["split_strategy"] == value else ""}>{label}</option>'
                      for value, label in (("proportional", "Proporcjonalnie do limitów talii"),
                                           ("heaviest_first", "Najpierw zmniejszaj największy limit")))
            + '</select></label></p><p class="hint">0 = mierz z historii.</p>'
            + measured("seconds_per_card", "Czas powtórki (s)")
            + measured("learn_seconds_per_card", "Czas odpowiedzi w nauce (s)")
            + measured("learn_answers_per_new_card", "Odpowiedzi w nauce na nową kartę")
            + '</div></details><button>Zapisz plan</button></form></details>')


def account_form(token, identity):
    if identity:
        server = identity["endpoint"] or "AnkiWeb"
        return ('<details><summary>Konto Anki</summary>'
                f'<form method="post" action="/account">{token_field(token)}'
                f'<p>Serwer: <strong>{e(server)}</strong><br>Login: <strong>{e(identity["username"])}</strong></p>'
                '<p><label>Hasło — tylko gdy trzeba odnowić logowanie'
                '<input name="password" type="password" autocomplete="current-password" required></label></p>'
                '<button class="ghost">Odnów logowanie</button>'
                '<p class="hint" style="margin-top:12px">Hasło nie jest zapisywane. Zmiana konta lub serwera '
                'wymaga nowego, pustego katalogu danych.</p></form></details>')
    return ('<details open><summary>Konto Anki</summary>'
            f'<form method="post" action="/account">{token_field(token)}'
            '<p><label>Serwer<input name="url" value="ankiweb" required></label>'
            '<span class="hint">„ankiweb” albo adres własnego serwera sync.</span></p>'
            '<p><label>Login<input name="username" autocomplete="username" required></label></p>'
            '<p><label>Hasło<input name="password" type="password" autocomplete="current-password" required></label></p>'
            '<button>Połącz i pobierz kolekcję</button>'
            '<p class="hint" style="margin-top:12px">Najpierw zsynchronizuj kolekcję z aplikacji Anki. '
            'Hasło służy tylko do zalogowania; zapisywany jest token.</p></form></details>')


def mail_form(token, mail):
    fields = "".join(
        f'<p><label>{label}<input name="{name}" type="{kind}" value="{e(mail.get(name, default))}"></label></p>'
        for name, label, kind, default in (("host", "Host SMTP", "text", ""), ("port", "Port", "number", 587),
                                           ("username", "Login SMTP (pusty = bez logowania)", "text", ""),
                                           ("sender", "Nadawca", "email", ""), ("recipient", "Odbiorca", "email", "")))
    options = "".join(
        f'<option value="{value}"{" selected" if mail.get("security", "starttls") == value else ""}>{label}</option>'
        for value, label in (("starttls", "STARTTLS (zwykle 587)"), ("ssl", "TLS (zwykle 465)"), ("none", "Brak (lokalny relay)")))
    return ('<details><summary>Powiadomienia e-mail</summary>'
            f'<form method="post" action="/mail">{token_field(token)}'
            f'<p><label><input type="checkbox" name="enabled"{" checked" if mail.get("enabled") else ""}>'
            'Wysyłaj raport po każdym przebiegu i alert przy błędzie</label></p>'
            f'{fields}<p><label>Szyfrowanie<select name="security">{options}</select></label></p>'
            '<p><label>Hasło SMTP (puste = zachowaj zapisane)<input type="password" name="password" autocomplete="new-password"></label></p>'
            '<p><label><input type="checkbox" name="clear_password">Usuń zapisane hasło SMTP</label></p>'
            '<button>Zapisz powiadomienia</button></form></details>')


def download_form(token, running):
    return (f'<form method="post" action="/download">{token_field(token)}'
            '<p>Pobranie zastąpi kopię kolekcji usługi wersją z serwera (z kopią bezpieczeństwa). '
            'Nic nie jest wysyłane.</p><p><label><input type="checkbox" name="confirm" value="yes" required>'
            'Moje urządzenia wysłały aktualne dane na serwer.</label></p>'
            f'<button class="ghost" {"disabled" if running else ""}>Pobierz kolekcję z serwera</button></form>')


def serve(data_dir, port=8080):
    token = secrets.token_urlsafe(32)
    process = None

    def running():
        if process is not None and process.poll() is None:
            return True
        path = data_dir / "worker.lock"
        if not path.exists():
            return False
        with path.open("r") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True

    def page(notice=None):
        try:
            settings = worker.load_settings(data_dir)
        except (worker.WorkloadError, ValueError) as error:
            settings, notice = worker.default_settings(), notice or ("error", f"Błędny plik ustawień: {error}")
        return render(worker.read_json(data_dir / "history.json", []), token, running(), settings,
                      worker.read_json(data_dir / "identity.json"), worker.read_json(data_dir / "mail.json", {}),
                      worker.read_json(data_dir / "intervention.json"), worker.read_json(data_dir / "decks.json"),
                      notice, bool(worker.read_json(data_dir / "state.json", {}).get("managed")))

    def save_plan(form):
        get = lambda name: form.get(name, [""])[0].strip()
        try:
            values = {name: int(get(name)) for name in ("minutes_per_day", "max_minutes_per_day", "new_cards_per_day")}
            values.update({name: float(get(name) or 0) for name in
                           ("seconds_per_card", "learn_seconds_per_card", "learn_answers_per_new_card")})
        except ValueError:
            raise worker.WorkloadError("Podaj liczby w polach czasu, tempa i pomiarów") from None
        values.update(run_at=get("run_at"), apply="apply" in form, split_strategy=get("split_strategy"),
                      decks=sorted({name.strip() for name in form.get("deck", []) if name.strip()}))
        previous = worker.load_settings(data_dir)
        if (worker.read_json(data_dir / "state.json", {}).get("managed")
                and set(values["decks"]) != set(previous["decks"])):
            raise worker.WorkloadError("Przed zmianą talii przywróć limity (Konserwacja)")
        worker.save_settings(data_dir, values)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body, kind="text/html"):
            body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/":
                done = DONE.get(parse_qs(url.query).get("done", [""])[0])
                self.respond(200, page(("ok", done) if done else None))
            elif url.path == "/status":
                self.respond(200, json.dumps({"running": running()}), "application/json")
            elif url.path == "/history.json":
                history = worker.read_json(data_dir / "history.json", [])
                self.respond(200, json.dumps(history, ensure_ascii=False), "application/json")
            else:
                self.send_error(404)

        def do_POST(self):
            nonlocal process
            action = self.path
            if action not in ("/run", "/plan", "/account", "/mail", "/download", "/restore"):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                self.send_error(400)
                return
            form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            if not secrets.compare_digest(form.get("token", [""])[0], token):
                self.send_error(403)
                return
            get = lambda name: form.get(name, [""])[0]
            command, env = None, os.environ.copy()
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                if action == "/mail":
                    config = notifications.settings_from(form, worker.read_json(data_dir / "mail.json", {}))
                    worker.write_json(data_dir / "mail.json", config)
                    (data_dir / "mail.json").chmod(0o600)
                    done = "mail"
                elif running():
                    raise worker.WorkloadError("Przebieg trwa — poczekaj na wynik")
                elif action == "/plan":
                    with (data_dir / "worker.lock").open("a") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        save_plan(form)
                    done = "plan"
                elif action == "/account":
                    identity = worker.read_json(data_dir / "identity.json")
                    if not get("password"):
                        raise worker.WorkloadError("Podaj hasło Anki")
                    env["ANKI_SYNC_PASSWORD"] = get("password")
                    if identity:
                        command = done = "login"
                    else:
                        endpoint, username = worker.credentials(get("url"), get("username"))
                        env["ANKI_SYNC_URL"], env["ANKI_SYNC_USERNAME"] = endpoint or "ankiweb", username
                        command = done = "init"
                elif action == "/run":
                    command = done = "run"
                elif get("confirm") != "yes":
                    raise worker.WorkloadError("Zaznacz potwierdzenie")
                elif action == "/download":
                    command = done = "download"
                else:  # /restore: stop applying first, so the scheduler does not re-apply limits
                    with (data_dir / "worker.lock").open("a") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        worker.save_settings(data_dir, {"apply": False})
                    command = done = "restore"
            except BlockingIOError:
                self.respond(409, page(("error", "Przebieg trwa — poczekaj na wynik")))
                return
            except (worker.WorkloadError, ValueError) as error:
                self.respond(400, page(("error", str(error))))
                return
            if command:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("worker.py")),
                                            command, "--data", str(data_dir)], env=env)
            self.send_response(303)
            self.send_header("Location", "/?done=" + done)
            self.end_headers()

        def log_message(self, *args):
            pass

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
