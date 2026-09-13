"""Czysta logika raportu obciążenia: bez importów Anki i Qt, w pełni testowalna.

Wejściem jest migawka kolekcji (zwykły słownik, patrz `analyze`), wyjściem raport
z liczbami i listą uwag. Dodatek nigdy nie zapisuje nic do kolekcji — proponuje
wartości, które użytkownik wpisuje sam w Opcjach talii.

Dwie wielkości opisują obciążenie i nie należy ich mieszać:

- `structural_load` — ile powtórek dziennie generują karty, które już masz.
  Suma odwrotności interwałów: karta z interwałem 10 dni kosztuje 0,1 powtórki
  na dzień przy stałym interwale. To przybliżenie, nie prognoza schedulera.
- `steady_state` — ile powtórek dziennie da dopływ nowych kart, gdy zapas się
  rozejdzie. To projekcja przez współczynnik „powtórek na nową kartę”, więc
  raport zawsze podaje, skąd ten współczynnik pochodzi.
"""

import dataclasses
import datetime
import math
from html import escape
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Zapasowe stałe używane, gdy historia powtórek jest za krótka, by cokolwiek zmierzyć.
DEFAULT_REVIEW_SECONDS = 9.0
DEFAULT_LEARN_SECONDS = 12.0
# Ile odpowiedzi kosztuje nowa karta w dniu wprowadzenia (kroki nauki 1 min/10 min).
DEFAULT_LEARN_ANSWERS_PER_NEW_CARD = 2.5
# Reguła z manuala Anki: 20 nowych kart dziennie daje około 200 powtórek dziennie.
DEFAULT_REVIEWS_PER_NEW_CARD = 10.0
# Minimalna historia dla opisowego ilorazu. Nawet długa historia nie
# czyni go modelem przyszłego kosztu nowych kart.
MIN_ACTIVE_DAYS_FOR_RATIO = 60
# Tyle dni z faktyczną nauką wystarczy, by liczyć trend dziennej liczby powtórek.
MIN_ACTIVE_DAYS_FOR_TREND = 10
# Trend poniżej tego nachylenia to szum, nie wzrost.
MIN_TREND_SLOPE = 0.2

SPLIT_PROPORTIONAL = "proportional"
SPLIT_HEAVIEST_FIRST = "heaviest_first"


@dataclasses.dataclass
class Finding:
    level: str  # "alert" | "warn" | "info" | "ok"
    title: str
    detail: str


@dataclasses.dataclass
class DeckRow:
    name: str
    preset: str
    new_per_day: int
    review_per_day: int
    new_left: int
    review_cards: int
    structural_load: float
    due_today: int
    is_root: bool
    suggested_new_per_day: Optional[int] = None
    suggested_review_per_day: Optional[int] = None


@dataclasses.dataclass
class Trend:
    slope: Optional[float]  # zmiana liczby powtórek na dzień
    level: Optional[float]  # średnia z ostatniego tygodnia
    days_to_ceiling: Optional[int]
    date_of_ceiling: Optional[datetime.date]


@dataclasses.dataclass
class StudyPlan:
    today_minutes: int
    spent_minutes: float
    due_cards: int
    due_minutes: float
    new_done: int
    new_remaining: int
    weekly_new: int
    reason: str
    weekly_reason: str
    recent_minutes: float
    active_days: int
    max_minutes: int
    again_percent: Optional[int]
    learning_minutes: float


@dataclasses.dataclass
class Report:
    minutes_per_day: int
    review_seconds: float
    review_seconds_source: str
    learn_seconds: float
    learn_seconds_source: str
    learn_answers_per_new_card: float
    learn_answers_source: str
    reviews_per_new_card: float
    ratio_source: str
    ceiling: int
    new_total: int
    structural_load: int
    structural_minutes: int
    steady_state: int
    steady_state_minutes: int
    new_left_total: int
    backlog: int
    peak: Optional[Tuple[int, int]]
    forecast: List[Tuple[int, int]]
    trend: Trend
    decks: List[DeckRow]
    roots: List[str]
    findings: List[Finding]
    plan: Optional[StudyPlan] = None


# ── Pomocnicze ─────────────────────────────────────────────────────────────

def plural(count: float, one: str, few: str, many: str) -> str:
    """Polska odmiana liczebnika: 1 karta, 2 karty, 5 kart."""
    number = int(round(count))
    if number == 1:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


