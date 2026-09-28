"""Czysta logika planu: bez importów Anki, w pełni testowalna.

Wejściem jest migawka kolekcji (słownik z `snapshot.build_snapshot`), wyjściem
raport z planem na dziś. Plan jest ostrożny: najpierw należne powtórki i nauka
rozpoczętych kart, nowe karty tylko z zapasu czasu.
"""

import dataclasses
import datetime
from typing import Any, Dict, List, Optional, Sequence

# Zapasowe stałe, gdy historia jest za krótka, by cokolwiek zmierzyć.
DEFAULT_REVIEW_SECONDS = 9.0
DEFAULT_LEARN_SECONDS = 12.0
# Ile odpowiedzi kosztuje nowa karta w dniu wprowadzenia (kroki nauki 1 min/10 min).
DEFAULT_LEARN_ANSWERS_PER_NEW_CARD = 2.5

SPLIT_PROPORTIONAL = "proportional"
SPLIT_HEAVIEST_FIRST = "heaviest_first"


@dataclasses.dataclass
class DeckRow:
    name: str
    new_per_day: int
    new_left: int
    due_today: int


@dataclasses.dataclass
class StudyPlan:
    today_minutes: int
    due_cards: int
    due_minutes: float
    new_done: int
    new_remaining: int
    weekly_new: int
    reason: str
    weekly_reason: str


@dataclasses.dataclass
class Report:
    minutes_per_day: int
    review_seconds: float
    learn_seconds: float
    learn_answers_per_new_card: float
    new_left_total: int
    backlog: int
    decks: List[DeckRow]
    plan: Optional[StudyPlan] = None
    card_costs: Dict[str, Any] = dataclasses.field(default_factory=dict)


def median(values: Sequence[float]):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def new_card_cost(learn_answers_per_new_card: float, learn_seconds: float) -> float:
    """Sekundy, które kosztuje jedna nowa karta w dniu wprowadzenia."""
    return max(0.0, learn_answers_per_new_card * learn_seconds)


def _measured(override, value, fallback) -> float:
    """Wartość z ustawień, gdy dodatnia; inaczej pomiar z historii albo stała."""
    if float(override or 0) > 0:
        return float(override)
    return value if value is not None and value > 0 else fallback


# ── Podział porcji między talie ────────────────────────────────────────────

def scale_limits(limits: Dict[str, int], target_total: int,
                 strategy: str = SPLIT_PROPORTIONAL) -> Dict[str, int]:
    """Obniża limity nowych kart do sumy `target_total`. Zero jest dozwolone.

    `proportional` zachowuje proporcje talii, `heaviest_first` ścina najpierw
    największy limit, więc małe talie zostają nietknięte.
    """
    active = {name: value for name, value in limits.items() if value > 0}
    if not active:
        return {}
    target_total = max(0, min(target_total, sum(active.values())))
    if strategy == SPLIT_HEAVIEST_FIRST:
        result = dict(active)
        while sum(result.values()) > target_total:
            # Przy równych wartościach alfabetycznie — wynik musi być powtarzalny.
            result[sorted(result, key=lambda key: (-result[key], key))[0]] -= 1
        return result
    current_total = sum(active.values())
    exact = {name: value * target_total / current_total for name, value in active.items()}
    scaled = {name: int(value) for name, value in exact.items()}
    # Reszta metodą największych ułamków, żeby suma trafiła dokładnie w cel.
    missing = target_total - sum(scaled.values())
    for name in sorted(active, key=lambda name: exact[name] - int(exact[name]), reverse=True)[:missing]:
        scaled[name] += 1
    return scaled


# ── Główna analiza ─────────────────────────────────────────────────────────

def analyze(snapshot: Dict[str, Any], settings: Dict[str, Any]) -> Report:
    per_card = None
    if snapshot.get("learn_answers", 0) > 0 and snapshot.get("new_introduced", 0) > 0:
        per_card = snapshot["learn_answers"] / snapshot["new_introduced"]
    learn_answers = _measured(settings.get("learn_answers_per_new_card"), per_card,
                              DEFAULT_LEARN_ANSWERS_PER_NEW_CARD)
    rows = [DeckRow(name=deck["name"], new_per_day=int(deck.get("new_per_day", 0)),
                    new_left=int(deck.get("new_left", 0)),
                    due_today=sum(int(count) for offset, count in (deck.get("due_counts") or {}).items()
                                  if int(offset) <= 0))
            for deck in snapshot.get("decks", [])]
    report = Report(
        minutes_per_day=max(1, int(settings.get("minutes_per_day", 15))),
        review_seconds=_measured(settings.get("seconds_per_card"),
                                 median(snapshot.get("review_seconds", [])), DEFAULT_REVIEW_SECONDS),
        learn_seconds=_measured(settings.get("learn_seconds_per_card"),
                                median(snapshot.get("learn_seconds", [])), DEFAULT_LEARN_SECONDS),
        learn_answers_per_new_card=learn_answers,
        new_left_total=sum(row.new_left for row in rows),
        backlog=sum(int(count) for deck in snapshot.get("decks", [])
                    for offset, count in (deck.get("due_counts") or {}).items() if int(offset) < 0),
        decks=rows,
        card_costs=snapshot.get("card_costs", {}),
    )
    report.plan = study_plan(snapshot, settings, report)
    weights = {row.name: min(row.new_left, max(0, row.new_per_day)) for row in rows if row.new_left > 0}
    report.plan.new_remaining = sum(scale_limits(
        weights, report.plan.new_remaining, settings.get("split_strategy", SPLIT_PROPORTIONAL)).values())
    return report


