"""Testy modułu Workload.

Czysta logika i warstwa odczytu (`build_snapshot`) są importowane bezpośrednio
z plików. Odczyt jest testowany na prawdziwej bazie SQLite w pamięci — dzięki
temu zapytania SQL wykonują się naprawdę.
"""

import datetime
import importlib.util
import sqlite3
import types
import unittest
from pathlib import Path

WORKLOAD = Path(__file__).parent.parent / "workload"


def _load(name):
    spec = importlib.util.spec_from_file_location("workload_" + name, WORKLOAD / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = _load("logic")

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

    def test_small_budget_can_pause_decks(self):
        for strategy in (logic.SPLIT_PROPORTIONAL, logic.SPLIT_HEAVIEST_FIRST):
            self.assertEqual(sum(logic.scale_limits({"a": 100, "b": 1}, 1, strategy).values()), 1)
            self.assertEqual(logic.scale_limits({"a": 10, "b": 5}, 0, strategy), {"a": 0, "b": 0})
            self.assertEqual(logic.scale_limits({"a": 2}, 100, strategy), {"a": 2})

    def test_strategy_from_settings_is_used_for_today(self):
        data = snapshot([deck("a", new_per_day=30), deck("b", new_per_day=5)])
        report = logic.analyze(data, {**SETTINGS, "new_cards_per_day": 10,
                                     "split_strategy": logic.SPLIT_HEAVIEST_FIRST})
        self.assertEqual(sum(row.suggested_new_per_day for row in report.decks), 10)
        self.assertEqual(report.decks[1].suggested_new_per_day, 5)


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

class FindingTests(unittest.TestCase):
    def test_high_review_limit_is_not_an_alarm(self):
        report = logic.analyze(snapshot(), SETTINGS)
        self.assertNotIn("Brak sufitu powtórek", [f.title for f in report.findings])
        self.assertIn("Limit sesji nie usuwa zaległości", [f.title for f in report.findings])
        self.assertTrue(all(row.suggested_review_per_day is None for row in report.decks))

    def test_unread_flags_are_reported_not_assumed(self):
        data = snapshot(flags={"fsrs": None}, flag_errors=["fsrs"])
        titles = [f.title for f in logic.analyze(data, SETTINGS).findings]
        self.assertNotIn("FSRS wyłączone", titles)
        self.assertIn("Nie odczytano ustawień kolekcji", titles)


class StudyPlanTests(unittest.TestCase):
    settings = {**SETTINGS, "minutes_per_day": 15, "new_cards_per_day": 3}
    today = datetime.date(2026, 9, 14)  # poniedziałek

    def history(self, count=14, seconds=300, new=3):
        return {(self.today - datetime.timedelta(days=i)).isoformat():
                {"seconds": seconds, "new": new, "answers": 10}
                for i in range(1, count + 1)}

    def report(self, today_minutes=None, **data):
        return logic.analyze(snapshot(today=self.today, **data), self.settings, today_minutes)

    def test_start_short_day_and_long_day(self):
        normal = self.report().plan
        self.assertEqual((normal.today_minutes, normal.weekly_new, normal.new_remaining), (15, 3, 3))
        self.assertEqual(self.report(5).plan.new_remaining, 0)
        self.assertEqual(self.report(0).plan.new_remaining, 0)
        self.assertEqual(self.report(60).plan.new_remaining, 3)
        self.assertEqual(self.report(60).plan.weekly_new, 3)

    def test_today_is_not_a_new_allowance_on_each_open(self):
        history = {self.today.isoformat(): {"seconds": 60, "new": 2, "answers": 5}}
        report = self.report(study_days=history)
        self.assertEqual(report.plan.new_remaining, 1)
        self.assertEqual(sum(row.suggested_new_per_day for row in report.decks), 1)
        history[self.today.isoformat()]["new"] = 3
        self.assertEqual(self.report(study_days=history).plan.new_remaining, 0)
        history[self.today.isoformat()].update(new=0, seconds=15 * 60)
        self.assertEqual(self.report(study_days=history).plan.new_remaining, 0)

    def test_backlog_and_learning_take_priority(self):
        report = self.report(decks=[deck("a", due_counts={-1: 1, 0: 2})])
        self.assertEqual((report.plan.new_remaining, report.plan.weekly_new), (0, 0))
        self.assertEqual(report.plan.due_cards, 3)
        self.assertEqual(self.report(learning_cards=30).plan.new_remaining, 0)
        self.assertEqual(self.report(decks=[deck("a", due_counts={0: 100})]).plan.new_remaining, 0)

    def test_two_complete_weeks_only_offer_one_extra(self):
        history = self.history()
        report = self.report(study_days=history)
        self.assertEqual(report.plan.weekly_new, 4)
        self.assertEqual(report.plan.new_remaining, 3)  # akceptacja wymaga ustawień
        history[self.today.isoformat()] = {"seconds": 600, "new": 20, "answers": 50}
        self.assertEqual(self.report(study_days=history).plan.weekly_new, 4)
        for length in (0, 1, 7):
            self.assertEqual(self.report(study_days=self.history(length)).plan.weekly_new, 3)
        changed = logic.analyze(snapshot(today=self.today, study_days=self.history()),
                                {**self.settings, "new_cards_per_day": 4})
        self.assertEqual(changed.plan.weekly_new, 4)  # nie eskaluje po ponownym otwarciu

    def test_break_overload_and_no_new_material(self):
        self.assertEqual(self.report(active_days=100).plan.weekly_new, 3)
        overloaded = self.report(study_days=self.history(seconds=2000))
        self.assertEqual(overloaded.plan.weekly_new, 2)
        self.assertEqual(overloaded.plan.new_remaining, 2)
        self.assertEqual(self.report(decks=[]).plan.new_remaining, 0)
        self.assertEqual(self.report(decks=[deck("a", new_per_day=0)]).plan.new_remaining, 0)
        paused = logic.analyze(snapshot(), {**self.settings, "new_cards_per_day": 0})
        self.assertEqual(paused.plan.new_remaining, 0)
        self.assertEqual(paused.plan.weekly_new, 0)

    def test_one_binge_or_review_only_history_cannot_raise_pace(self):
        history = self.history()
        history[(self.today - datetime.timedelta(days=1)).isoformat()]["new"] = 30
        self.assertEqual(self.report(study_days=history).plan.weekly_new, 3)
        self.assertEqual(self.report(study_days=self.history(new=0)).plan.weekly_new, 3)

    def test_missing_times_or_full_queue_cannot_raise_pace(self):
        self.assertEqual(self.report(study_days=self.history(seconds=0)).plan.weekly_new, 3)
        self.assertEqual(self.report(study_days=self.history(),
                                     decks=[deck("a", due_counts={0: 200})]).plan.weekly_new, 0)

    def test_difficult_cards_slow_intake_before_backlog(self):
        history = self.history()
        for day in history.values():
            day["again"] = 3  # 30%, 70 odpowiedzi w ostatnim tygodniu
        report = self.report(study_days=history)
        self.assertEqual(report.backlog, 0)
        self.assertEqual((report.plan.weekly_new, report.plan.new_remaining), (2, 2))
        self.assertIn("Ponownie", report.plan.weekly_reason)
        for day in history.values():
            day["again"] = 5
        self.assertEqual(self.report(study_days=history).plan.new_remaining, 0)
        self.assertEqual(self.report(study_days=dict(list(history.items())[:1])).plan.weekly_new, 3)

    def test_flexible_range_holds_pace_between_fifteen_and_thirty(self):
        self.assertEqual(self.report(study_days=self.history(seconds=20 * 60)).plan.weekly_new, 3)
        self.assertEqual(self.report(60).plan.today_minutes, 30)

    def test_copy_contains_the_selected_daily_plan(self):
        text = logic.render_text(self.report(5))
        self.assertIn("Dziś około 5 min", text)
        self.assertIn("Jeszcze najwyżej 0", text)
        self.assertIn("nie zmienia limitów", text)



class RenderTests(unittest.TestCase):
    def test_html_shows_both_load_numbers(self):
        data = snapshot([deck("a", reciprocal_sum=12.0, review_cards=100)])
        html = logic.render_html(logic.analyze(data, SETTINGS))
        self.assertIn("Przybliżenie z interwałów", html)
        self.assertIn("Scenariusz według limitów", html)
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
            "create table cards (id integer primary key, did int, odid int, queue int, type int, due int, ivl int)"
        )
        connection.executemany("insert into cards (did,odid,queue,type,due,ivl) values (?,?,?,?,?,?)", cards)
        connection.execute("create table revlog (id int, cid int, type int, time int, ease int default 3)")
        connection.executemany("insert into revlog (id,cid,type,time) values (?,?,?,?)", revlog)
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
        cls.addon = _load("snapshot")

    def _col(self, cards=(), revlog=(), **kwargs):
        decks = {
            1: {"name": "angielski", "conf": preset("ang", 999)},
            2: {"name": "angielski::a", "conf": preset("a", 10)},
            3: {"name": "filtrowana", "dyn": 1, "conf": preset("f")},
        }
        if revlog and not cards:
            cards = [(2, 0, 2, 2, 105, 10)] * max(row[1] for row in revlog)
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

    def test_recent_card_costs_use_completed_days_and_preserve_plan(self):
        rows = [(day_ms(86), 1, 0, 5000),  # first learning: cohort boundary
                (day_ms(93), 1, 1, 60000),
                (day_ms(99), 1, 2, 30000),
                (day_ms(100), 1, 1, 900000),  # today excluded
                (day_ms(85), 2, 0, 5000),  # older card
                (day_ms(99) + 1, 2, 0, 20000),  # reset is not introduction
                (day_ms(98), 3, 1, 10000),  # missing initial learning
                (day_ms(99) + 2, 3, 4, 999000)]
        col = self._col(revlog=rows)
        col.connection.execute("update revlog set ease = 1 where type = 2")
        data = self.addon.build_snapshot(col, {})
        cost = data["card_costs"]
        self.assertEqual(cost["cohort_cards"], 1)
        self.assertEqual(cost["cohort_seconds"], 90)
        self.assertEqual(cost["total_seconds"], 120)
        self.assertEqual(cost["top"][0], {"cid": 1, "seconds": 90, "answers": 2,
                                          "again": 1, "recent": True})
        report = logic.analyze(data, SETTINGS)
        self.assertIn("75%", logic.render_text(report))
        self.assertIn("cid:1", logic.render_html(report))
        self.assertEqual(report.plan, logic.analyze({**data, "card_costs": {}}, SETTINGS).plan)
        self.assertEqual(self.addon.build_snapshot(col, {"decks": ["missing"]})["card_costs"]["top"], [])

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

    def test_study_history_filters_decks_and_counts_first_learning_only(self):
        cards = [(1, 0, 0, 0, 0, 0), (3, 2, 1, 1, 9999999999, 0)]
        revlog = [(day_ms(99), 1, 0, 900000), (day_ms(99) + 1, 2, 0, 10000),
                  (day_ms(100), 2, 0, 10000), (day_ms(100) + 1, 2, 3, 5000)]
        data = self.addon.build_snapshot(self._col(cards, revlog), {"decks": ["angielski::a"]})
        self.assertEqual(data["learn_seconds"], [10, 10])
        self.assertEqual(data["review_seconds"], [5])
        self.assertEqual(data["new_introduced"], 1)
        current = data["study_days"][data["today"].isoformat()]
        self.assertEqual(current, {"seconds": 15, "answers": 2, "new": 0,
                                   "again": 0, "learning_seconds": 10})
        self.assertEqual(data["learning_cards"], 1)
        empty = self.addon.build_snapshot(self._col(cards, revlog), {"decks": ["missing"]})
        self.assertEqual(empty["study_days"], {})

    def test_again_and_learning_cost_are_read_from_answers(self):
        col = self._col(revlog=[(day_ms(100), 1, 0, 20000),
                               (day_ms(100) + 1, 1, 2, 10000),
                               (day_ms(100) + 2, 1, 1, 5000)])
        col.connection.execute("update revlog set ease = 1 where type = 0")
        data = self.addon.build_snapshot(col, {})
        current = data["study_days"][data["today"].isoformat()]
        self.assertEqual(current["again"], 1)
        self.assertEqual(current["learning_seconds"], 30)
        self.assertEqual(current["seconds"], 35)

    def test_day_rollover_uses_scheduler_cutoff(self):
        col = self._col(revlog=[(day_ms(100) + 3 * 3600000, 1, 0, 10000),
                               (day_ms(100) + 5 * 3600000, 2, 0, 10000)])
        col.sched.day_cutoff += 4 * 3600
        data = self.addon.build_snapshot(col, {})
        current = data["study_days"][data["today"].isoformat()]
        self.assertEqual(current["new"], 1)
        yesterday = (data["today"] - datetime.timedelta(days=1)).isoformat()
        self.assertEqual(data["study_days"][yesterday]["new"], 1)

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