def reviews(count: float) -> str:
    return f"{int(round(count))} {plural(count, 'powtórka', 'powtórki', 'powtórek')}"


def cards(count: float) -> str:
    return f"{int(round(count))} {plural(count, 'karta', 'karty', 'kart')}"


def days(count: float) -> str:
    return f"{int(round(count))} {plural(count, 'dzień', 'dni', 'dni')}"


def new_cards(count: float) -> str:
    return f"{int(round(count))} {plural(count, 'nowa karta', 'nowe karty', 'nowych kart')}"


def ancestors(name: str) -> List[str]:
    """Nazwy talii nadrzędnych dla „a::b::c”: „a” i „a::b”."""
    parts = name.split("::")
    return ["::".join(parts[:index]) for index in range(1, len(parts))]


def median(values: Sequence[float]) -> Optional[float]:
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def linear_slope(points: Sequence[Tuple[float, float]]) -> Optional[float]:
    """Nachylenie prostej najmniejszych kwadratów; None przy zbyt małej próbce."""
    if len(points) < 3:
        return None
    n = float(len(points))
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


# ── Czas: budżet, sufit i dopływ ───────────────────────────────────────────

def new_card_cost(learn_answers_per_new_card: float, learn_seconds: float) -> float:
    """Sekundy, które kosztuje jedna nowa karta w dniu wprowadzenia."""
    return max(0.0, learn_answers_per_new_card * learn_seconds)


def ceiling_from_minutes(
    minutes: int,
    review_seconds: float,
    new_per_day: int = 0,
    learn_answers_per_new_card: float = 0.0,
    learn_seconds: float = 0.0,
) -> int:
    """Ile powtórek dziennie zmieści się w czasie, który zostaje po nowych kartach.

    Nowe karty nie są darmowe: przy krokach nauki każda kosztuje kilka odpowiedzi
    tego samego dnia. Ten czas odejmujemy od budżetu, zanim policzymy sufit.
    """
    if minutes <= 0 or review_seconds <= 0:
        return 0
    budget = minutes * 60 - new_per_day * new_card_cost(
        learn_answers_per_new_card, learn_seconds
    )
    if budget <= 0:
        return 0
    return max(1, int(budget / review_seconds))


def steady_state_reviews(new_per_day: int, reviews_per_new_card: float) -> int:
    """Liczba powtórek dziennie, do której dojdzie nauka przy stałym dopływie."""
    return max(0, int(round(new_per_day * reviews_per_new_card)))


def structural_load(reciprocal_sum: float) -> float:
    """Powtórki dziennie generowane przez karty, które już są w kolekcji."""
    return max(0.0, reciprocal_sum)


# ── Podział limitów między talie ───────────────────────────────────────────

def scale_limits(
    limits: Dict[str, int], target_total: int, strategy: str = SPLIT_PROPORTIONAL
) -> Dict[str, int]:
    """Obniża limity nowych kart do sumy `target_total`.

    `proportional` zachowuje wzajemne proporcje talii. `heaviest_first` ścina
    najpierw talię z największym limitem, więc małe talie zostają nietknięte.
    Zero jest dozwolone: mały budżet nie może wymuszać nowych kart.
    """
    active = {name: value for name, value in limits.items() if value > 0}
    if not active:
        return {}
    target_total = max(0, min(target_total, sum(active.values())))
    if strategy == SPLIT_HEAVIEST_FIRST:
        return _cut_heaviest_first(active, target_total)
    return _scale_proportional(active, target_total)


def _scale_proportional(active: Dict[str, int], target_total: int) -> Dict[str, int]:
    current_total = sum(active.values())
    exact = {name: value * target_total / current_total for name, value in active.items()}
    scaled = {name: int(value) for name, value in exact.items()}
    # Rozdaj resztę metodą największych ułamków, żeby suma trafiła dokładnie w cel.
    missing = target_total - sum(scaled.values())
    if missing > 0:
        order = sorted(active, key=lambda name: exact[name] - int(exact[name]), reverse=True)
        for name in order[:missing]:
            scaled[name] += 1
    return scaled


