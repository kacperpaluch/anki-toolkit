"""Testy dodatku Workload.

Czysta logika jest importowana bezpośrednio z pliku. Warstwa odczytu z Anki
(`build_snapshot`) jest testowana na atrapach `aqt` i na prawdziwej bazie
SQLite w pamięci — dzięki temu zapytania SQL wykonują się naprawdę.
"""

import datetime
import importlib.util
import sqlite3
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "workload_logic", ROOT / "anki_toolkit_workload/logic.py"
)
logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logic)

SETTINGS = {
    "minutes_per_day": 30,
    "seconds_per_card": 9,
    "learn_seconds_per_card": 12,
    "learn_answers_per_new_card": 2.5,
    "reviews_per_new_card": 10,
    "forecast_days": 60,
}


def deck(name, **overrides):
    base = {
        "name": name,
        "preset": name.split("::")[-1],
        "new_per_day": 10,
        "review_per_day": 9999,
        "new_left": 100,
        "review_cards": 0,
        "reciprocal_sum": 0.0,
        "due_counts": {},
        "easy_days": [1.0] * 7,
    }
    base.update(overrides)
    return base


def snapshot(decks=None, **overrides):
    base = {
        "decks": decks if decks is not None else [deck("a"), deck("b", new_per_day=5)],
        "review_seconds": [],
        "learn_seconds": [],
        "active_days": 0,
        "new_introduced": 0,
        "reviews_done": 0,
        "learn_answers": 0,
        "daily_reviews": [],
        "flags": {},
        "flag_errors": [],
        "today": datetime.date(2026, 9, 13),
    }
    base.update(overrides)
    return base


class BudgetTests(unittest.TestCase):
    def test_new_cards_consume_the_budget_before_reviews(self):
        # 30 min = 1800 s. 20 nowych kart × 2.5 × 12 s = 600 s zostaje 1200 s.
        self.assertEqual(logic.ceiling_from_minutes(30, 9.0), 200)
        self.assertEqual(logic.ceiling_from_minutes(30, 9.0, 20, 2.5, 12.0), 133)

    def test_intake_can_eat_the_whole_budget(self):
        self.assertEqual(logic.ceiling_from_minutes(30, 9.0, 100, 2.5, 12.0), 0)

    def test_zero_inputs_do_not_crash(self):
        self.assertEqual(logic.ceiling_from_minutes(0, 9.0), 0)
        self.assertEqual(logic.ceiling_from_minutes(30, 0), 0)

    def test_suggested_intake_includes_both_costs(self):
        # Koszt jednej nowej karty dziennie: 10 × 9 s powtórek + 2.5 × 12 s nauki.
        self.assertEqual(logic.suggest_new_per_day(30, 9.0, 10.0, 2.5, 12.0), 15)
        # Bez kosztu nauki wychodzi klasyczne 20.
        self.assertEqual(logic.suggest_new_per_day(30, 9.0, 10.0), 20)

    def test_new_card_cost_is_never_negative(self):
        self.assertEqual(logic.new_card_cost(-1, 12.0), 0.0)


class StructuralLoadTests(unittest.TestCase):
    def test_load_is_the_sum_of_interval_reciprocals(self):
        # Karta co 10 dni to 0.1 powtórki dziennie, karta co 2 dni to 0.5.
        self.assertAlmostEqual(logic.structural_load(0.1 + 0.5), 0.6)

    def test_load_is_reported_per_deck_and_summed(self):
        data = snapshot([
            deck("a", reciprocal_sum=1.5, review_cards=10),
            deck("b", reciprocal_sum=2.5, review_cards=20),
        ])
        report = logic.analyze(data, SETTINGS)
        self.assertEqual(report.structural_load, 4)
        self.assertEqual([row.structural_load for row in report.decks], [1.5, 2.5])

    def test_load_above_ceiling_is_an_alert(self):
        data = snapshot([deck("a", new_left=0, reciprocal_sum=500.0, review_per_day=100)])
        titles = [f.title for f in logic.analyze(data, SETTINGS).findings]
        self.assertIn("Już teraz powyżej sufitu", titles)


