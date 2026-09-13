"""Czysta logika raportu obciążenia: bez importów Anki i Qt, w pełni testowalna.

Wejściem jest migawka kolekcji (zwykły słownik, patrz `analyze`), wyjściem raport
z liczbami i listą uwag. Dodatek nigdy nie zapisuje nic do kolekcji — proponuje
wartości, które użytkownik wpisuje sam w Opcjach talii.

Dwie wielkości opisują obciążenie i nie należy ich mieszać:

- `structural_load` — ile powtórek dziennie generują karty, które już masz.
  Suma odwrotności interwałów: karta z interwałem 10 dni kosztuje 0,1 powtórki
  na dzień. To pomiar, nie prognoza.
- `steady_state` — ile powtórek dziennie da dopływ nowych kart, gdy zapas się
  rozejdzie. To projekcja przez współczynnik „powtórek na nową kartę”, więc
  raport zawsze podaje, skąd ten współczynnik pochodzi.
"""

import dataclasses
import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Zapasowe stałe używane, gdy historia powtórek jest za krótka, by cokolwiek zmierzyć.
DEFAULT_REVIEW_SECONDS = 9.0
DEFAULT_LEARN_SECONDS = 12.0
# Ile odpowiedzi kosztuje nowa karta w dniu wprowadzenia (kroki nauki 1 min/10 min).
DEFAULT_LEARN_ANSWERS_PER_NEW_CARD = 2.5
# Reguła z manuala Anki: 20 nowych kart dziennie daje około 200 powtórek dziennie.
DEFAULT_REVIEWS_PER_NEW_CARD = 10.0
# Poniżej tylu dni z faktyczną nauką zmierzony stosunek powtórek do nowych kart
# jest zaniżony (karty nie zdążyły jeszcze wrócić), więc używamy reguły ×10.
MIN_ACTIVE_DAYS_FOR_RATIO = 60
# Tyle dni z faktyczną nauką wystarczy, by liczyć trend dziennej liczby powtórek.
MIN_ACTIVE_DAYS_FOR_TREND = 10
# Limit powtórek w presecie powyżej tej wartości traktujemy jako brak sufitu.
NO_CEILING_THRESHOLD = 1000
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
    suggested_new_total: int
    structural_load: int
    structural_minutes: int
    steady_state: int
    steady_state_minutes: int
    new_left_total: int
    days_of_intake: Optional[int]
    backlog: int
    peak: Optional[Tuple[int, int]]
    forecast: List[Tuple[int, int]]
    trend: Trend
    decks: List[DeckRow]
    roots: List[str]
    findings: List[Finding]


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