def _cut_heaviest_first(active: Dict[str, int], target_total: int) -> Dict[str, int]:
    result = dict(active)
    while sum(result.values()) > target_total:
        # Malejąco po wartości, przy równych wartościach alfabetycznie — wynik
        # musi być powtarzalny między uruchomieniami.
        name = sorted(result, key=lambda key: (-result[key], key))[0]
        result[name] -= 1
    return result


# ── Prognoza ───────────────────────────────────────────────────────────────

def merge_due_counts(decks: Sequence[Dict[str, Any]]) -> Dict[int, int]:
    merged: Dict[int, int] = {}
    for deck in decks:
        for offset, count in (deck.get("due_counts") or {}).items():
            merged[int(offset)] = merged.get(int(offset), 0) + int(count)
    return merged


def forecast_from_counts(due_counts: Dict[int, int], days: int) -> List[Tuple[int, int]]:
    """Liczba kart wypadających w każdym z najbliższych `days` dni (0 = dzisiaj).

    Karty zaległe (offset < 0) trafiają do dnia 0, bo czekają już teraz.
    """
    counts = [0] * max(0, days + 1)
    if not counts:
        return []
    for offset, count in due_counts.items():
        index = 0 if offset < 0 else offset
        if index < len(counts):
            counts[index] += count
    return list(enumerate(counts))


def backlog_from_counts(due_counts: Dict[int, int]) -> int:
    return sum(count for offset, count in due_counts.items() if offset < 0)


def cumulative_at(forecast: Sequence[Tuple[int, int]], day: int) -> int:
    return sum(count for offset, count in forecast if offset <= day)


# ── Pomiary z historii ─────────────────────────────────────────────────────

def measured_seconds(
    values: Sequence[float], fallback: float
) -> Tuple[float, str]:
    value = median(values)
    if value is None or value <= 0:
        return fallback, "domyślne"
    return value, "zmierzone"


def measured_learn_answers(
    learn_answers: int, new_introduced: int
) -> Tuple[float, str]:
    if learn_answers > 0 and new_introduced > 0:
        return learn_answers / new_introduced, "zmierzone"
    return DEFAULT_LEARN_ANSWERS_PER_NEW_CARD, "domyślne"


def measured_ratio(
    active_days: int, new_introduced: int, reviews_done: int
) -> Tuple[float, str]:
    if (
        active_days >= MIN_ACTIVE_DAYS_FOR_RATIO
        and new_introduced > 0
        and reviews_done > 0
    ):
        return reviews_done / new_introduced, "zmierzone"
    return DEFAULT_REVIEWS_PER_NEW_CARD, "domyślne"


def measured_trend(
    daily_reviews: Sequence[Tuple[int, int]],
    active_days: int,
    ceiling: int,
    today: Optional[datetime.date] = None,
) -> Trend:
    """Trend dziennej liczby powtórek i data przebicia sufitu.

    `daily_reviews` to pary (numer dnia, liczba powtórek) — dni bez nauki muszą
    być w danych jako zera, inaczej przerwa w nauce wyglądałaby jak spadek.
    """
    if active_days < MIN_ACTIVE_DAYS_FOR_TREND or len(daily_reviews) < 3:
        return Trend(None, None, None, None)
    ordered = sorted(daily_reviews)
    slope = linear_slope([(float(day), float(count)) for day, count in ordered])
    recent = [count for _, count in ordered[-7:]]
    level = sum(recent) / len(recent) if recent else None
    if slope is None or level is None or slope < MIN_TREND_SLOPE or ceiling <= 0:
        return Trend(slope, level, None, None)
    if level >= ceiling:
        return Trend(slope, level, 0, today)
    days = int((ceiling - level) / slope)
    return Trend(slope, level, days, (today + datetime.timedelta(days=days)) if today else None)


# ── Główna analiza ─────────────────────────────────────────────────────────