class SplitTests(unittest.TestCase):
    def test_proportional_keeps_ratios_and_hits_target(self):
        result = logic.scale_limits({"a": 10, "b": 5, "c": 5}, 10)
        self.assertEqual(sum(result.values()), 10)
        self.assertGreater(result["a"], result["b"])

    def test_heaviest_first_leaves_small_decks_alone(self):
        result = logic.scale_limits(
            {"duża": 30, "mała": 5}, 20, logic.SPLIT_HEAVIEST_FIRST
        )
        self.assertEqual(result["mała"], 5)
        self.assertEqual(result["duża"], 15)

    def test_heaviest_first_is_deterministic_on_ties(self):
        first = logic.scale_limits({"a": 10, "b": 10}, 15, logic.SPLIT_HEAVIEST_FIRST)
        second = logic.scale_limits({"b": 10, "a": 10}, 15, logic.SPLIT_HEAVIEST_FIRST)
        self.assertEqual(first, second)

    def test_every_deck_keeps_at_least_one_card(self):
        result = logic.scale_limits({"a": 100, "b": 1}, 3)
        self.assertEqual(result["b"], 1)
        self.assertTrue(all(value >= 1 for value in result.values()))

    def test_strategy_from_settings_is_used(self):
        data = snapshot([deck("a", new_per_day=30), deck("b", new_per_day=5)])
        report = logic.analyze(data, {**SETTINGS, "split_strategy": logic.SPLIT_HEAVIEST_FIRST})
        proposals = {row.name: row.suggested_new_per_day for row in report.decks}
        self.assertEqual(proposals["b"], 5)


class ReviewCeilingSplitTests(unittest.TestCase):
    def test_root_gets_the_whole_ceiling_and_children_a_share(self):
        data = snapshot([
            deck("angielski", new_per_day=999, new_left=0, due_counts={1: 1}),
            deck("angielski::a", new_per_day=10),
            deck("angielski::b", new_per_day=5),
        ])
        report = logic.analyze(data, SETTINGS)
        rows = {row.name: row for row in report.decks}
        self.assertTrue(rows["angielski"].is_root)
        self.assertFalse(rows["angielski::a"].is_root)
        self.assertEqual(rows["angielski"].suggested_review_per_day, report.ceiling)
        self.assertLess(rows["angielski::a"].suggested_review_per_day, report.ceiling)
        self.assertGreater(
            rows["angielski::a"].suggested_review_per_day,
            rows["angielski::b"].suggested_review_per_day,
        )

    def test_finding_warns_that_equal_ceilings_do_not_cap_the_total(self):
        data = snapshot([
            deck("angielski", new_per_day=999, new_left=0, due_counts={1: 1}),
            deck("angielski::a", new_per_day=10),
        ])
        detail = next(
            f.detail for f in logic.analyze(data, SETTINGS).findings
            if f.title == "Brak sufitu powtórek"
        )
        self.assertIn("nie ogranicza sumy", detail)
        self.assertIn("z których się uczysz", detail)

    def test_deck_without_parent_in_report_is_its_own_root(self):
        report = logic.analyze(snapshot([deck("angielski::a")]), SETTINGS)
        self.assertEqual(report.roots, ["angielski::a"])


class ForecastTests(unittest.TestCase):
    def test_overdue_cards_land_on_day_zero(self):
        forecast = dict(logic.forecast_from_counts({-5: 2, -1: 1, 0: 1, 2: 1}, 7))
        self.assertEqual(forecast[0], 4)
        self.assertEqual(forecast[2], 1)

    def test_cards_beyond_window_are_dropped(self):
        forecast = dict(logic.forecast_from_counts({3: 1, 99: 1}, 7))
        self.assertEqual(sum(forecast.values()), 1)

    def test_backlog_counts_only_overdue(self):
        self.assertEqual(logic.backlog_from_counts({-2: 1, -1: 3, 0: 5}), 4)

    def test_cumulative_adds_up_to_the_day(self):
        forecast = logic.forecast_from_counts({0: 1, 1: 2, 9: 1}, 30)
        self.assertEqual(logic.cumulative_at(forecast, 1), 3)
        self.assertEqual(logic.cumulative_at(forecast, 30), 4)

    def test_marks_stop_at_the_window_edge(self):
        marks = logic.forecast_marks(logic.forecast_from_counts({1: 1}, 14))
        self.assertEqual([day for day, _, _ in marks], [1, 3, 7, 14])


