"""Anki Toolkit: Workload — raport obciążenia nauką i spójności limitów.

Dodatek tylko czyta kolekcję: zbiera migawkę (limity presetów, zapas nowych
kart, interwały, terminy powtórek, historię revlog), przekazuje ją do
`logic.analyze` i pokazuje raport. Nie zapisuje nic do kolekcji ani do opcji
talii.
"""

import datetime

from aqt import gui_hooks, mw
from aqt.qt import (
    QAction, QApplication, QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout, QSpinBox, QFormLayout
)
from aqt.utils import tooltip

from . import logic

DEFAULTS = {
    "minutes_per_day": 15,
    "max_minutes_per_day": 30,
    "new_cards_per_day": 3,
    "seconds_per_card": 0,
    "learn_seconds_per_card": 0,
    "learn_answers_per_new_card": 0,
    "reviews_per_new_card": 0,
    "forecast_days": 60,
    "split_strategy": logic.SPLIT_PROPORTIONAL,
    "decks": [],
}
# Typy revlog: 0 = nauka, 1 = powtórka, 2 = przeuczenie, 3 = talia filtrowana,
# 4 = ręczna zmiana, 5 = przeplanowanie. Do czasów i liczników bierzemy 0-3.
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
    learning = dict(empty)
    # odid wskazuje talię macierzystą karty wyciągniętej do talii filtrowanej.
    for did, odid, queue, card_type, due, ivl in col.db.all(
        "select did, odid, queue, type, due, ivl from cards where queue != -1"
    ):
        home = odid or did
        if home not in new_left:
            continue
        if queue == 0 or (queue in (-2, -3) and card_type == 0):
            new_left[home] += 1  # zakopane nowe karty wrócą, więc liczą się do zapasu
        elif queue == 1:
            learning[home] += 1
        elif queue in (2, 3):  # tylko tu `due` jest numerem dnia, nie znacznikiem czasu
            offset = int(due) - today
            counts = due_counts[home]
            counts[offset] = counts.get(offset, 0) + 1
            review_cards[home] += 1
            # Karta z interwałem N dni kosztuje 1/N powtórki dziennie.
            reciprocal[home] += 1.0 / max(1, int(ivl or 0))
    return new_left, review_cards, reciprocal, due_counts, learning


def _revlog_data(col, deck_ids):
    """Historia wybranego zakresu, według bieżącej granicy dnia Anki."""
    cutoff = col.sched.day_cutoff * 1000
    today = col.sched.today
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
    daily_reviews = dict.fromkeys(range(today - _TREND_WINDOW_DAYS + 1, today + 1), 0)
    study_days = {}
    learn_answers = reviews_done = 0
    for stamp, cid, kind, milliseconds, ease in rows:
        offset = int((cutoff - 1 - stamp) // 86400000)
        day = today - offset
        active_days.add(day)
        seconds = max(0, milliseconds) / 1000
        if offset < _SECONDS_WINDOW_DAYS and seconds > 0:
            (learn_seconds if kind == 0 else review_seconds).append(seconds)
        first = kind == 0 and cid not in introduced
        if kind == 0:
            learn_answers += 1
            introduced.add(cid)
        else:
            reviews_done += 1
            if day in daily_reviews:
                daily_reviews[day] += 1
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
    return {
        "today": date,
        "learn_seconds": learn_seconds,
        "review_seconds": review_seconds,
        "active_days": len(active_days),
        "daily_reviews": list(daily_reviews.items()),
        "study_days": study_days,
        "new_introduced": len(introduced),
        "learn_answers": learn_answers,
        "reviews_done": reviews_done,
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
    new_left, review_cards, reciprocal, due_counts, learning = _card_data(col, deck_ids)
    with_cards = {
        deck["name"] for deck in decks if new_left[deck["id"]] or due_counts[deck["id"]] or learning[deck["id"]]
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
        "learning_cards": sum(learning.values()),
    }
    snapshot.update(_revlog_data(col, deck_ids))
    return snapshot


# ── Okno raportu ───────────────────────────────────────────────────────────

class ReportDialog(QDialog):
    def __init__(self):
        super().__init__(mw)
        self.setWindowTitle("Anki Toolkit: Workload")
        self.resize(760, 680)
        self.settings = get_config()
        self.snapshot = build_snapshot(mw.col, self.settings)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.minutes = QSpinBox()
        self.minutes.setRange(0, max(self.settings["minutes_per_day"], self.settings["max_minutes_per_day"]))
        self.minutes.setSuffix(" min")
        self.minutes.setValue(self.settings["minutes_per_day"])
        form.addRow("Dziś mam łącznie (tylko w tym oknie):", self.minutes)
        layout.addLayout(form)
        self.view = QTextBrowser()
        layout.addWidget(self.view)
        self.details = QPushButton("Pokaż szczegóły raportu")
        self.details.setCheckable(True)
        self.details.toggled.connect(self.render)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for title, callback in (("Odśwież", self.refresh), ("Kopiuj raport", self.copy_report),
                                ("Ustawienia…", self.open_settings)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addButton(button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.minutes.valueChanged.connect(self.render)
        self.render()

    def render(self, *_):
        self.report = logic.analyze(self.snapshot, self.settings, self.minutes.value())
        html = logic.render_plan_html(self.report)
        if self.details.isChecked():
            html += logic.render_html(self.report)
        self.details.setText("Ukryj szczegóły raportu" if self.details.isChecked() else "Pokaż szczegóły raportu")
        self.view.setHtml(html)

    def refresh(self):
        if mw.col is None:
            self.reject()
            return
        self.snapshot = build_snapshot(mw.col, self.settings)
        self.render()

    def copy_report(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            tooltip("Schowek jest niedostępny.", parent=mw)
            return
        clipboard.setText(logic.render_text(self.report))
        tooltip("Raport skopiowany.", parent=mw)

    def open_settings(self):
        from .settings import open_settings
        if open_settings():
            self.settings = get_config()
            self.minutes.blockSignals(True)
            self.minutes.setMaximum(max(self.settings["minutes_per_day"], self.settings["max_minutes_per_day"]))
            self.minutes.setValue(self.settings["minutes_per_day"])
            self.minutes.blockSignals(False)
            self.refresh()


def show_report():
    if mw.col is None:
        tooltip("Najpierw otwórz profil.", parent=mw)
        return
    ReportDialog().exec()


def _setup(*_args):
    action = QAction("Anki Toolkit: Workload…", mw)
    action.triggered.connect(show_report)
    mw.form.menuTools.addAction(action)


if hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(_setup)