def suggest_new_per_day(
    minutes: int,
    review_seconds: float,
    reviews_per_new_card: float,
    learn_answers_per_new_card: float = 0.0,
    learn_seconds: float = 0.0,
) -> int:
    """Dopływ nowych kart, którego pełny koszt zmieści się w budżecie czasu.

    Jedna nowa karta dziennie kosztuje dziennie: powtórki, które wygeneruje, oraz
    odpowiedzi w dniu wprowadzenia. Stąd zamknięty wzór na największy dopływ.
    """
    cost = reviews_per_new_card * review_seconds + new_card_cost(
        learn_answers_per_new_card, learn_seconds
    )
    if minutes <= 0 or cost <= 0:
        return 0
    return max(1, int(minutes * 60 / cost))


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
    Każda talia dostaje co najmniej 1 kartę dziennie, więc przy bardzo małym
    `target_total` suma może być większa od zadanej — lepiej zaproponować
    minimum niż wyłączyć talię.
    """
    active = {name: value for name, value in limits.items() if value > 0}
    if not active:
        return {}
    if strategy == SPLIT_HEAVIEST_FIRST:
        return _cut_heaviest_first(active, target_total)
    return _scale_proportional(active, target_total)


def _scale_proportional(active: Dict[str, int], target_total: int) -> Dict[str, int]:
    current_total = sum(active.values())
    exact = {name: value * target_total / current_total for name, value in active.items()}
    scaled = {name: max(1, int(value)) for name, value in exact.items()}
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
        if result[name] <= 1:
            break  # dalej nie ma czego ścinać bez wyłączania talii
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

def analyze(snapshot: Dict[str, Any], settings: Dict[str, Any]) -> Report:
    """Buduje raport z migawki kolekcji (patrz `__init__.build_snapshot`)."""
    minutes = int(settings.get("minutes_per_day", 30))
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
    suggested_total = suggest_new_per_day(
        minutes, review_seconds, ratio, learn_answers, learn_seconds
    )
    strategy = settings.get("split_strategy", SPLIT_PROPORTIONAL)
    proposal = scale_limits(feeding, suggested_total, strategy) if new_total > suggested_total else {}
    for row in rows:
        row.suggested_new_per_day = proposal.get(row.name)

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
        suggested_new_total=suggested_total,
        structural_load=int(round(load)),
        structural_minutes=int(round(load * review_seconds / 60)),
        steady_state=steady,
        steady_state_minutes=int(
            round((steady * review_seconds + new_total * new_card_cost(learn_answers, learn_seconds)) / 60)
        ),
        new_left_total=new_left_total,
        days_of_intake=int(new_left_total / new_total) if new_total > 0 else None,
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
    _assign_review_ceilings(report)
    report.findings = _findings(report, snapshot)
    return report


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


def _assign_review_ceilings(report: Report) -> None:
    """Rozdziela sufit powtórek: korzeń dostaje całość, podtalie swój udział.

    Sufit wpisany w każdą podtalię osobno nie ogranicza sumy — dlatego wartość
    dla korzenia i dla podtalii musi być inna.
    """
    if report.ceiling <= 0:
        return
    children = [row for row in report.decks if not row.is_root]
    share_base = {row.name: max(1, row.new_per_day) for row in children}
    total = sum(share_base.values())
    for row in report.decks:
        if row.is_root:
            row.suggested_review_per_day = report.ceiling
        elif total > 0:
            row.suggested_review_per_day = max(
                1, int(report.ceiling * share_base[row.name] / total)
            )


# ── Uwagi ──────────────────────────────────────────────────────────────────

def _findings(report: Report, snapshot: Dict[str, Any]) -> List[Finding]:
    flags = snapshot.get("flags", {})
    findings: List[Finding] = []
    findings.extend(_ceiling_findings(report))
    findings.extend(_load_findings(report))
    findings.extend(_brake_findings(report, flags))
    findings.extend(_measurement_findings(report))
    findings.extend(_setting_findings(report, snapshot))
    if not [f for f in findings if f.level in ("alert", "warn")]:
        findings.insert(
            0,
            Finding("ok", "Bez uwag", "Dopływ nowych kart i sufit powtórek są spójne."),
        )
    return findings


def _ceiling_findings(report: Report) -> List[Finding]:
    uncapped = [row for row in report.decks if row.review_per_day >= NO_CEILING_THRESHOLD]
    if not uncapped:
        return []
    roots = [row for row in uncapped if row.is_root]
    children = [row for row in uncapped if not row.is_root]
    lines = []
    if roots:
        lines.append(
            "w presetach talii, z których się uczysz ("
            + ", ".join(f"{row.preset or row.name} → {row.suggested_review_per_day}" for row in roots)
            + ")"
        )
    if children:
        lines.append(
            "w podtaliach ("
            + ", ".join(f"{row.preset or row.name} → {row.suggested_review_per_day}" for row in children)
            + ")"
        )
    return [
        Finding(
            "alert",
            "Brak sufitu powtórek",
            f"Twój sufit to {reviews(report.ceiling)} dziennie. Wpisz Maksymalna "
            "liczba powtórek/dzień " + " oraz ".join(lines) + ". "
            "Ta sama liczba w każdej podtalii nie ogranicza sumy — pięć presetów "
            f"po {report.ceiling} daje {reviews(report.ceiling * 5)} dziennie, dlatego "
            "całość należy do talii nadrzędnej, a podtalie dostają swój udział.",
        )
    ]


def _load_findings(report: Report) -> List[Finding]:
    findings: List[Finding] = []
    if report.backlog > report.ceiling:
        findings.append(
            Finding(
                "alert",
                "Zaległości",
                f"{cards(report.backlog)} czeka po terminie, czyli więcej niż dzienny "
                f"sufit ({report.ceiling}). Zanim wrócisz do nowych kart, odrób "
                "zaległość lub tymczasowo zejdź z dopływu do zera.",
            )
        )

    if report.ceiling <= 0:
        findings.append(
            Finding(
                "alert",
                "Nowe karty zjadają cały czas",
                f"Samo wprowadzenie {new_cards(report.new_total)} dziennie kosztuje "
                f"więcej niż {report.minutes_per_day} min, które chcesz poświęcać. "
                "Na powtórki nie zostaje nic — obniż dopływ albo zwiększ czas.",
            )
        )
    elif report.structural_load > report.ceiling:
        findings.append(
            Finding(
                "alert",
                "Już teraz powyżej sufitu",
                f"Karty, które już masz, generują {reviews(report.structural_load)} "
                f"dziennie (~{report.structural_minutes} min) — to pomiar z interwałów, "
                f"nie prognoza. Twój sufit to {report.ceiling}.",
            )
        )

    if report.new_total > report.suggested_new_total:
        changes = ", ".join(
            f"{row.name}: {row.new_per_day} → {row.suggested_new_per_day}"
            for row in report.decks
            if row.suggested_new_per_day is not None
            and row.suggested_new_per_day != row.new_per_day
        )
        findings.append(
            Finding(
                "warn",
                "Dopływ nowych kart za wysoki",
                f"Razem {new_cards(report.new_total)} dziennie dojdzie do "
                f"{reviews(report.steady_state)} dziennie (~{report.steady_state_minutes} min "
                f"z kosztem nauki), a mieści się {new_cards(report.suggested_new_total)}. "
                + (f"Podział: {changes}." if changes else ""),
            )
        )

    trend = report.trend
    if trend.days_to_ceiling is not None and trend.slope:
        date = f" (około {trend.date_of_ceiling.isoformat()})" if trend.date_of_ceiling else ""
        findings.append(
            Finding(
                "warn",
                "Obciążenie rośnie",
                f"Dzienna liczba powtórek rośnie o {trend.slope:.1f} na dzień, "
                f"teraz jest {trend.level:.0f}. Przy tym tempie sufit "
                f"{report.ceiling} przebijesz za {days(trend.days_to_ceiling)}{date}.",
            )
        )

    if report.peak and report.peak[1] > report.ceiling:
        day, count = report.peak
        findings.append(
            Finding(
                "warn",
                "Górka w prognozie",
                f"Za {days(day)} wypada {cards(count)}, powyżej sufitu {report.ceiling}. "
                "Jeden dzień ponad limit nie jest problemem, powtarzająca się górka "
                "oznacza za szybki dopływ.",
            )
        )
    return findings


def _brake_findings(report: Report, flags: Dict[str, Any]) -> List[Finding]:
    ignore = flags.get("newCardsIgnoreReviewLimit")
    if ignore is True:
        return [
            Finding(
                "alert",
                "Hamulec wyłączony",
                "„Nowe karty ignorują limit powtórek” jest włączone, więc nowe karty "
                "wchodzą nawet przy pełnej kolejce powtórek. Wyłącz tę opcję — razem "
                "z sufitem powtórek to jedyny mechanizm, który sam reguluje dopływ.",
            )
        ]
    if ignore is False:
        return [
            Finding(
                "info",
                "Hamulec działa",
                "„Nowe karty ignorują limit powtórek” jest wyłączone, więc nowe karty "
                "liczą się do limitu powtórek: w dniach z dużą kolejką same przestaną "
                "wchodzić. Ten mechanizm działa tylko wtedy, gdy limit powtórek ma "
                "realną wartość.",
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
                "interwałów kart i jest pomiarem niezależnie od historii.",
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
                f"niż suma podtalii: {gaps}. To one obowiązują podczas nauki, więc "
                "sufit z podtalii nie działa.",
            )
        )

    reduced = _easy_days(snapshot)
    if reduced:
        findings.append(
            Finding(
                "info",
                "Dni łatwe zmieniają sufit",
                f"Obniżone dni tygodnia: {reduced}. W te dni realny sufit jest "
                "odpowiednio mniejszy, a raport liczy wartość dla zwykłego dnia.",
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

_LEVEL_MARK = {"alert": "●", "warn": "▲", "info": "·", "ok": "✓"}
_LEVEL_COLOR = {"alert": "#b00020", "warn": "#a35b00", "info": "#555", "ok": "#1b7a2f"}
# Punkty prognozy pokazywane w tabeli — pełna lista dzienna byłaby nieczytelna.
_FORECAST_MARKS = (1, 3, 7, 14, 30, 60, 90, 180, 365)
_BAR_WIDTH = 18


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


def _bar(value: int, reference: int) -> str:
    if reference <= 0 or value <= 0:
        return ""
    return "█" * max(1, min(_BAR_WIDTH, int(_BAR_WIDTH * value / reference)))


def render_html(report: Report) -> str:
    """Buduje HTML raportu dla okna dodatku."""
    parts = [
        "<style>"
        "body{font-family:-apple-system,Segoe UI,sans-serif;font-size:13px}"
        "h3{margin:14px 0 6px}"
        "table{border-collapse:collapse;margin:4px 0}"
        "td,th{border:1px solid #bbb;padding:3px 7px;text-align:right}"
        "th:first-child,td:first-child{text-align:left}"
        ".note{color:#666}.bar{font-family:monospace;color:#888}"
        "</style>"
    ]
    cost = new_card_cost(report.learn_answers_per_new_card, report.learn_seconds)

    parts.append("<h3>Twój budżet</h3>")
    parts.append(
        f"<p>{report.minutes_per_day} min dziennie, powtórka {report.review_seconds:.1f} s "
        f"({report.review_seconds_source}). Jedna nowa karta kosztuje dodatkowo "
        f"{report.learn_answers_per_new_card:.1f} × {report.learn_seconds:.1f} s = {cost:.0f} s "
        f"w dniu wprowadzenia ({report.learn_answers_source}).<br>"
        f"Po odjęciu kosztu {new_cards(report.new_total)} zostaje "
        f"<b>{reviews(report.ceiling)} dziennie</b>, a docelowo mieści się "
        f"<b>{new_cards(report.suggested_new_total)} dziennie</b>.</p>"
    )

    parts.append("<h3>Teraz — pomiar</h3>")
    parts.append(
        f"<p>Karty, które już masz, generują <b>{reviews(report.structural_load)} dziennie</b> "
        f"(~{report.structural_minutes} min). To suma odwrotności interwałów, nie prognoza.<br>"
        f"Zaległości: {cards(report.backlog)}."
    )
    trend = report.trend
    if trend.slope is not None and trend.level is not None:
        direction = "rośnie" if trend.slope > 0 else "maleje"
        parts.append(
            f"<br>Trend: {reviews(trend.level)} dziennie, {direction} o "
            f"{abs(trend.slope):.1f} na dzień."
        )
        if trend.days_to_ceiling is not None:
            date = f" ({trend.date_of_ceiling.isoformat()})" if trend.date_of_ceiling else ""
            parts.append(f" Sufit za {days(trend.days_to_ceiling)}{date}.")
    parts.append("</p>")

    parts.append("<h3>Docelowo — projekcja</h3>")
    parts.append(
        f"<p>Dopływ <b>{new_cards(report.new_total)}</b> dziennie przy "
        f"{report.reviews_per_new_card:.1f} powtórkach na kartę ({report.ratio_source}) "
        f"daje <b>{reviews(report.steady_state)} dziennie</b> "
        f"(~{report.steady_state_minutes} min z kosztem nauki).<br>"
        f"Zapas: {new_cards(report.new_left_total)}"
        + (f", wystarczy na {days(report.days_of_intake)}." if report.days_of_intake else ".")
        + "</p>"
    )

    parts.append("<h3>Talie</h3>")
    parts.append(
        "<table><tr><th>Talia</th><th>Preset</th><th>Nowe/dzień</th><th>Propozycja</th>"
        "<th>Max powtórek</th><th>Propozycja</th><th>Obciążenie/dzień</th>"
        "<th>Nowe zostało</th><th>Due dziś</th></tr>"
    )
    for row in report.decks:
        new_suggestion = (
            str(row.suggested_new_per_day) if row.suggested_new_per_day is not None else "—"
        )
        ceiling_suggestion = (
            str(row.suggested_review_per_day)
            if row.suggested_review_per_day is not None
            else "—"
        )
        current_ceiling = (
            f"<b>{row.review_per_day}</b>"
            if row.review_per_day >= NO_CEILING_THRESHOLD
            else str(row.review_per_day)
        )
        name = f"{row.name} ★" if row.is_root else row.name
        parts.append(
            f"<tr><td>{name}</td><td>{row.preset}</td><td>{row.new_per_day}</td>"
            f"<td>{new_suggestion}</td><td>{current_ceiling}</td><td>{ceiling_suggestion}</td>"
            f"<td>{row.structural_load:.1f}</td><td>{row.new_left}</td><td>{row.due_today}</td></tr>"
        )
    parts.append("</table>")
    parts.append(
        "<p class='note'>★ talia, z której się uczysz — jej preset narzuca sufit całej "
        "sesji, dlatego dostaje pełną wartość, a podtalie swój udział.</p>"
    )

    marks = forecast_marks(report.forecast)
    if marks:
        reference = max(single for _, single, _ in marks) or 1
        parts.append("<h3>Prognoza</h3>")
        parts.append(
            "<table><tr><th>Za dni</th><th>Kart tego dnia</th><th></th>"
            "<th>Razem do tego dnia</th></tr>"
        )
        for day, single, total in marks:
            parts.append(
                f"<tr><td>{day}</td><td>{single}</td>"
                f"<td class='bar'>{_bar(single, reference)}</td><td>{total}</td></tr>"
            )
        parts.append("</table>")
        if report.peak:
            parts.append(
                f"<p class='note'>Największy dzień w oknie: za {days(report.peak[0])}, "
                f"{cards(report.peak[1])}.</p>"
            )

    parts.append("<h3>Uwagi</h3><ul>")
    for finding in report.findings:
        color = _LEVEL_COLOR.get(finding.level, "#333")
        mark = _LEVEL_MARK.get(finding.level, "·")
        parts.append(
            f"<li><span style='color:{color}'>{mark} <b>{finding.title}</b></span>"
            f"<br>{finding.detail}</li>"
        )
    parts.append("</ul>")
    parts.append(
        "<p class='note'>Dodatek tylko czyta kolekcję. Żadnej z tych wartości nie "
        "zapisuje — wpisujesz je sam w Opcjach talii.</p>"
    )
    return "".join(parts)


def render_text(report: Report) -> str:
    """Wersja tekstowa raportu do skopiowania."""
    lines = [
        "Anki Toolkit: Workload",
        "",
        f"Budżet: {report.minutes_per_day} min/dzień, powtórka {report.review_seconds:.1f} s "
        f"({report.review_seconds_source})",
        f"Sufit przy obecnym dopływie: {reviews(report.ceiling)} na dzień",
        f"Mieści się: {new_cards(report.suggested_new_total)} na dzień",
        "",
        f"Teraz (pomiar z interwałów): {reviews(report.structural_load)} na dzień "
        f"(~{report.structural_minutes} min)",
        f"Zaległości: {report.backlog}",
    ]
    trend = report.trend
    if trend.slope is not None and trend.level is not None:
        lines.append(
            f"Trend: {trend.level:.0f}/dzień, zmiana {trend.slope:+.1f}/dzień"
            + (
                f", sufit za {trend.days_to_ceiling} dni"
                if trend.days_to_ceiling is not None
                else ""
            )
        )
    lines += [
        "",
        f"Dopływ: {new_cards(report.new_total)} na dzień → docelowo {reviews(report.steady_state)} "
        f"na dzień (~{report.steady_state_minutes} min)",
        f"Zapas: {new_cards(report.new_left_total)}"
        + (f", na {days(report.days_of_intake)}" if report.days_of_intake else ""),
        "",
        "Talie:",
    ]
    for row in report.decks:
        root = " ★" if row.is_root else ""
        lines.append(
            f"  {row.name}{root} [{row.preset}] nowe {row.new_per_day}"
            + (f"→{row.suggested_new_per_day}" if row.suggested_new_per_day is not None else "")
            + f", max powtórek {row.review_per_day}"
            + (
                f"→{row.suggested_review_per_day}"
                if row.suggested_review_per_day is not None
                else ""
            )
            + f", obciążenie {row.structural_load:.1f}/dzień, zapas {row.new_left}"
        )
    lines += ["", "Uwagi:"]
    for finding in report.findings:
        lines.append(f"  {_LEVEL_MARK.get(finding.level, '·')} {finding.title}: {finding.detail}")
    lines += ["", "Dodatek tylko czyta kolekcję — wartości wpisujesz sam w Opcjach talii."]
    return "\n".join(lines)