class MeasurementTests(unittest.TestCase):
    def test_short_history_falls_back_to_manual_rule(self):
        ratio, source = logic.measured_ratio(10, 100, 50)
        self.assertEqual(ratio, logic.DEFAULT_REVIEWS_PER_NEW_CARD)
        self.assertEqual(source, "domyślne")

    def test_ratio_needs_active_study_days_not_calendar_days(self):
        self.assertEqual(logic.measured_ratio(200, 100, 900), (9.0, "zmierzone"))
        self.assertEqual(
            logic.measured_ratio(59, 100, 900)[1], "domyślne"
        )

    def test_seconds_use_median_not_mean(self):
        self.assertEqual(logic.measured_seconds([1.0, 2.0, 100.0], 9.0), (2.0, "zmierzone"))

    def test_empty_history_falls_back(self):
        self.assertEqual(logic.measured_seconds([], 9.0), (9.0, "domyślne"))
        self.assertEqual(
            logic.measured_learn_answers(0, 0),
            (logic.DEFAULT_LEARN_ANSWERS_PER_NEW_CARD, "domyślne"),
        )

    def test_learn_answers_measured_per_introduced_card(self):
        self.assertEqual(logic.measured_learn_answers(250, 100), (2.5, "zmierzone"))

    def test_manual_override_beats_measurement(self):
        data = snapshot(review_seconds=[30.0] * 10, active_days=100,
                        new_introduced=10, reviews_done=100)
        report = logic.analyze(data, {**SETTINGS, "seconds_per_card": 5})
        self.assertEqual(report.review_seconds, 5)
        self.assertEqual(report.review_seconds_source, "ustawione ręcznie")


class TrendTests(unittest.TestCase):
    def test_no_trend_before_enough_active_days(self):
        points = [(day, day) for day in range(20)]
        self.assertIsNone(logic.measured_trend(points, 5, 100).slope)

    def test_rising_trend_predicts_the_crossing_date(self):
        points = [(day, 10 * day) for day in range(10)]
        trend = logic.measured_trend(points, 30, 200, datetime.date(2026, 9, 13))
        self.assertAlmostEqual(trend.slope, 10.0, places=6)
        # Poziom to średnia z ostatnich 7 dni (30..90) = 60, więc (200-60)/10 = 14.
        self.assertEqual(trend.days_to_ceiling, 14)
        self.assertEqual(trend.date_of_ceiling, datetime.date(2026, 9, 27))

    def test_flat_trend_gives_no_crossing(self):
        points = [(day, 50) for day in range(14)]
        trend = logic.measured_trend(points, 30, 200)
        self.assertIsNone(trend.days_to_ceiling)

    def test_level_above_ceiling_crosses_today(self):
        points = [(day, 300) for day in range(14)]
        points[-1] = (13, 400)
        trend = logic.measured_trend(points, 30, 200, datetime.date(2026, 9, 13))
        self.assertEqual(trend.days_to_ceiling, 0)

    def test_trend_finding_names_the_date(self):
        data = snapshot(
            [deck("a", new_left=0, new_per_day=0, review_per_day=100, reciprocal_sum=5.0)],
            active_days=40,
            daily_reviews=[(day, 5 * day) for day in range(20)],
        )
        detail = next(
            (f.detail for f in logic.analyze(data, SETTINGS).findings
             if f.title == "Obciążenie rośnie"), ""
        )
        self.assertIn("przebijesz za", detail)


