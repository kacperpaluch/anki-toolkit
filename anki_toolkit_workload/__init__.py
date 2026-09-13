"""Anki Toolkit: Workload — raport obciążenia nauką i spójności limitów.

Dodatek tylko czyta kolekcję: zbiera migawkę (limity presetów, zapas nowych
kart, interwały, terminy powtórek, historię revlog), przekazuje ją do
`logic.analyze` i pokazuje raport. Nie zapisuje nic do kolekcji ani do opcji
talii.
"""

import datetime

from aqt import gui_hooks, mw
from aqt.qt import (
    QAction, QApplication, QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout
)
from aqt.utils import tooltip

from . import logic

DEFAULTS = {
    "minutes_per_day": 30,
    "seconds_per_card": 0,
    "learn_seconds_per_card": 0,
    "learn_answers_per_new_card": 0,
    "reviews_per_new_card": 0,
    "forecast_days": 60,
    "split_strategy": logic.SPLIT_PROPORTIONAL,
    "decks": [],
}
# Typy revlog: 0 = nauka, 1 = powtórka, 2 = przeuczenie, 3 = talia filtrowana,
# 4 = ręczna zmiana, 5 = przeplanowanie. Do czasów i liczników bierzemy 0-2.
_LEARN_TYPE = 0
_REVIEW_TYPES = (1, 2)
_ANSWER_TYPES = (_LEARN_TYPE, *_REVIEW_TYPES)
_SECONDS_WINDOW_DAYS = 30
_TREND_WINDOW_DAYS = 28
_COLLECTION_FLAGS = ("fsrs", "loadBalancerEnabled", "newCardsIgnoreReviewLimit", "applyAllParentLimits")
_MISSING = object()


def _addon_name(): return __name__.split(".")[0]
def get_config(): return {**DEFAULTS, **(mw.addonManager.getConfig(_addon_name()) or {})}
def save_config(changes):
    config = get_config(); config.update(changes); mw.addonManager.writeConfig(_addon_name(), config)


# ── Odczyt kolekcji ────────────────────────────────────────────────────────

def _flags(col):
    """Flagi kolekcji oraz klucze, których odczyt się nie udał.

    Klucz nieobecny daje None i nie jest błędem — Anki mogło go po prostu nigdy
    nie zapisać. Wyjątek przy odczycie oznacza zmianę API i musi być widoczny
    w raporcie, bo po cichu wycina powiązane uwagi.
    """
    values, errors = {}, []
    for key in _COLLECTION_FLAGS:
        try:
            value = col.get_config(key, default=_MISSING)
        except Exception:
            values[key] = None; errors.append(key); continue
        values[key] = None if value is _MISSING else value
    return values, errors


def _deck_limits(col, did):
    """Efektywne limity talii: „Ta talia” ma pierwszeństwo nad presetem."""
    conf = col.decks.config_dict_for_deck_id(did)
    deck = col.decks.get(did) or {}
    new_per_day = deck.get("newLimit")
    review_per_day = deck.get("reviewLimit")
    if new_per_day is None:
        new_per_day = conf.get("new", {}).get("perDay", 0)
    if review_per_day is None:
        review_per_day = conf.get("rev", {}).get("perDay", 0)
    return {
        "new_per_day": int(new_per_day),
        "review_per_day": int(review_per_day),
        "preset": conf.get("name", ""),
        "easy_days": list(conf.get("easyDaysPercentages") or []),
    }


def _card_data(col, deck_ids):
    """Zapas nowych kart, terminy i obciążenie strukturalne, per talia."""
    today = col.sched.today
    empty = {did: 0 for did in deck_ids}
    new_left = dict(empty)
    review_cards = dict(empty)
    reciprocal = {did: 0.0 for did in deck_ids}
    due_counts = {did: {} for did in deck_ids}
    # odid wskazuje talię macierzystą karty wyciągniętej do talii filtrowanej.
    for did, odid, queue, card_type, due, ivl in col.db.all(
        "select did, odid, queue, type, due, ivl from cards where queue != -1"
    ):
        home = odid or did
        if home not in new_left:
            continue
        if queue == 0 or (queue in (-2, -3) and card_type == 0):
            new_left[home] += 1  # zakopane nowe karty wrócą, więc liczą się do zapasu
        elif queue in (2, 3):  # tylko tu `due` jest numerem dnia, nie znacznikiem czasu
            offset = int(due) - today
            counts = due_counts[home]
            counts[offset] = counts.get(offset, 0) + 1
            review_cards[home] += 1
            # Karta z interwałem N dni kosztuje 1/N powtórki dziennie.
            reciprocal[home] += 1.0 / max(1, int(ivl or 0))
    return new_left, review_cards, reciprocal, due_counts


