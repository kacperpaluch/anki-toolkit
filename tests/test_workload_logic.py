"""Testy logiki Workload Service.

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

WORKLOAD = Path(__file__).parent.parent / "workload_service"


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
}


def deck(name, **overrides):
    base = {
        "name": name,
        "new_per_day": 10,
        "new_left": 100,
        "due_counts": {},
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
        "learn_answers": 0,
        "today": datetime.date(2026, 9, 13),
    }
    base.update(overrides)
    return base


class BudgetTests(unittest.TestCase):
    def test_new_card_cost_is_never_negative(self):
        self.assertEqual(logic.new_card_cost(-1, 12.0), 0.0)


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


class MeasurementTests(unittest.TestCase):
    def test_seconds_use_median_not_mean(self):
        report = logic.analyze(snapshot(review_seconds=[1.0, 2.0, 100.0]), {})
        self.assertEqual(report.review_seconds, 2.0)

    def test_empty_history_falls_back(self):
        report = logic.analyze(snapshot(), {})
        self.assertEqual(report.review_seconds, logic.DEFAULT_REVIEW_SECONDS)
        self.assertEqual(report.learn_seconds, logic.DEFAULT_LEARN_SECONDS)
        self.assertEqual(report.learn_answers_per_new_card, logic.DEFAULT_LEARN_ANSWERS_PER_NEW_CARD)

    def test_learn_answers_measured_per_introduced_card(self):
        report = logic.analyze(snapshot(learn_answers=250, new_introduced=100), {})
        self.assertEqual(report.learn_answers_per_new_card, 2.5)

    def test_manual_override_beats_measurement(self):
        report = logic.analyze(snapshot(review_seconds=[30.0] * 10), {**SETTINGS, "seconds_per_card": 5})
        self.assertEqual(report.review_seconds, 5)


class StudyPlanTests(unittest.TestCase):
    settings = {**SETTINGS, "minutes_per_day": 15, "new_cards_per_day": 3}
    today = datetime.date(2026, 9, 14)  # poniedziałek

    def history(self, count=14, seconds=300, new=3):
        return {(self.today - datetime.timedelta(days=i)).isoformat():
                {"seconds": seconds, "new": new, "answers": 10}
                for i in range(1, count + 1)}

    def report(self, **data):
        return logic.analyze(snapshot(today=self.today, **data), self.settings)

    def test_start(self):
        normal = self.report().plan
        self.assertEqual((normal.today_minutes, normal.weekly_new, normal.new_remaining), (15, 3, 3))

    def test_today_is_not_a_new_allowance_on_each_open(self):
        history = {self.today.isoformat(): {"seconds": 60, "new": 2, "answers": 5}}
        report = self.report(study_days=history)
        self.assertEqual(report.plan.new_remaining, 1)
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


# ── Warstwa odczytu z Anki ─────────────────────────────────────────────────

class FakeDecks:
    def __init__(self, decks): self.decks = decks
    def all_names_and_ids(self, skip_empty_default=False):
        return [types.SimpleNamespace(id=did, name=data["name"]) for did, data in self.decks.items()]
    def get(self, did): return self.decks.get(did)
    def config_dict_for_deck_id(self, did): return self.decks[did]["conf"]


class FakeCol:
    """Kolekcja na prawdziwym SQLite — zapytania dodatku wykonują się naprawdę."""

    def __init__(self, decks, cards, revlog, today=100, crt=0):
        self.decks = FakeDecks(decks)
        self.sched = types.SimpleNamespace(today=today, day_cutoff=crt + (today + 1) * 86400)
        self.crt = crt
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "create table cards (id integer primary key, did int, odid int, queue int, type int, due int, ivl int, odue int default 0)"
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



def preset(name, new_per_day=10):
    return {"name": name, "new": {"perDay": new_per_day}}


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

    def test_filtered_deck_card_uses_its_original_due_day(self):
        col = self._col([(3, 2, 2, 2, -100000, 5)])
        col.connection.execute("update cards set odue = 103")
        row = self.addon.build_snapshot(col, {})["decks"][-1]
        self.assertEqual(row["due_counts"], {3: 1})

    def test_interday_learning_due_today_counts_as_learning(self):
        cards = [(2, 0, 3, 1, 100, 0), (2, 0, 3, 3, 99, 4), (2, 0, 3, 3, 104, 4)]
        snapshot = self.addon.build_snapshot(self._col(cards), {})
        row = snapshot["decks"][-1]
        self.assertEqual(snapshot["learning_cards"], 2)
        self.assertEqual(row["due_counts"], {4: 1})

    def test_due_offsets_are_relative_to_today(self):
        cards = [(2, 0, 2, 2, 95, 5), (2, 0, 2, 2, 100, 5), (2, 0, 2, 2, 107, 5)]
        row = self.addon.build_snapshot(self._col(cards), {})["decks"][-1]
        self.assertEqual(row["due_counts"], {-5: 1, 0: 1, 7: 1})

    def test_filtered_deck_card_counts_to_its_home_deck(self):
        cards = [(3, 2, 2, 2, 100, 10)]  # leży w talii filtrowanej, dom to talia 2
        rows = {row["name"]: row for row in self.addon.build_snapshot(self._col(cards), {})["decks"]}
        self.assertNotIn("filtrowana", rows)
        self.assertEqual(rows["angielski::a"]["due_counts"], {0: 1})

    def test_parent_without_own_cards_is_kept_as_ancestor(self):
        cards = [(2, 0, 0, 0, 0, 0)]
        names = [row["name"] for row in self.addon.build_snapshot(self._col(cards), {})["decks"]]
        self.assertEqual(names, ["angielski", "angielski::a"])

    def test_new_limit_comes_from_the_preset_unless_the_deck_overrides_it(self):
        cards = [(2, 0, 0, 0, 0, 0)]
        col = self._col(cards)
        self.assertEqual(self.addon.build_snapshot(col, {})["decks"][-1]["new_per_day"], 10)
        col.decks.decks[2]["newLimit"] = 0
        self.assertEqual(self.addon.build_snapshot(col, {})["decks"][-1]["new_per_day"], 0)

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
        self.assertEqual(report.card_costs, cost)
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

    def test_totals_cover_whole_history(self):
        revlog = [
            (day_ms(1), 1, 0, 5000), (day_ms(1) + 1, 1, 0, 5000),
            (day_ms(2), 2, 0, 5000), (day_ms(3), 1, 1, 5000), (day_ms(4), 1, 2, 5000),
        ]
        data = self.addon.build_snapshot(self._col(revlog=revlog), {})
        self.assertEqual(data["new_introduced"], 2)
        self.assertEqual(data["learn_answers"], 3)

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

    def test_snapshot_feeds_analyze_end_to_end(self):
        cards = [(2, 0, 0, 0, 0, 0)] * 50 + [(2, 0, 2, 2, 103, 10)] * 20
        data = self.addon.build_snapshot(self._col(cards), {})
        report = logic.analyze(data, SETTINGS)
        self.assertEqual(report.new_left_total, 50)
        self.assertEqual(report.backlog, 0)
        self.assertEqual(report.plan.due_cards, 0)


if __name__ == "__main__":
    unittest.main()