class FindingTests(unittest.TestCase):
    def test_missing_ceiling_is_flagged(self):
        titles = [f.title for f in logic.analyze(snapshot(), SETTINGS).findings]
        self.assertIn("Brak sufitu powtórek", titles)

    def test_intake_above_capacity_gets_a_per_deck_proposal(self):
        data = snapshot([deck("a", new_per_day=30), deck("b", new_per_day=5)])
        report = logic.analyze(data, SETTINGS)
        self.assertEqual(report.new_total, 35)
        self.assertEqual(report.suggested_new_total, 15)
        self.assertEqual(sum(row.suggested_new_per_day for row in report.decks), 15)

    def test_decks_without_new_cards_do_not_inflate_intake(self):
        data = snapshot([
            deck("a", new_per_day=10), deck("b", new_per_day=5),
            deck("parent", new_per_day=999, new_left=0, due_counts={1: 1}),
        ])
        self.assertEqual(logic.analyze(data, SETTINGS).new_total, 15)

    def test_backlog_above_ceiling_is_an_alert(self):
        data = snapshot([deck("d", new_per_day=1, review_per_day=100,
                              due_counts={-1: 300})])
        report = logic.analyze(data, SETTINGS)
        self.assertEqual(report.backlog, 300)
        self.assertIn("Zaległości", [f.title for f in report.findings if f.level == "alert"])

    def test_intake_eating_whole_budget_is_an_alert(self):
        data = snapshot([deck("d", new_per_day=200, review_per_day=100)])
        titles = [f.title for f in logic.analyze(data, SETTINGS).findings]
        self.assertIn("Nowe karty zjadają cały czas", titles)

    def test_brake_is_explained_when_switched_off(self):
        data = snapshot(flags={"newCardsIgnoreReviewLimit": False})
        titles = [f.title for f in logic.analyze(data, SETTINGS).findings]
        self.assertIn("Hamulec działa", titles)

    def test_brake_switched_on_is_an_alert(self):
        data = snapshot(flags={"newCardsIgnoreReviewLimit": True})
        findings = logic.analyze(data, SETTINGS).findings
        self.assertIn("Hamulec wyłączony", [f.title for f in findings if f.level == "alert"])

    def test_unread_flags_are_reported_not_assumed(self):
        data = snapshot(flags={"fsrs": None}, flag_errors=["fsrs"])
        titles = [f.title for f in logic.analyze(data, SETTINGS).findings]
        self.assertNotIn("FSRS wyłączone", titles)
        self.assertIn("Nie odczytano ustawień kolekcji", titles)

    def test_easy_days_are_reported(self):
        data = snapshot([deck("a", easy_days=[1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.0])])
        detail = next(
            f.detail for f in logic.analyze(data, SETTINGS).findings
            if f.title == "Dni łatwe zmieniają sufit"
        )
        self.assertIn("sobota", detail)
        self.assertIn("niedziela", detail)

    def test_parent_gap_only_with_limits_from_top(self):
        decks = [
            deck("angielski", new_per_day=999, new_left=0, due_counts={1: 1}),
            deck("angielski::a", new_per_day=10),
        ]
        without = logic.analyze(snapshot(decks), SETTINGS)
        with_flag = logic.analyze(
            snapshot(decks, flags={"applyAllParentLimits": True}), SETTINGS
        )
        self.assertNotIn(
            "Talia nadrzędna szersza niż podtalie", [f.title for f in without.findings]
        )
        self.assertIn(
            "Talia nadrzędna szersza niż podtalie", [f.title for f in with_flag.findings]
        )

    def test_healthy_collection_reports_no_issues(self):
        data = snapshot(
            [deck("d", new_per_day=10, review_per_day=100, new_left=100,
                  reciprocal_sum=20.0, due_counts={1: 5, 2: 5})],
            active_days=200, new_introduced=100, reviews_done=900,
            learn_answers=250, review_seconds=[9.0] * 50, learn_seconds=[12.0] * 50,
            flags={"newCardsIgnoreReviewLimit": False, "fsrs": True,
                   "loadBalancerEnabled": True},
            daily_reviews=[(day, 60) for day in range(28)],
        )
        report = logic.analyze(data, {**SETTINGS, "seconds_per_card": 0,
                                      "learn_seconds_per_card": 0,
                                      "learn_answers_per_new_card": 0,
                                      "reviews_per_new_card": 0})
        self.assertEqual([f.level for f in report.findings if f.level in ("alert", "warn")], [])
        self.assertEqual(report.findings[0].title, "Bez uwag")


