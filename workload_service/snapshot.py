"""Odczyt kolekcji dla usługi Workload; bez zapisów."""

import datetime

# Typy revlog: 0 = nauka, 1 = powtórka, 2 = przeuczenie, 3 = talia filtrowana,
# 4 = ręczna zmiana, 5 = przeplanowanie. Do czasów i liczników bierzemy 0-3.
_SECONDS_WINDOW_DAYS = 30


# ── Odczyt kolekcji ────────────────────────────────────────────────────────

def _deck_limits(col, did):
    """Efektywny limit nowych: „Ta talia” ma pierwszeństwo nad presetem."""
    new_per_day = (col.decks.get(did) or {}).get("newLimit")
    if new_per_day is None:
        new_per_day = col.decks.config_dict_for_deck_id(did).get("new", {}).get("perDay", 0)
    return {"new_per_day": int(new_per_day)}


def _card_data(col, deck_ids):
    """Zapas nowych kart, terminy i nauka rozpoczętych kart, per talia."""
    today = col.sched.today
    empty = {did: 0 for did in deck_ids}
    new_left = dict(empty)
    due_counts = {did: {} for did in deck_ids}
    learning = dict(empty)
    # odid wskazuje talię macierzystą karty wyciągniętej do talii filtrowanej;
    # jej `due` jest wtedy pozycją w tej talii (bywa ujemne), a prawdziwy
    # termin leży w `odue`.
    for did, odid, queue, card_type, due, odue in col.db.all(
        "select did, odid, queue, type, due, odue from cards where queue != -1"
    ):
        home = odid or did
        if home not in new_left:
            continue
        if odid and odue:
            due = odue
        if queue == 0 or (queue in (-2, -3) and card_type == 0):
            new_left[home] += 1  # zakopane nowe karty wrócą, więc liczą się do zapasu
        elif queue == 1:
            learning[home] += 1
        elif queue in (2, 3):  # tylko tu `due` jest numerem dnia, nie znacznikiem czasu
            offset = int(due) - today
            if queue == 3 and offset <= 0:
                # Nauka międzydniowa na dziś kosztuje jak nauka, nie jak powtórka.
                learning[home] += 1
            else:
                counts = due_counts[home]
                counts[offset] = counts.get(offset, 0) + 1
    return new_left, due_counts, learning


def _revlog_data(col, deck_ids):
    """Historia wybranego zakresu, według bieżącej granicy dnia Anki."""
    cutoff = col.sched.day_cutoff * 1000
    date = (datetime.datetime.fromtimestamp(col.sched.day_cutoff)
            - datetime.timedelta(days=1)).date()
    selected = ",".join("?" for _ in deck_ids) or "NULL"
    rows = col.db.all(
        "select r.id, r.cid, r.type, r.time, r.ease from revlog r join cards c on c.id = r.cid "
        f"where (case when c.odid != 0 then c.odid else c.did end) in ({selected}) "
        "and r.type in (0,1,2,3) and r.id < ? order by r.id",
        *deck_ids, cutoff,
    )
    learn_seconds, review_seconds = [], []
    active_days, introduced = set(), set()
    study_days = {}
    first_seen, recent_costs = {}, {}
    learn_answers = 0
    for stamp, cid, kind, milliseconds, ease in rows:
        offset = int((cutoff - 1 - stamp) // 86400000)
        active_days.add(offset)
        seconds = max(0, milliseconds) / 1000
        if offset < _SECONDS_WINDOW_DAYS and seconds > 0:
            (learn_seconds if kind == 0 else review_seconds).append(seconds)
        first_seen.setdefault(cid, (kind, offset))
        if 1 <= offset <= 7:
            cost = recent_costs.setdefault(cid, {"cid": cid, "seconds": 0, "answers": 0, "again": 0})
            cost["seconds"] += seconds
            cost["answers"] += 1
            cost["again"] += int(ease == 1)
        first = kind == 0 and cid not in introduced
        if kind == 0:
            learn_answers += 1
            introduced.add(cid)
        if offset < _SECONDS_WINDOW_DAYS:
            key = (date - datetime.timedelta(days=offset)).isoformat()
            entry = study_days.setdefault(key, {"seconds": 0, "answers": 0, "new": 0,
                                               "again": 0, "learning_seconds": 0})
            entry["seconds"] += seconds
            entry["answers"] += 1
            entry["new"] += int(first)
            entry["again"] += int(ease == 1)
            if kind in (0, 2):
                entry["learning_seconds"] += seconds
    cohort = {cid for cid, (kind, offset) in first_seen.items() if kind == 0 and 1 <= offset <= 14}
    for cid, cost in recent_costs.items():
        cost["recent"] = cid in cohort
    cohort_seconds = sum(cost["seconds"] for cid, cost in recent_costs.items() if cid in cohort)
    total_seconds = sum(cost["seconds"] for cost in recent_costs.values())
    top = sorted(recent_costs.values(), key=lambda cost: (-cost["seconds"], cost["cid"]))[:5]
    return {
        "card_costs": {"cohort_cards": len(cohort), "cohort_seconds": cohort_seconds,
                       "total_seconds": total_seconds,
                       "top": [cost for cost in top if cost["seconds"] > 0]},
        "today": date,
        "learn_seconds": learn_seconds,
        "review_seconds": review_seconds,
        "active_days": len(active_days),
        "study_days": study_days,
        "new_introduced": len(introduced),
        "learn_answers": learn_answers,
    }


def build_snapshot(col, settings):
    wanted = [name.strip() for name in settings.get("decks", []) if name.strip()]
    decks = []
    for item in col.decks.all_names_and_ids(skip_empty_default=True):
        deck = col.decks.get(item.id) or {}
        if deck.get("dyn"):  # talie filtrowane nie mają własnego dopływu
            continue
        if wanted and not any(item.name == n or item.name.startswith(n + "::") for n in wanted):
            continue
        decks.append({"id": item.id, "name": item.name})

    deck_ids = [deck["id"] for deck in decks]
    new_left, due_counts, learning = _card_data(col, deck_ids)
    with_cards = {
        deck["name"] for deck in decks if new_left[deck["id"]] or due_counts[deck["id"]] or learning[deck["id"]]
    }
    # Talia bez własnych kart zostaje w raporcie tylko jako przodek talii z
    # kartami — jej preset obowiązuje przy „limitach od góry”.
    kept = with_cards | {name.rsplit("::", depth)[0]
                         for name in with_cards for depth in range(1, name.count("::") + 1)}

    rows = []
    for deck in decks:
        if deck["name"] not in kept:
            continue
        row = {"name": deck["name"], **_deck_limits(col, deck["id"])}
        row.update({
            "new_left": new_left[deck["id"]],
            "due_counts": due_counts[deck["id"]],
        })
        rows.append(row)

    snapshot = {
        "decks": rows,
        "learning_cards": sum(learning.values()),
    }
    snapshot.update(_revlog_data(col, deck_ids))
    return snapshot