def _revlog_data(col):
    """Czasy odpowiedzi, liczba dni z nauką, sumy i dzienny przebieg powtórek."""
    answers = ",".join("?" * len(_ANSWER_TYPES))
    reviews = ",".join("?" * len(_REVIEW_TYPES))
    cutoff_ms = (col.sched.day_cutoff - _SECONDS_WINDOW_DAYS * 86400) * 1000
    learn_seconds, review_seconds = [], []
    for card_type, time_ms in col.db.all(
        f"select type, time from revlog where id > ? and time > 0 and type in ({answers})",
        cutoff_ms, *_ANSWER_TYPES,
    ):
        (learn_seconds if card_type == _LEARN_TYPE else review_seconds).append(time_ms / 1000.0)

    # Numer dnia liczony jak w schedulerze, żeby zgadzał się z `sched.today`.
    day_expression = f"cast((id / 1000 - {int(col.crt)}) / 86400 as int)"
    active_days = col.db.scalar(
        f"select count(distinct {day_expression}) from revlog where type in ({answers})",
        *_ANSWER_TYPES,
    ) or 0

    today = col.sched.today
    first_day = today - _TREND_WINDOW_DAYS + 1
    counted = dict(col.db.all(
        f"select {day_expression} as day, count() from revlog "
        f"where type in ({reviews}) and {day_expression} >= ? group by day",
        *_REVIEW_TYPES, first_day,
    ))
    # Dni bez nauki muszą być zerami, inaczej przerwa wyglądałaby jak spadek.
    daily_reviews = [(day, int(counted.get(day, 0))) for day in range(first_day, today + 1)]

    return {
        "learn_seconds": learn_seconds,
        "review_seconds": review_seconds,
        "active_days": int(active_days),
        "daily_reviews": daily_reviews,
        "new_introduced": col.db.scalar("select count(distinct cid) from revlog where type = ?", _LEARN_TYPE) or 0,
        "learn_answers": col.db.scalar("select count() from revlog where type = ?", _LEARN_TYPE) or 0,
        "reviews_done": col.db.scalar(
            f"select count() from revlog where type in ({reviews})", *_REVIEW_TYPES
        ) or 0,
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
    new_left, review_cards, reciprocal, due_counts = _card_data(col, deck_ids)
    with_cards = {
        deck["name"] for deck in decks if new_left[deck["id"]] or due_counts[deck["id"]]
    }
    # Talia bez własnych kart zostaje w raporcie tylko jako przodek talii z
    # kartami — jej preset obowiązuje przy „limitach od góry”.
    kept = with_cards | {a for name in with_cards for a in logic.ancestors(name)}

    rows = []
    for deck in decks:
        if deck["name"] not in kept:
            continue
        row = {"name": deck["name"], **_deck_limits(col, deck["id"])}
        row.update({
            "new_left": new_left[deck["id"]],
            "review_cards": review_cards[deck["id"]],
            "reciprocal_sum": reciprocal[deck["id"]],
            "due_counts": due_counts[deck["id"]],
        })
        rows.append(row)

    values, errors = _flags(col)
    snapshot = {
        "decks": rows,
        "flags": values,
        "flag_errors": errors,
        "today": datetime.date.today(),
    }
    snapshot.update(_revlog_data(col))
    return snapshot


# ── Okno raportu ───────────────────────────────────────────────────────────

class ReportDialog(QDialog):
    def __init__(self, report):
        super().__init__(mw); self.setWindowTitle("Anki Toolkit: Workload"); self.resize(760, 680)
        self.report = report
        layout = QVBoxLayout(self)
        view = QTextBrowser(); view.setHtml(logic.render_html(report)); layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_button = QPushButton("Kopiuj raport")
        copy_button.clicked.connect(self.copy_report)
        buttons.addButton(copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        settings_button = QPushButton("Ustawienia…")
        settings_button.clicked.connect(self.open_settings)
        buttons.addButton(settings_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def copy_report(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            tooltip("Schowek jest niedostępny.", parent=mw); return
        clipboard.setText(logic.render_text(self.report))
        tooltip("Raport skopiowany.", parent=mw)

    def open_settings(self):
        from .settings import open_settings
        if open_settings():
            self.accept(); show_report()


def show_report():
    if mw.col is None:
        tooltip("Najpierw otwórz profil.", parent=mw); return
    settings = get_config()
    ReportDialog(logic.analyze(build_snapshot(mw.col, settings), settings)).exec()


def _setup(*_args):
    action = QAction("Anki Toolkit: Workload…", mw)
    action.triggered.connect(show_report)
    mw.form.menuTools.addAction(action)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup)