def analyze(snapshot: Dict[str, Any], settings: Dict[str, Any], today_minutes=None) -> Report:
    """Buduje raport z migawki kolekcji (patrz `__init__.build_snapshot`)."""
    minutes = max(1, int(settings.get("minutes_per_day", 15)))
    active_days = int(snapshot.get("active_days", 0))

    review_seconds, review_source = _override_or_measure(
        settings.get("seconds_per_card"),
        lambda: measured_seconds(snapshot.get("review_seconds", []), DEFAULT_REVIEW_SECONDS),
    )
    learn_seconds, learn_seconds_source = _override_or_measure(
        settings.get("learn_seconds_per_card"),
        lambda: measured_seconds(snapshot.get("learn_seconds", []), DEFAULT_LEARN_SECONDS),
    )
    learn_answers, learn_answers_source = _override_or_measure(
        settings.get("learn_answers_per_new_card"),
        lambda: measured_learn_answers(
            int(snapshot.get("learn_answers", 0)), int(snapshot.get("new_introduced", 0))
        ),
    )
    ratio, ratio_source = _override_or_measure(
        settings.get("reviews_per_new_card"),
        lambda: measured_ratio(
            active_days,
            int(snapshot.get("new_introduced", 0)),
            int(snapshot.get("reviews_done", 0)),
        ),
    )

    rows, roots = _deck_rows(snapshot.get("decks", []))

    # Do sumy dopływu liczą się tylko talie, w których zostały nowe karty —
    # inaczej szeroki limit talii nadrzędnej bez własnych kart zawyża wynik.
    feeding = {row.name: row.new_per_day for row in rows if row.new_left > 0}
    new_total = sum(feeding.values())

    ceiling = ceiling_from_minutes(minutes, review_seconds, new_total, learn_answers, learn_seconds)
    due_counts = merge_due_counts(snapshot.get("decks", []))
    forecast = forecast_from_counts(due_counts, int(settings.get("forecast_days", 60)))
    peak = max(forecast, key=lambda item: item[1]) if forecast else None
    load = structural_load(sum(row.structural_load for row in rows))
    steady = steady_state_reviews(new_total, ratio)
    new_left_total = sum(row.new_left for row in rows)

    report = Report(
        minutes_per_day=minutes,
        review_seconds=review_seconds,
        review_seconds_source=review_source,
        learn_seconds=learn_seconds,
        learn_seconds_source=learn_seconds_source,
        learn_answers_per_new_card=learn_answers,
        learn_answers_source=learn_answers_source,
        reviews_per_new_card=ratio,
        ratio_source=ratio_source,
        ceiling=ceiling,
        new_total=new_total,
        structural_load=int(round(load)),
        structural_minutes=int(round(load * review_seconds / 60)),
        steady_state=steady,
        steady_state_minutes=int(
            round((steady * review_seconds + new_total * new_card_cost(learn_answers, learn_seconds)) / 60)
        ),
        new_left_total=new_left_total,
        backlog=backlog_from_counts(due_counts),
        peak=peak if peak and peak[1] > 0 else None,
        forecast=forecast,
        trend=measured_trend(
            snapshot.get("daily_reviews", []), active_days, ceiling, snapshot.get("today")
        ),
        decks=rows,
        roots=roots,
        findings=[],
    )
    report.plan = study_plan(snapshot, settings, report, today_minutes)
    weights = {row.name: min(row.new_left, max(0, row.new_per_day))
               for row in rows if row.new_left > 0}
    proposal = scale_limits(weights, report.plan.new_remaining,
                            settings.get("split_strategy", SPLIT_PROPORTIONAL))
    report.plan.new_remaining = sum(proposal.values())
    for row in rows:
        row.suggested_new_per_day = proposal.get(row.name, 0)
    report.findings = _findings(report, snapshot)
    return report