class RenderTests(unittest.TestCase):
    def test_html_shows_both_load_numbers(self):
        data = snapshot([deck("a", reciprocal_sum=12.0, review_cards=100)])
        html = logic.render_html(logic.analyze(data, SETTINGS))
        self.assertIn("Teraz — pomiar", html)
        self.assertIn("Docelowo — projekcja", html)
        self.assertIn("tylko czyta kolekcję", html)

    def test_text_version_is_copyable_plain_text(self):
        text = logic.render_text(logic.analyze(snapshot(), SETTINGS))
        self.assertNotIn("<", text)
        self.assertIn("Anki Toolkit: Workload", text)
        self.assertIn("Uwagi:", text)


class AncestorTests(unittest.TestCase):
    def test_returns_every_parent_level(self):
        self.assertEqual(
            logic.ancestors("angielski::preston::ang-pol"),
            ["angielski", "angielski::preston"],
        )

    def test_top_level_deck_has_no_parents(self):
        self.assertEqual(logic.ancestors("angielski"), [])


# ── Warstwa odczytu z Anki ─────────────────────────────────────────────────

def _stub_aqt():
    """Minimalne atrapy `aqt`, żeby dało się zaimportować pakiet dodatku."""
    if "aqt" in sys.modules:
        return
    qt = types.ModuleType("aqt.qt")
    for name in ("QAction", "QApplication", "QDialog", "QDialogButtonBox",
                 "QPushButton", "QTextBrowser", "QVBoxLayout", "QComboBox",
                 "QDoubleSpinBox", "QFormLayout", "QLabel", "QLineEdit", "QSpinBox"):
        setattr(qt, name, type(name, (), {}))
    utils = types.ModuleType("aqt.utils")
    utils.tooltip = lambda *args, **kwargs: None
    aqt = types.ModuleType("aqt")
    aqt.mw = types.SimpleNamespace(col=None, addonManager=None, form=None)
    aqt.gui_hooks = types.SimpleNamespace()
    aqt.qt = qt
    aqt.utils = utils
    sys.modules.update({"aqt": aqt, "aqt.qt": qt, "aqt.utils": utils})


class FakeDecks:
    def __init__(self, decks): self.decks = decks
    def all_names_and_ids(self, skip_empty_default=False):
        return [types.SimpleNamespace(id=did, name=data["name"]) for did, data in self.decks.items()]
    def get(self, did): return self.decks.get(did)
    def config_dict_for_deck_id(self, did): return self.decks[did]["conf"]


class FakeCol:
    """Kolekcja na prawdziwym SQLite — zapytania dodatku wykonują się naprawdę."""

    def __init__(self, decks, cards, revlog, today=100, crt=0, flags=None, raising=()):
        self.decks = FakeDecks(decks)
        self.sched = types.SimpleNamespace(today=today, day_cutoff=crt + (today + 1) * 86400)
        self.crt = crt
        self._flags = flags or {}
        self._raising = raising
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "create table cards (did int, odid int, queue int, type int, due int, ivl int)"
        )
        connection.executemany("insert into cards values (?,?,?,?,?,?)", cards)
        connection.execute("create table revlog (id int, cid int, type int, time int)")
        connection.executemany("insert into revlog values (?,?,?,?)", revlog)
        self.connection = connection
        self.db = types.SimpleNamespace(
            all=lambda sql, *args: connection.execute(sql, args).fetchall(),
            scalar=lambda sql, *args: connection.execute(sql, args).fetchone()[0],
            list=lambda sql, *args: [row[0] for row in connection.execute(sql, args)],
        )

    def get_config(self, key, default=None):
        if key in self._raising:
            raise RuntimeError("API się zmieniło")
        return self._flags.get(key, default)


def preset(name, new_per_day=10, review_per_day=9999, easy_days=None):
    return {
        "name": name,
        "new": {"perDay": new_per_day},
        "rev": {"perDay": review_per_day},
        "easyDaysPercentages": easy_days or [1.0] * 7,
    }