def study_plan(snapshot, settings, report) -> StudyPlan:
    """Ostrożna porcja na dziś. Dłuższy dzień nie podnosi dopływu."""
    normal = report.minutes_per_day
    maximum = max(normal, int(settings.get("max_minutes_per_day", 30)))
    pace = max(0, int(settings.get("new_cards_per_day", 3)))
    history = snapshot.get("study_days", {})
    today = snapshot.get("today", datetime.date.today())
    current = history.get(today.isoformat(), {})
    spent = current.get("seconds", 0) / 60
    new_done = current.get("new", 0)
    due = sum(row.due_today for row in report.decks)
    learning = snapshot.get("learning_cards", 0)
    cost = new_card_cost(report.learn_answers_per_new_card, report.learn_seconds)
    due_minutes = (due * report.review_seconds + learning * cost) / 60
    due += learning

    # ponytail: dwa pełne tygodnie i próg 80% to heurystyka; symulator FSRS
    # jest właściwym miejscem na modelowanie przyszłego kosztu kart.
    monday = today - datetime.timedelta(days=today.weekday())
    weeks = [[history.get((monday - datetime.timedelta(days=offset + day)).isoformat(), {})
              for day in range(1, 8)] for offset in (7, 0)]
    recent = [history.get((today - datetime.timedelta(days=day)).isoformat(), {})
              for day in range(1, 8)]
    active = [day for day in recent if day.get("answers", 0) > 0]
    answers = sum(day.get("answers", 0) for day in recent)
    again = sum(day.get("again", 0) for day in recent)
    weekly = pace
    weekly_reason = "Utrzymaj spokojne tempo. Zwiększenie nie jest obowiązkiem."
    if report.backlog:
        weekly = 0
        weekly_reason = "Wstrzymaj nowe karty, aż odrobisz zaległości. Nie musisz nadrabiać wszystkiego dziś."
    elif due_minutes >= maximum * 0.8:
        weekly = 0
        weekly_reason = "Obecna kolejka zajmuje zwykły czas z zapasem. Na razie bez nowych kart."
    elif not active and snapshot.get("active_days", 0):
        weekly = min(pace, 3)
        weekly_reason = "Wracasz po przerwie: zacznij spokojnie, bez nadrabiania nowych kart."
    elif answers >= 20 and again / answers >= 0.3:
        weekly = 0 if again / answers >= 0.5 else max(0, pace - 1)
        weekly_reason = (
            f"W ostatnich 7 dniach „Ponownie” stanowiło {round(100 * again / answers)}% odpowiedzi. "
            "Nowe słówka mogą poczekać — daj czas kartom, które już wracają."
        )
    elif any(day.get("seconds", 0) > maximum * 60 for day in recent):
        weekly = max(0, pace - 1)
        weekly_reason = "W ostatnim tygodniu nauka przekroczyła górną granicę czasu. Proponuję mniej nowych kart."
    elif pace and all(
        sum(day.get("answers", 0) > 0 for day in week) >= 5
        and sum(day.get("new", 0) for day in week) >= pace * sum(
            day.get("answers", 0) > 0 for day in week)
        and all((not day.get("answers", 0) or 0 < day.get("seconds", 0) <= normal * 60 * 0.8)
                and day.get("new", 0) <= pace for day in week)
        and sum(day.get("again", 0) for day in week) <= 0.2 * sum(
            day.get("answers", 0) for day in week)
        for week in weeks
    ):
        weekly = pace + 1
        weekly_reason = (
            "Dwa pełne tygodnie mieściły się w czasie z zapasem. Jeśli kończyłeś należne "
            "powtórki, możesz rozważyć +1 nową kartę dziennie w ustawieniach."
        )
    elif not any(day.get("answers", 0) for week in weeks for day in week):
        weekly_reason = "Spokojny start. Najpierw poznaj swój rytm; nie zwiększaj tempa na zapas."

    room = max(0, int((normal * 0.8 - spent - due_minutes) * 60 / max(1, cost)))
    remaining = min(max(0, min(pace, weekly) - new_done), room, report.new_left_total)
    reason = "Najpierw zakończ należne powtórki i naukę rozpoczętych kart. Nowe tylko, jeśli zostanie czas."
    if report.backlog:
        remaining = 0
        reason = "Najpierw spokojny powrót do powtórek. Zaległości nie wymagają restartu talii."
    elif spent + due_minutes >= normal * 0.8:
        reason = "Zostaw zapas czasu. Dziś skup się na powtórkach i rozpoczętych kartach."
    elif new_done >= min(pace, weekly):
        reason = "Na dziś wystarczy nowych kart. Dodatkowy czas nie zwiększa tempa na kolejne dni."
    elif report.new_left_total == 0:
        reason = "Nie ma nowych kart w wybranych taliach. Spokojnie kontynuuj powtórki."
    return StudyPlan(normal, due, due_minutes, new_done, remaining, weekly, reason, weekly_reason)