def study_plan(snapshot, settings, report, today_minutes=None) -> StudyPlan:
    """Ostrożna porada, nie harmonogram. Dłuższy dzień nie podnosi dopływu."""
    normal = report.minutes_per_day
    maximum = max(normal, int(settings.get("max_minutes_per_day", 30)))
    available = normal if today_minutes is None else min(maximum, max(0, int(today_minutes)))
    pace = max(0, int(settings.get("new_cards_per_day", 3)))
    history = snapshot.get("study_days", {})
    today = snapshot.get("today", datetime.date.today())
    current = history.get(today.isoformat(), {})
    spent = current.get("seconds", 0) / 60
    new_done = current.get("new", 0)
    due = sum(row.due_today for row in report.decks)
    learning = snapshot.get("learning_cards", 0)
    due_minutes = (due * report.review_seconds + learning * new_card_cost(
        report.learn_answers_per_new_card, report.learn_seconds
    )) / 60
    due += learning

    # ponytail: dwa pełne tygodnie i próg 80% to heurystyka; symulator FSRS
    # jest właściwym miejscem na modelowanie przyszłego kosztu kart.
    monday = today - datetime.timedelta(days=today.weekday())
    weeks = [[history.get((monday - datetime.timedelta(days=offset + day)).isoformat(), {})
              for day in range(1, 8)] for offset in (7, 0)]
    recent = [history.get((today - datetime.timedelta(days=day)).isoformat(), {})
              for day in range(1, 8)]
    active = [day for day in recent if day.get("answers", 0) > 0]
    average = sum(day.get("seconds", 0) for day in active) / max(1, len(active)) / 60
    answers = sum(day.get("answers", 0) for day in recent)
    again = sum(day.get("again", 0) for day in recent)
    again_percent = round(100 * again / answers) if answers else None
    learning_minutes = sum(day.get("learning_seconds", 0) for day in recent) / 60
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
            f"W ostatnich 7 dniach „Ponownie” stanowiło {again_percent}% odpowiedzi. "
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

    cost = max(1, new_card_cost(report.learn_answers_per_new_card, report.learn_seconds))
    room = max(0, int((available * 0.8 - spent - due_minutes) * 60 / cost))
    remaining = min(max(0, min(pace, weekly) - new_done), room, report.new_left_total)
    reason = "Najpierw zakończ należne powtórki i naukę rozpoczętych kart. Nowe tylko, jeśli zostanie czas."
    if available < normal:
        remaining = 0
        reason = "Dziś krócej: bez nowych kart. Zrób tyle powtórek, na ile masz czas."
    elif report.backlog:
        remaining = 0
        reason = "Najpierw spokojny powrót do powtórek. Zaległości nie wymagają restartu talii."
    elif spent + due_minutes >= available * 0.8:
        reason = "Zostaw zapas czasu. Dziś skup się na powtórkach i rozpoczętych kartach."
    elif new_done >= min(pace, weekly):
        reason = "Na dziś wystarczy nowych kart. Dodatkowy czas nie zwiększa tempa na kolejne dni."
    elif report.new_left_total == 0:
        reason = "Nie ma nowych kart w wybranych taliach. Spokojnie kontynuuj powtórki."
    return StudyPlan(available, spent, due, due_minutes, new_done, remaining,
                     weekly, reason, weekly_reason, average, len(active), maximum,
                     again_percent, learning_minutes)


def plan_lines(report):
    plan = report.plan
    return [
        "Twój spokojny plan",
        f"Dziś około {plan.today_minutes} min; zwykle {report.minutes_per_day}–{plan.max_minutes} min. To punkt odniesienia, nie obowiązek.",
        f"Zapisany czas odpowiedzi dziś: {plan.spent_minutes:.1f} min.",
        f"Pozostało do powtórek i nauki: {cards(plan.due_cards)} (~{math.ceil(plan.due_minutes)} min).",
        f"Po terminie: {cards(report.backlog)}. Limit sesji nie usuwa zaległości.",
        f"Nowe już dziś: {plan.new_done}. Jeszcze najwyżej {plan.new_remaining} łącznie we wszystkich wybranych taliach.",
        plan.reason,
        f"Propozycja tempa na tydzień: {new_cards(plan.weekly_new)} dziennie.",
        plan.weekly_reason,
        f"Ostatnie 7 zakończonych dni: {plan.active_days} dni nauki, średnio {plan.recent_minutes:.1f} min w dni nauki.",
        f"Nauka i ponowna nauka w tym okresie: {plan.learning_minutes:.1f} min łącznie. "
        + (f"Odpowiedzi „Ponownie”: {plan.again_percent}%." if plan.again_percent is not None else "Brak odpowiedzi do oceny trudności."),
        "Czas z Anki nie obejmuje wszystkich przerw. Nie wiemy, czy w poprzednich dniach kończyłeś kolejkę.",
        "To wskazówki: dodatek nie zatrzymuje sesji ani nie zmienia limitów Anki. Po nauce odśwież plan.",
    ]


def render_plan_html(report):
    lines = plan_lines(report)
    return "<h2>" + escape(lines[0]) + "</h2>" + "".join(
        "<p>" + escape(line) + "</p>" for line in lines[1:]
    )