def day_ms(day, crt=0): return (crt + day * 86400) * 1000 + 1


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _stub_aqt()
        sys.path.insert(0, str(ROOT))
        import anki_toolkit_workload
        cls.addon = anki_toolkit_workload

    def _col(self, cards=(), revlog=(), **kwargs):
        decks = {
            1: {"name": "angielski", "conf": preset("ang", 999)},
            2: {"name": "angielski::a", "conf": preset("a", 10)},
            3: {"name": "filtrowana", "dyn": 1, "conf": preset("f")},
        }
        col = FakeCol(decks, list(cards), list(revlog), **kwargs)
        self.addCleanup(col.connection.close)
        return col

    def test_new_pool_includes_buried_new_cards_but_not_suspended(self):
        cards = [
            (2, 0, 0, 0, 0, 0),    # nowa
            (2, 0, -2, 0, 0, 0),   # zakopana nowa — wróci, więc liczy się
            (2, 0, -1, 0, 0, 0),   # zawieszona — pomijana
        ]
        row = self.addon.build_snapshot(self._col(cards), {})["decks"][-1]
        self.assertEqual(row["new_left"], 2)

    def test_structural_load_from_intervals(self):
        cards = [(2, 0, 2, 2, 105, 10), (2, 0, 2, 2, 102, 2)]
        row = self.addon.build_snapshot(self._col(cards), {})["decks"][-1]
        self.assertAlmostEqual(row["reciprocal_sum"], 0.6)
        self.assertEqual(row["review_cards"], 2)

    def test_due_offsets_are_relative_to_today(self):
        cards = [(2, 0, 2, 2, 95, 5), (2, 0, 2, 2, 100, 5), (2, 0, 2, 2, 107, 5)]
        row = self.addon.build_snapshot(self._col(cards), {})["decks"][-1]
        self.assertEqual(row["due_counts"], {-5: 1, 0: 1, 7: 1})

    def test_zero_interval_does_not_divide_by_zero(self):
        cards = [(2, 0, 3, 3, 100, 0)]
        row = self.addon.build_snapshot(self._col(cards), {})["decks"][-1]
        self.assertEqual(row["reciprocal_sum"], 1.0)

    def test_filtered_deck_card_counts_to_its_home_deck(self):
        cards = [(3, 2, 2, 2, 100, 10)]  # leży w talii filtrowanej, dom to talia 2
        rows = {row["name"]: row for row in self.addon.build_snapshot(self._col(cards), {})["decks"]}
        self.assertNotIn("filtrowana", rows)
        self.assertEqual(rows["angielski::a"]["review_cards"], 1)

    def test_parent_without_own_cards_is_kept_as_ancestor(self):
        cards = [(2, 0, 0, 0, 0, 0)]
        names = [row["name"] for row in self.addon.build_snapshot(self._col(cards), {})["decks"]]
        self.assertEqual(names, ["angielski", "angielski::a"])

    def test_limits_and_easy_days_come_from_the_preset(self):
        cards = [(2, 0, 0, 0, 0, 0)]
        row = self.addon.build_snapshot(self._col(cards), {})["decks"][-1]
        self.assertEqual((row["new_per_day"], row["review_per_day"]), (10, 9999))
        self.assertEqual(row["preset"], "a")
        self.assertEqual(len(row["easy_days"]), 7)

    def test_deck_filter_from_settings(self):
        cards = [(2, 0, 0, 0, 0, 0)]
        empty = self.addon.build_snapshot(self._col(cards), {"decks": ["nie ma takiej"]})
        self.assertEqual(empty["decks"], [])

    def test_learning_and_review_times_are_separated(self):
        revlog = [
            (day_ms(99), 1, 0, 12000), (day_ms(99) + 1, 1, 0, 14000),
            (day_ms(99) + 2, 2, 1, 8000), (day_ms(99) + 3, 2, 2, 10000),
            (day_ms(99) + 4, 2, 4, 99000),  # ręczna zmiana — pomijana
        ]
        data = self.addon.build_snapshot(self._col(revlog=revlog), {})
        self.assertEqual(sorted(data["learn_seconds"]), [12.0, 14.0])
        self.assertEqual(sorted(data["review_seconds"]), [8.0, 10.0])

    def test_active_days_counts_distinct_study_days(self):
        revlog = [(day_ms(10), 1, 1, 5000), (day_ms(10) + 5, 1, 1, 5000), (day_ms(40), 1, 1, 5000)]
        self.assertEqual(self.addon.build_snapshot(self._col(revlog=revlog), {})["active_days"], 2)

    def test_daily_reviews_fill_gaps_with_zeros(self):
        revlog = [(day_ms(100), 1, 1, 5000), (day_ms(100) + 1, 2, 1, 5000)]
        data = self.addon.build_snapshot(self._col(revlog=revlog), {})
        daily = dict(data["daily_reviews"])
        self.assertEqual(daily[100], 2)
        self.assertEqual(daily[99], 0)
        self.assertEqual(len(daily), 28)

    def test_totals_cover_whole_history(self):
        revlog = [
            (day_ms(1), 1, 0, 5000), (day_ms(1) + 1, 1, 0, 5000),
            (day_ms(2), 2, 0, 5000), (day_ms(3), 1, 1, 5000), (day_ms(4), 1, 2, 5000),
        ]
        data = self.addon.build_snapshot(self._col(revlog=revlog), {})
        self.assertEqual(data["new_introduced"], 2)
        self.assertEqual(data["learn_answers"], 3)
        self.assertEqual(data["reviews_done"], 2)

    def test_missing_flag_is_none_and_not_an_error(self):
        data = self.addon.build_snapshot(self._col(), {})
        self.assertIsNone(data["flags"]["fsrs"])
        self.assertEqual(data["flag_errors"], [])

    def test_failed_flag_read_is_reported(self):
        col = self._col(flags={"fsrs": True}, raising=("loadBalancerEnabled",))
        data = self.addon.build_snapshot(col, {})
        self.assertTrue(data["flags"]["fsrs"])
        self.assertEqual(data["flag_errors"], ["loadBalancerEnabled"])

    def test_snapshot_feeds_analyze_end_to_end(self):
        cards = [(2, 0, 0, 0, 0, 0)] * 50 + [(2, 0, 2, 2, 103, 10)] * 20
        data = self.addon.build_snapshot(self._col(cards), {})
        report = logic.analyze(data, SETTINGS)
        self.assertEqual(report.new_left_total, 50)
        self.assertEqual(report.structural_load, 2)
        self.assertEqual(report.roots, ["angielski"])
        self.assertIn("Workload", logic.render_text(report))


