"""Scheduled Anki client. Own replica only; all remote writes use Anki sync."""

import argparse
import copy
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from urllib.parse import urlsplit

try:
    from . import logic, snapshot
except ImportError:  # run as a script: python workload_service/worker.py
    import logic
    import snapshot

LIMIT_FIELDS = ("newLimit", "newLimitToday")
DEFAULTS = {
    "apply": False,
    "run_at": "05:00",
    "minutes_per_day": 15,
    "max_minutes_per_day": 30,
    "new_cards_per_day": 3,
    # 0 = measured from history (median review/learn time, learn answers per new card).
    "seconds_per_card": 0,
    "learn_seconds_per_card": 0,
    "learn_answers_per_new_card": 0,
    "split_strategy": logic.SPLIT_PROPORTIONAL,
    "decks": [],
}


class WorkloadError(Exception):
    """Messages safe to print without credentials or card contents."""


class FullSyncRequired(WorkloadError):
    """A full download requires explicit operator confirmation."""


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, value):
    # Unique temporary name: the worker and the dashboard may write concurrently.
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=path.name + ".", delete=False) as file:
        file.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    Path(file.name).replace(path)


def default_settings():
    return copy.deepcopy(DEFAULTS)


def validate(settings):
    """Normalized copy of `settings`; raises WorkloadError with a message for the panel."""
    settings = {**default_settings(), **settings}
    for key, low, high, label in (("minutes_per_day", 5, 240, "Zwykły czas"),
                                  ("max_minutes_per_day", 5, 240, "Górna granica czasu"),
                                  ("new_cards_per_day", 0, 100, "Pułap nowych kart")):
        if type(settings[key]) is not int or not low <= settings[key] <= high:
            raise WorkloadError(f"{label}: podaj liczbę od {low} do {high}")
    if settings["max_minutes_per_day"] < settings["minutes_per_day"]:
        raise WorkloadError("Górna granica czasu nie może być mniejsza niż zwykły czas")
    for key in ("seconds_per_card", "learn_seconds_per_card", "learn_answers_per_new_card"):
        if type(settings[key]) not in (int, float) or not 0 <= settings[key] <= 600:
            raise WorkloadError("Pomiary: podaj 0 (z historii) albo dodatnią liczbę")
    if not isinstance(settings["decks"], list) or any(
            not isinstance(name, str) or not name.strip() for name in settings["decks"]):
        raise WorkloadError("Niepoprawna lista talii")
    if type(settings["apply"]) is not bool:
        raise WorkloadError("apply must be true or false")
    if settings["split_strategy"] not in (logic.SPLIT_PROPORTIONAL, logic.SPLIT_HEAVIEST_FIRST):
        raise WorkloadError("Nieznana strategia podziału")
    try:
        settings["run_at"] = dt.datetime.strptime(settings["run_at"], "%H:%M").strftime("%H:%M")
    except (TypeError, ValueError):
        raise WorkloadError("Godzina w formacie GG:MM") from None
    return settings


def load_settings(data_dir):
    """`settings.json` in the data directory is the only source of settings."""
    path = data_dir / "settings.json"
    if not path.exists() and os.environ.get("WORKLOAD_CONFIG"):
        # ponytail: one-time import from the old Compose variable; delete once all installs migrated.
        data_dir.mkdir(parents=True, exist_ok=True)
        write_json(path, validate(json.loads(os.environ["WORKLOAD_CONFIG"])))
    return validate(read_json(path, {}))


def save_settings(data_dir, settings):
    """Merge into the stored settings, keeping unknown keys."""
    settings = validate({**read_json(data_dir / "settings.json", {}), **settings})
    write_json(data_dir / "settings.json", settings)
    return settings


def credentials(target=None, username=None):
    """Account for `init`: from the panel form or, on the CLI, from the environment."""
    target = (os.environ.get("ANKI_SYNC_URL", "ankiweb") if target is None else target).strip() or "ankiweb"
    endpoint = None if target == "ankiweb" else target.rstrip("/") + "/"
    if endpoint is not None:
        url = urlsplit(endpoint)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.query or url.fragment:
            raise WorkloadError("Serwer: wpisz 'ankiweb' albo adres http(s) bez loginu i parametrów")
    username = (os.environ.get("ANKI_SYNC_USERNAME", "") if username is None else username).strip()
    if not username:
        raise WorkloadError("Podaj login Anki")
    return endpoint, username