def _override_or_measure(override: Any, measure) -> Tuple[float, str]:
    """Wartość z ustawień, gdy dodatnia; inaczej pomiar z historii."""
    value = float(override or 0)
    if value > 0:
        return value, "ustawione ręcznie"
    return measure()


def _deck_rows(decks: Sequence[Dict[str, Any]]) -> Tuple[List[DeckRow], List[str]]:
    names = {deck["name"] for deck in decks}
    rows: List[DeckRow] = []
    for deck in decks:
        due_counts = {int(k): int(v) for k, v in (deck.get("due_counts") or {}).items()}
        rows.append(
            DeckRow(
                name=deck["name"],
                preset=deck.get("preset", ""),
                new_per_day=int(deck.get("new_per_day", 0)),
                review_per_day=int(deck.get("review_per_day", 0)),
                new_left=int(deck.get("new_left", 0)),
                review_cards=int(deck.get("review_cards", 0)),
                structural_load=float(deck.get("reciprocal_sum", 0.0)),
                due_today=sum(count for offset, count in due_counts.items() if offset <= 0),
                # Korzeń nauki to talia, której żaden przodek nie jest w raporcie —
                # to jej preset narzuca sufit całej sesji.
                is_root=not any(parent in names for parent in ancestors(deck["name"])),
            )
        )
    return rows, [row.name for row in rows if row.is_root]


def _findings(report: Report, snapshot: Dict[str, Any]) -> List[Finding]:
    findings = _measurement_findings(report) + _setting_findings(report, snapshot)
    findings.extend(_brake_findings(report, snapshot.get("flags", {})))
    findings.append(Finding(
        "info", "Limit sesji nie usuwa zaległości",
        "Maksymalna liczba powtórek/dzień ogranicza widoczną kolejkę. "
        "Wysoki limit sam w sobie nie jest błędem. Gdy brakuje czasu, ogranicz nowe "
        "karty; pozostałe powtórki nadal czekają."
    ))
    return findings


def _brake_findings(report: Report, flags: Dict[str, Any]) -> List[Finding]:
    ignore = flags.get("newCardsIgnoreReviewLimit")
    if ignore is True:
        return [
            Finding(
                "info",
                "Nowe karty niezależne od limitu",
                "„Nowe karty ignorują limit powtórek” jest włączone, więc nowe karty "
                "mogą pojawiać się mimo pełnej kolejki powtórek. Plan Workload nie blokuje ich; "
                "zakończ sesję po osiągnięciu wybranego czasu.",
            )
        ]
    if ignore is False:
        return [
            Finding(
                "info",
                "Nowe karty podlegają limitowi",
                "„Nowe karty ignorują limit powtórek” jest wyłączone, więc nowe karty "
                "liczą się do limitu powtórek: w dniach z dużą kolejką same przestaną "
                "wchodzić. Ten mechanizm działa tylko wtedy, gdy limit powtórek ma "
                "odpowiednio niską wartość. Nie gwarantuje to zmieszczenia się w czasie.",
            )
        ]
    return []


def _measurement_findings(report: Report) -> List[Finding]:
    findings: List[Finding] = []
    estimated = [
        label
        for label, source in (
            ("powtórek na nową kartę", report.ratio_source),
            ("czas powtórki", report.review_seconds_source),
            ("czas nauki nowej karty", report.learn_seconds_source),
            ("odpowiedzi na nową kartę", report.learn_answers_source),
        )
        if source == "domyślne"
    ]
    if estimated:
        findings.append(
            Finding(
                "info",
                "Część liczb jest oszacowana",
                "Z braku historii przyjęto wartości domyślne: "
                + ", ".join(estimated)
                + f". Stan stacjonarny liczony jest wtedy regułą ×{DEFAULT_REVIEWS_PER_NEW_CARD:.0f} "
                "z manuala Anki, a nie Twoimi danymi. Obciążenie „teraz” pochodzi z "
                "interwałów kart i również jest przybliżeniem.",
            )
        )
    if report.trend.slope is None and report.structural_load > 0:
        findings.append(
            Finding(
                "info",
                "Za mało dni nauki na trend",
                f"Trend dziennej liczby powtórek liczymy od {days(MIN_ACTIVE_DAYS_FOR_TREND)} "
                "z faktyczną nauką.",
            )
        )
    return findings