if __name__ == "__main__":
    unittest.main()


class PluralTests(unittest.TestCase):
    def test_polish_numeral_forms(self):
        self.assertEqual(logic.reviews(1), "1 powtórka")
        self.assertEqual(logic.reviews(3), "3 powtórki")
        self.assertEqual(logic.reviews(5), "5 powtórek")
        self.assertEqual(logic.reviews(83), "83 powtórki")

    def test_teens_use_the_genitive_form(self):
        self.assertEqual(logic.cards(12), "12 kart")
        self.assertEqual(logic.cards(13), "13 kart")
        self.assertEqual(logic.cards(22), "22 karty")

    def test_days_and_new_cards(self):
        self.assertEqual(logic.days(1), "1 dzień")
        self.assertEqual(logic.days(2), "2 dni")
        self.assertEqual(logic.new_cards(1), "1 nowa karta")
        self.assertEqual(logic.new_cards(15), "15 nowych kart")
        self.assertEqual(logic.new_cards(22), "22 nowe karty")

    def test_report_text_uses_inflected_forms(self):
        data = snapshot([deck("a", new_per_day=10, new_left=100, reciprocal_sum=3.0)])
        text = logic.render_text(logic.analyze(data, SETTINGS))
        self.assertIn("3 powtórki na dzień", text)
        self.assertNotIn("3 powtórek", text)
        # „Maksymalna liczba powtórek/dzień” to nazwa ustawienia w Anki i zostaje.
        self.assertIn("Maksymalna liczba powtórek/dzień", text)