def checked_endpoint(endpoint, target):
    url = urlsplit(endpoint)
    if url.username or url.query or url.fragment or not url.hostname:
        raise WorkloadError("Invalid sync endpoint")
    if target is None:
        allowed = url.scheme == "https" and url.port in (None, 443) and (
            url.hostname == "ankiweb.net" or url.hostname.endswith(".ankiweb.net"))
    else:
        base = urlsplit(target)
        allowed = (url.scheme, url.hostname, url.port) == (base.scheme, base.hostname, base.port)
    if not allowed:
        raise WorkloadError("Refusing sync endpoint outside the configured server")
    return endpoint


def get_auth(col, data_dir, identity, login=False):
    from anki.sync_pb2 import SyncAuth
    cached = read_json(data_dir / "auth.json")
    if cached and not login:
        if cached["identity"] != identity:
            raise WorkloadError("Cached token belongs to another server/account")
        auth = SyncAuth(hkey=cached["hkey"], io_timeout_secs=60)
        if cached.get("endpoint"):
            auth.endpoint = checked_endpoint(cached["endpoint"], identity["endpoint"])
        elif identity["endpoint"] is not None:
            auth.endpoint = identity["endpoint"]
        return auth
    password = os.environ.get("ANKI_SYNC_PASSWORD", "")
    if not password:
        raise WorkloadError("Logowanie wymaga hasła Anki")
    auth = col.sync_login(identity["username"], password, identity["endpoint"])
    if identity["endpoint"] is not None:
        auth.endpoint = identity["endpoint"]
    auth.io_timeout_secs = 60
    save_auth(data_dir, identity, auth)
    return auth


def save_auth(data_dir, identity, auth):
    write_json(data_dir / "auth.json", {"identity": identity, "hkey": auth.hkey,
               "endpoint": auth.endpoint if auth.HasField("endpoint") else None})
    (data_dir / "auth.json").chmod(0o600)


def accept_endpoint(result, auth):
    if result.HasField("new_endpoint"):
        current = auth.endpoint if auth.HasField("endpoint") else None
        host = urlsplit(current).hostname if current else None
        official = host is None or host == "ankiweb.net" or host.endswith(".ankiweb.net")
        auth.endpoint = checked_endpoint(result.new_endpoint, None if official else current)


def clone_database(source, destination):
    # SQLite backup includes committed WAL data; never copy an open .anki2 file.
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)


def sync_normal(col, auth):
    from anki.sync_pb2 import SyncCollectionResponse as Response
    result = col.sync_collection(auth, sync_media=False)
    accept_endpoint(result, auth)
    if result.required != Response.NO_CHANGES:
        raise FullSyncRequired("Full sync requested. Stopped; no automatic upload/download is allowed")


def selected_decks(col, names):
    decks = [col.decks.get(item.id, default=False)
             for item in col.decks.all_names_and_ids(skip_empty_default=False)]
    for name in names:
        if not any(deck["name"] == name and not deck.get("dyn") for deck in decks):
            raise WorkloadError(f"Selected normal deck not found: {name}")
    return [deck for deck in decks if not deck.get("dyn") and any(
        deck["name"] == name or deck["name"].startswith(name + "::") for name in names)]


def limits(deck):
    return {field: copy.deepcopy(deck.get(field)) for field in LIMIT_FIELDS}


def save_deck_names(col, data_dir):
    """Normal deck names for the panel's deck picker; refreshed after every sync."""
    names = sorted(item.name for item in col.decks.all_names_and_ids(
        skip_empty_default=True, include_filtered=False))
    write_json(data_dir / "decks.json", names)


def today_plan(report, proposals):
    """What the panel and history show as today's allowance."""
    names = [deck["name"] for deck in proposals]
    rows = [{"deck": deck["name"], "limit": deck["newLimitToday"]["limit"],
             "root": not any(deck["name"].startswith(name + "::") for name in names)}
            for deck in proposals]
    return {"new_today": sum(row["limit"] for row in rows if row["root"]), "decks": rows,
            "due_cards": report.plan.due_cards, "due_minutes": round(report.plan.due_minutes, 1),
            "minutes": report.plan.today_minutes, "pace": report.plan.weekly_new,
            "pace_reason": report.plan.weekly_reason}


def ours(deck, entry):
    """Limits this controller may overwrite.

    Studying offline rewrites the whole deck, so a phone that has not pulled the
    latest plan uploads an older copy of our limits. Base 0 is always ours; only a
    non-zero base limit is a deliberate edit that stops the controller.
    """
    return limits(deck) in (entry["applied"], entry.get("pending")) or deck.get("newLimit") == 0