def _setting_findings(report: Report, snapshot: Dict[str, Any]) -> List[Finding]:
    flags = snapshot.get("flags", {})
    findings: List[Finding] = []
    if flags.get("fsrs") is False:
        findings.append(
            Finding(
                "info",
                "FSRS wyłączone",
                "FSRS planuje powtórki celniej niż SM-2, co przy tym samym materiale "
                "oznacza mniej powtórek dziennie. Warto włączyć.",
            )
        )
    if flags.get("loadBalancerEnabled") is False:
        findings.append(
            Finding(
                "info",
                "Load balancer wyłączony",
                "Bez niego powtórki zbijają się w górki w pojedynczych dniach. "
                "Włącz go w Opcjach talii, w menu akcji.",
            )
        )

    gaps = _parent_gaps(report, flags)
    if gaps:
        findings.append(
            Finding(
                "warn",
                "Talia nadrzędna szersza niż podtalie",
                "Włączone jest „Limity od góry”, a limity talii nadrzędnej są szersze "
                f"niż suma podtalii: {gaps}. Limity opisują ustawienia, "
                "nie należy sumować limitów jako rzeczywistego dopływu nowych kart.",
            )
        )

    reduced = _easy_days(snapshot)
    if reduced:
        findings.append(
            Finding(
                "info",
                "Dni łatwe",
                f"Obniżone dni tygodnia: {reduced}. Mogą zmieniać rozkład terminów w Anki; "
                "nie zmieniają wybranego czasu w Workload.",
            )
        )

    unread = snapshot.get("flag_errors") or []
    if unread:
        findings.append(
            Finding(
                "info",
                "Nie odczytano ustawień kolekcji",
                "Tych kluczy nie udało się odczytać: " + ", ".join(sorted(unread))
                + ". Powiązane uwagi są w tym raporcie pominięte, a nie uznane za "
                "wyłączone — prawdopodobnie zmieniło się API Anki.",
            )
        )
    return findings


def _parent_gaps(report: Report, flags: Dict[str, Any]) -> str:
    if flags.get("applyAllParentLimits") is not True:
        return ""
    by_name = {row.name: row for row in report.decks}
    gaps = []
    for row in report.decks:
        children = [
            other for name, other in by_name.items() if name.startswith(row.name + "::")
        ]
        if not children:
            continue
        children_new = sum(child.new_per_day for child in children)
        if row.new_per_day > children_new:
            gaps.append(f"{row.name} ({row.new_per_day} > {children_new})")
    return ", ".join(gaps)


_WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")


def _easy_days(snapshot: Dict[str, Any]) -> str:
    """Dni tygodnia obniżone w „dniach łatwych”, zebrane ze wszystkich presetów."""
    reduced: Dict[str, float] = {}
    for deck in snapshot.get("decks", []):
        percentages = deck.get("easy_days") or []
        for index, value in enumerate(percentages[: len(_WEEKDAYS)]):
            if value is not None and float(value) < 1.0:
                name = _WEEKDAYS[index]
                reduced[name] = min(reduced.get(name, 1.0), float(value))
    return ", ".join(f"{name} {int(value * 100)}%" for name, value in reduced.items())


# ── Renderowanie raportu (czyste, bez Qt) ──────────────────────────────────

# Punkty prognozy pokazywane w tabeli — pełna lista dzienna byłaby nieczytelna.
_FORECAST_MARKS = (1, 3, 7, 14, 30, 60, 90, 180, 365)


def forecast_marks(forecast: Sequence[Tuple[int, int]]) -> List[Tuple[int, int, int]]:
    """Wiersze tabeli prognozy: (dzień, karty tego dnia, suma do tego dnia)."""
    if not forecast:
        return []
    last = forecast[-1][0]
    rows = []
    for day in _FORECAST_MARKS:
        if day > last:
            break
        single = next((count for offset, count in forecast if offset == day), 0)
        rows.append((day, single, cumulative_at(forecast, day)))
    return rows