def prepare(col, settings, state):
    """Compute a bounded, same-day non-increasing allowance, including parent caps."""
    decks = selected_decks(col, settings["decks"])
    current_ids = {str(deck["id"]) for deck in decks}
    managed = state.setdefault("managed", {})
    if set(managed) - current_ids:
        raise WorkloadError("Managed deck left the selected scope. Restore before changing scope")
    for deck in decks:
        key = str(deck["id"])
        if key in managed:
            if limits(deck) != managed[key]["applied"]:
                raise WorkloadError("New-card limits changed outside Workload. Restore or resolve manually")
        else:
            managed[key] = {"original": limits(deck), "applied": limits(deck),
                            "weight": snapshot._deck_limits(col, deck["id"])["new_per_day"]}

    # New cards in filtered decks may bypass ordinary deck limits.
    ids = ",".join("?" for _ in decks)
    if col.db.scalar(f"select count() from cards where odid in ({ids}) and type = 0",
                     *(deck["id"] for deck in decks)):
        raise WorkloadError("Return new cards from filtered decks before running the controller")
    data = snapshot.build_snapshot(col, settings)
    weights = {deck["name"]: max(0, managed[str(deck["id"])]["weight"]) for deck in decks}
    for row in data["decks"]:
        row["new_per_day"] = weights[row["name"]]
    if data["today"] != dt.date.today():
        raise WorkloadError("Run after Anki's day boundary; check TZ and run_at")
    # Native per-deck counters also cover reintroduced cards after a reset.
    day = col.sched.today
    roots = [deck for deck in decks if not any(
        deck["name"].startswith(parent["name"] + "::") for parent in decks)]
    done_today = sum(max(0, deck["newToday"][1]) for deck in roots if deck["newToday"][0] == day)
    today_data = data["study_days"].setdefault(data["today"].isoformat(), {})
    today_data["new"] = max(done_today, today_data.get("new", 0))
    report = logic.analyze(data, settings)
    # Rotate ties so a small total does not always favour the first deck.
    rows = report.decks
    offset = day % len(rows) if rows else 0
    ordered = rows[offset:] + rows[:offset]
    shares = logic.scale_limits(
        {row.name: min(row.new_left, weights[row.name]) for row in ordered},
        report.plan.new_remaining, settings.get("split_strategy", "proportional"))
    proposals = []
    daily = state.get("daily", {}) if state.get("day") == day else {}
    for deck in decks:
        key = str(deck["id"])
        additional = sum(value for name, value in shares.items()
                         if name == deck["name"] or name.startswith(deck["name"] + "::"))
        count_day, count = deck["newToday"]
        done = max(0, count) if count_day == day else 0
        cap = done + additional
        if key in daily:
            cap = min(cap, daily[key])
        daily[key] = cap
        updated = copy.deepcopy(deck)
        updated["newLimit"] = 0  # outage tomorrow -> no new allowance
        updated["newLimitToday"] = {"today": day, "limit": cap}
        proposals.append(updated)
    state["day"], state["daily"] = day, daily
    return proposals, report


def initialize(data_dir, identity):
    from anki.collection import Collection
    path = data_dir / "collection.anki2"
    if path.exists() or (data_dir / "state.json").exists():
        raise WorkloadError("Initialization requires a fresh private client volume")
    with tempfile.TemporaryDirectory(dir=data_dir) as folder:
        replica = Path(folder) / "collection.anki2"
        col = Collection(str(replica))
        try:
            auth = get_auth(col, data_dir, identity, login=True)
            accept_endpoint(col.sync_status(auth), auth)
            save_auth(data_dir, identity, auth)
            col.close_for_full_sync()
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
            col.reopen(after_full_sync=True)
            if col.is_empty():
                raise WorkloadError("Remote collection is empty; sync your cards from an app first")
            save_deck_names(col, data_dir)
        finally:
            col.close()
        clone_database(replica, path)
    write_json(data_dir / "identity.json", identity)
    print("Private replica downloaded. No limits changed.", flush=True)


def download_replica(data_dir, identity, state, event):
    """Replace only this client's replica, after backup and limit validation."""
    from anki.collection import Collection
    write_json(data_dir / "intervention.json", {"error": "Pobieranie kolekcji wymaga zakończenia sukcesem; sprawdź historię."})
    backup = Path(tempfile.mkdtemp(prefix="before-download-", dir=data_dir))
    clone_database(data_dir / "collection.anki2", backup / "collection.anki2")
    write_json(backup / "state.json", state)
    event["backup"] = backup.name
    with tempfile.TemporaryDirectory(dir=data_dir) as folder:
        replica = Path(folder) / "collection.anki2"
        col = Collection(str(replica))
        try:
            auth = get_auth(col, data_dir, identity)
            accept_endpoint(col.sync_status(auth), auth)
            save_auth(data_dir, identity, auth)
            col.close_for_full_sync()
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
            col.reopen(after_full_sync=True)
            if col.is_empty():
                raise WorkloadError("Remote collection is empty; download rejected")
            for key, entry in state.get("managed", {}).items():
                deck = col.decks.get(int(key), default=False)
                if not deck or not ours(deck, entry):
                    raise WorkloadError("Downloaded limits differ from Workload state; resolve limits manually")
            save_deck_names(col, data_dir)
        finally:
            col.close()
        destination = data_dir / "replica.tmp"
        clone_database(replica, destination)
        destination.replace(data_dir / "collection.anki2")
    (data_dir / "intervention.json").unlink(missing_ok=True)
    event["reason"] = "Pobrano kolekcję z serwera. Kopia bezpieczeństwa: " + backup.name


def _run(data_dir, command, event):
    from anki.collection import Collection
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkloadError("Another Workload process is running") from None
        identity = read_json(data_dir / "identity.json")
        if command == "init":
            endpoint, username = credentials()
            initialize(data_dir, {"endpoint": endpoint, "username": username})
            return
        if identity is None:
            raise WorkloadError("Najpierw połącz konto Anki")
        apply = command == "restore"
        if command == "run":
            # Read under the lock, so a change saved meanwhile (e.g. apply off) is obeyed.
            settings = load_settings(data_dir)
            event["apply"] = apply = settings["apply"]
            if not settings["decks"]:
                raise WorkloadError("Wybierz talie w panelu")
        state_path = data_dir / "state.json"
        state = read_json(state_path, {"managed": {}})
        if command == "download":
            download_replica(data_dir, identity, state, event)
            return
        with tempfile.TemporaryDirectory(dir=data_dir) as folder:
            replica = Path(folder) / "collection.anki2"
            clone_database(data_dir / "collection.anki2", replica)
            col = Collection(str(replica))
            try:
                auth = get_auth(col, data_dir, identity, login=command == "login")
                if command == "login":
                    print("Token refreshed.", flush=True)
                    return
                sync_normal(col, auth)
                save_auth(data_dir, identity, auth)
                save_deck_names(col, data_dir)
                for key, entry in state["managed"].items():
                    deck = col.decks.get(int(key), default=False)
                    if deck and ours(deck, entry):
                        entry["applied"] = limits(deck)
                        entry.pop("pending", None)
                if command == "restore":
                    proposals = []
                    for key, entry in state["managed"].items():
                        deck = col.decks.get(int(key), default=False)
                        if not deck or limits(deck) != entry["applied"]:
                            raise WorkloadError("Restore stopped: deck missing or limits edited outside Workload")
                        deck.update(entry["original"])
                        proposals.append(deck)
                else:
                    proposals, report = prepare(col, settings, state)
                    print(json.dumps({"apply": apply, "day": dt.date.today().isoformat(), "minutes": report.plan.today_minutes,
                                      "new_remaining": report.plan.new_remaining,
                                      "card_costs": report.card_costs,
                                      "reason": report.plan.reason,
                                      "pace_reason": report.plan.weekly_reason, "limits": [
                        {"deck": deck["name"], **limits(deck)} for deck in proposals
                    ]}, ensure_ascii=False), flush=True)
                event["changes"] = [{"deck": deck["name"],
                    "before": limits(col.decks.get(deck["id"], default=False)), "after": limits(deck)}
                    for deck in proposals
                    if limits(col.decks.get(deck["id"], default=False)) != limits(deck)]
                if command != "restore":
                    event["reason"] = report.plan.reason
                    event["card_costs"] = report.card_costs
                    event["plan"] = today_plan(report, proposals)
                if apply:
                    # Reserve same-day caps BEFORE attempting the remote write. A failed
                    # upload must never result in a larger allowance on retry.
                    for deck in proposals:
                        state["managed"][str(deck["id"])]["pending"] = limits(deck)
                    write_json(state_path, state)
                    for deck in proposals:
                        if limits(col.decks.get(deck["id"], default=False)) != limits(deck):
                            col.decks.update_dict(deck)
                    sync_normal(col, auth)
                    save_auth(data_dir, identity, auth)
                    if any(limits(col.decks.get(deck["id"], default=False)) != limits(deck)
                           for deck in proposals):
                        raise WorkloadError("Sync conflict: limits differ from the proposed values")
                    for entry in state["managed"].values():
                        entry["applied"] = entry.pop("pending")
                    if command == "restore":
                        state = {"managed": {}}
                    state["last_success"] = dt.date.today().isoformat()
                    write_json(state_path, state)
            except FullSyncRequired as error:
                write_json(data_dir / "intervention.json", {"error": str(error)})
                raise
            finally:
                col.close()
            # Only successful runs replace the durable replica. Failed runs discard
            # local pending changes instead of uploading yesterday's plan on retry.
            destination = data_dir / "replica.tmp"
            clone_database(replica, destination)
            destination.replace(data_dir / "collection.anki2")
            (data_dir / "intervention.json").unlink(missing_ok=True)
        if not apply:
            print("Dry run: no limit changes uploaded.", flush=True)