def render_html(report: Report) -> str:
    """Szczegóły opisują dane i założenia, nie obiecują bezpiecznego dopływu."""
    parts = ["<h3>Szczegóły raportu</h3>"]
    parts.append(
        f"<p>Zwykły czas: {report.minutes_per_day} min. Czas odpowiedzi powtórkowej: "
        f"{report.review_seconds:.1f} s ({escape(report.review_seconds_source)}). "
        f"Koszt nauki nowej karty: około "
        f"{new_card_cost(report.learn_answers_per_new_card, report.learn_seconds):.0f} s.</p>"
        f"<h3>Przybliżenie z interwałów</h3><p>{reviews(report.structural_load)} na dzień "
        f"(~{report.structural_minutes} min), przy założeniu stałych interwałów. "
        "To wskaźnik, nie pomiar rzeczywistego czasu ani prognoza schedulera.</p>"
        f"<h3>Scenariusz według limitów</h3><p>Suma limitów talii z nowymi kartami: "
        f"{report.new_total}. Nie uwzględnia ograniczenia przez rodzica ani dzisiejszej dostępności. "
        f"Mnożnik {report.reviews_per_new_card:.1f} ({escape(report.ratio_source)}) daje "
        f"{reviews(report.steady_state)} dziennie (~{report.steady_state_minutes} min z nauką). "
        "To uproszczony scenariusz, nie zalecane tempo. Historyczny stosunek powtórek do nowych "
        "kart nie określa ich przyszłego kosztu. Do porównania przyszłych scenariuszy służy "
        "symulator w Opcjach talii Anki.</p>"
    )
    if report.trend.level is not None:
        parts.append(f"<p>Wykonane powtórki: średnio {report.trend.level:.0f}/dzień "
                     "w ostatnich 7 dniach (z dzisiejszym). To aktywność, nie liczba należnych kart.</p>")
    parts.append("<h3>Talie</h3><table cellpadding='5'><tr><th>Talia</th><th>Preset</th>"
                 "<th>Limit nowych</th><th>Jeszcze dziś — propozycja</th>"
                 "<th>Limit powtórek</th><th>Przybliżenie/dzień</th><th>Zapas nowych</th></tr>")
    for row in report.decks:
        parts.append(
            f"<tr><td>{escape(row.name)}</td><td>{escape(row.preset)}</td>"
            f"<td>{row.new_per_day}</td><td>{row.suggested_new_per_day}</td>"
            f"<td>{row.review_per_day}</td><td>{row.structural_load:.1f}</td><td>{row.new_left}</td></tr>"
        )
    parts.append("</table><p>Podział propozycji jest orientacyjny; Anki nadal stosuje swoje "
                 "limity i zakopywanie kart. Możesz zrobić mniej lub zero nowych.</p>")
    marks = forecast_marks(report.forecast)
    if marks:
        parts.append("<h3>Już zaplanowane terminy</h3><p>Każda karta występuje tylko raz. "
                     "Tabela nie uwzględnia jej kolejnych powrotów ani przyszłych nowych kart.</p>"
                     "<table cellpadding='5'><tr><th>Za dni</th><th>Kart</th><th>Łącznie do dnia</th></tr>")
        for day, single, total in marks:
            parts.append(f"<tr><td>{day}</td><td>{single}</td><td>{total}</td></tr>")
        parts.append("</table>")
        if report.peak:
            parts.append(f"<p>Największa obecnie zaplanowana kolejka: za {days(report.peak[0])}, "
                         f"{cards(report.peak[1])}.</p>")
    parts.append("<h3>Uwagi</h3>")
    for finding in report.findings:
        parts.append(f"<p><b>{escape(finding.title)}</b><br>{escape(finding.detail)}</p>")
    parts.append("<p>Dodatek tylko czyta kolekcję. Propozycje nie zmieniają opcji Anki.</p>")
    return "".join(parts)


def render_text(report: Report) -> str:
    lines = ["Anki Toolkit: Workload", "", *plan_lines(report), "", "Szczegóły:",
             f"Przybliżenie z interwałów: {reviews(report.structural_load)} na dzień "
             f"(~{report.structural_minutes} min), przy stałych interwałach.",
             "Talie (propozycje dodatkowych nowych kart na dziś):"]
    for row in report.decks:
        lines.append(f"  {row.name}: {row.suggested_new_per_day}, zapas {row.new_left}")
    lines += ["", "Uwagi:"]
    lines.extend(f"  {finding.title}: {finding.detail}" for finding in report.findings)
    lines.append("Dodatek tylko czyta kolekcję — nie zmienia limitów Anki.")
    return "\n".join(lines)