def run(data_dir, command):
    event = {"started": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
             "command": command, "apply": command == "restore", "status": "running", "changes": []}
    try:
        _run(data_dir, command, event)
        event["status"] = "success"
    except Exception as error:
        event["status"] = "error"
        event["error"] = str(error) if isinstance(error, WorkloadError) else type(error).__name__
        raise
    finally:
        event["finished"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "history.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            history = read_json(data_dir / "history.json", [])
            incident_path = data_dir / "notification_state.json"
            incident = read_json(incident_path)
            # Seed from old history when upgrading an already failing service.
            if incident is None:
                incident = {}
                for previous in reversed(history):
                    if previous.get("command") not in ("run", "restore"):
                        continue
                    if previous.get("status") == "success":
                        break
                    if previous.get("email") == "sent":
                        incident = {"error": previous.get("error")}
                        break
            try:
                try:
                    from .notifications import send_summary
                except ImportError:
                    from notifications import send_summary
                if command in ("run", "restore") and event["status"] == "error" and incident.get("error") == event["error"]:
                    event["email"] = "suppressed_duplicate"
                else:
                    event["email"] = send_summary(read_json(data_dir / "mail.json", {}), event)
                if command in ("run", "restore"):
                    if event["status"] == "success":
                        incident = {}
                    elif event["email"] == "sent":
                        incident = {"error": event["error"]}
            except Exception as error:
                # SMTP failure must not retry an already successful collection mutation.
                event["email"] = "error: " + type(error).__name__
                if command in ("run", "restore") and event["status"] == "success":
                    incident = {}
            write_json(incident_path, incident)
            # ponytail: retain 200 runs; use SQLite if searchable long-term history is needed.
            write_json(data_dir / "history.json", (history + [event])[-200:])


def main():
    os.umask(0o077)
    os.environ.setdefault("TZ", "Europe/Warsaw")
    time.tzset()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "login", "run", "serve", "restore", "download", "dashboard"))
    parser.add_argument("--data", type=Path, default=Path("/data/user_files"))
    args = parser.parse_args()
    data = args.data.resolve()
    if args.command == "dashboard":
        from dashboard import serve
        serve(data)
        return
    if args.command != "serve":
        run(data, args.command)
        return
    last_run = None
    while True:
        try:
            settings = load_settings(data)
        except WorkloadError as error:
            print(error, flush=True)
            settings = None
        # Not configured yet, or waiting for a manual download after a full-sync request.
        if (not settings or not settings["decks"] or not (data / "identity.json").exists()
                or (data / "intervention.json").exists()):
            time.sleep(30)
            continue
        now = dt.datetime.now()
        stored = read_json(data / "state.json", {})
        today = now.date().isoformat()
        already = stored.get("last_success") == today if settings["apply"] else last_run == today
        if not already and now.strftime("%H:%M") >= settings["run_at"]:
            try:
                run(data, "run")
                last_run = today
            except Exception as error:
                print(str(error) if isinstance(error, WorkloadError) else type(error).__name__, flush=True)
                time.sleep(300)
        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Backend errors may contain request details; never log credentials.
        print(str(error) if isinstance(error, WorkloadError) else type(error).__name__, file=sys.stderr)
        sys.exit(1)
