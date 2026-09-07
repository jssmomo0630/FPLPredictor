#!/usr/bin/env python3
"""Regression tests for transfer-state rules."""

import unittest
import json
import tempfile
from pathlib import Path

import pandas as pd

from plan_transfers import (
    _allocate_chip_schedule,
    _chip_week_values,
    _wildcard_reachability,
    advise_chips,
    chip_period_for_gameweek,
    load_opponent_pairs,
    load_squad,
    plan,
    snapshot_used_chips,
)


class TransferPlannerTests(unittest.TestCase):
    def test_wildcard_is_evaluated_only_for_the_current_deadline(self):
        rows = []
        positions = [1, 1, *([2] * 5), *([3] * 5), *([4] * 3)]
        for gameweek in (4, 5):
            for index, position in enumerate(positions, start=1):
                role = (
                    "starting_xi" if index <= 11
                    else ("bench_gk" if index == 12 else "bench")
                )
                rows.append({
                    "gameweek": gameweek,
                    "element": index,
                    "player_name": f"Player {index}",
                    "element_type": position,
                    "team_id": (index - 1) // 3 + 1,
                    "price": 50,
                    "expected_points": 2.0,
                    "role": role,
                    "bench_order": max(0, index - 12),
                    "is_captain": index == 1,
                    "is_vice_captain": index == 2,
                })
        plan_rows = pd.DataFrame(rows)
        report = {
            "initial_squad": list(range(1, 16)),
            "weeks": [
                {
                    "gameweek": gameweek,
                    "bank_after": 0,
                    "hit_cost": 0,
                    "free_transfers_before": 2,
                }
                for gameweek in (4, 5)
            ],
        }
        advice = advise_chips(
            plan_rows,
            plan_rows,
            report,
            available_chips={"wildcard"},
            period_start_gameweek=1,
            period_end_gameweek=19,
            wildcard_horizon=2,
        )
        wildcard_options = [
            row for row in advice["options"] if row["chip"] == "wildcard"
        ]
        self.assertEqual(len(wildcard_options), 1)
        self.assertEqual(wildcard_options[0]["gameweek"], 4)
        self.assertFalse(wildcard_options[0]["eligible"])
        self.assertEqual(advice["tentative_schedule"], [])

    def test_wildcard_target_reachable_with_rolled_free_transfers(self):
        gameweeks = [4, 5, 6]
        plan_rows = pd.DataFrame([
            {"gameweek": gameweek, "element": element}
            for gameweek in gameweeks
            for element in range(1, 16)
        ])
        week_reports = {
            gameweek: {"gameweek": gameweek, "free_transfers_before": 2}
            for gameweek in gameweeks
        }
        assessment = _wildcard_reachability(
            4,
            gameweeks,
            plan_rows,
            week_reports,
            set(range(1, 16)),
            set(range(1, 12)) | {16, 17, 18, 19},
        )
        self.assertEqual(assessment["squad_changes_required"], 4)
        self.assertEqual(assessment["free_transfers_available_over_window"], 4)
        self.assertFalse(assessment["reachable_immediately_without_hits"])
        self.assertTrue(assessment["reachable_within_window_without_hits"])

    def test_wildcard_target_is_not_reachable_when_overhaul_is_large(self):
        gameweeks = [4, 5, 6]
        plan_rows = pd.DataFrame([
            {"gameweek": gameweek, "element": element}
            for gameweek in gameweeks
            for element in range(1, 16)
        ])
        week_reports = {
            gameweek: {"gameweek": gameweek, "free_transfers_before": 1}
            for gameweek in gameweeks
        }
        assessment = _wildcard_reachability(
            4,
            gameweeks,
            plan_rows,
            week_reports,
            set(range(1, 16)),
            set(range(1, 10)) | {16, 17, 18, 19, 20, 21},
        )
        self.assertEqual(assessment["squad_changes_required"], 6)
        self.assertEqual(assessment["free_transfers_available_over_window"], 3)
        self.assertFalse(assessment["reachable_within_window_without_hits"])

    def test_joint_chip_schedule_uses_distinct_gameweeks(self):
        options = [
            {"chip": "triple_captain", "gameweek": 18, "net_gain": 5.0},
            {"chip": "triple_captain", "gameweek": 19, "net_gain": 10.0},
            {"chip": "bench_boost", "gameweek": 18, "net_gain": 4.0},
            {"chip": "bench_boost", "gameweek": 19, "net_gain": 9.0},
        ]
        schedule = _allocate_chip_schedule(
            options,
            {"triple_captain", "bench_boost"},
            [18, 19],
            require_maximum_uses=True,
        )
        self.assertEqual({row["chip"] for row in schedule}, {
            "triple_captain", "bench_boost",
        })
        self.assertEqual({row["gameweek"] for row in schedule}, {18, 19})

    def test_chip_period_changes_at_gameweek_20(self):
        self.assertEqual(chip_period_for_gameweek(19)["number"], 1)
        self.assertEqual(chip_period_for_gameweek(20)["number"], 2)

    def test_used_chips_are_scoped_to_the_active_half(self):
        payload = {
            "squad": {
                "used_chips": [
                    {"name": "wildcard", "event": 6},
                    {"name": "3xc", "event": 22},
                ]
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            first_half = snapshot_used_chips(path, 10)
            second_half = snapshot_used_chips(path, 25)
        self.assertEqual(first_half, {"wildcard"})
        self.assertEqual(second_half, {"triple_captain"})

    def test_chip_advice_does_not_cross_the_active_period_expiry(self):
        rows = []
        for gameweek in (19, 20):
            for index in range(15):
                role = (
                    "starting_xi" if index < 11
                    else ("bench_gk" if index == 11 else "bench")
                )
                rows.append({
                    "gameweek": gameweek,
                    "element": index + 1,
                    "player_name": f"Player {index + 1}",
                    "element_type": (
                        1 if index in (0, 11)
                        else (2 if index < 7 else (3 if index < 12 else 4))
                    ),
                    "team_id": index // 3 + 1,
                    "price": 50,
                    "expected_points": 5.0 if gameweek == 20 else 2.0,
                    "role": role,
                    "bench_order": max(0, index - 11),
                    "is_captain": index == 0,
                    "is_vice_captain": index == 1,
                })
        plan_rows = pd.DataFrame(rows)
        report = {
            "weeks": [
                {"gameweek": 19, "bank_after": 0, "hit_cost": 0},
                {"gameweek": 20, "bank_after": 0, "hit_cost": 0},
            ]
        }
        advice = advise_chips(
            plan_rows,
            plan_rows,
            report,
            available_chips={"triple_captain", "bench_boost"},
            period_start_gameweek=1,
            period_end_gameweek=19,
        )
        self.assertEqual({row["gameweek"] for row in advice["options"]}, {19})
        self.assertTrue(advice["chip_period"]["forecast_reaches_expiry"])
        self.assertEqual(len(advice["tentative_schedule"]), 1)
        self.assertEqual(advice["tentative_schedule"][0]["reserve_value"], 0)
        self.assertEqual(len(advice["unscheduled_chips"]), 1)

    def test_loads_unique_opponent_pairs_for_requested_season(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixtures.csv"
            path.write_text(
                "season,gameweek,team,opponent_team\n"
                "2026-27,4,1,5\n2026-27,4,5,1\n2025-26,4,2,3\n",
                encoding="utf-8",
            )
            pairs = load_opponent_pairs(path, "2026-27", [4, 5])
        self.assertEqual(pairs, {4: {(1, 5)}, 5: set()})

    def test_loads_public_status_squad_and_locked_bank(self):
        positions = [1, 1, *([2] * 5), *([3] * 5), *([4] * 3)]
        forecasts = pd.DataFrame([
            {
                "element": index,
                "price": 45 + index,
                "gameweek": 4,
                "player_name": f"Player {index}",
                "element_type": position,
                "team_id": (index - 1) // 3 + 1,
                "expected_points": 2.0,
            }
            for index, position in enumerate(positions, start=1)
        ])
        payload = {
            "squad": {
                "players": [{"element": index} for index in range(1, 16)],
                "financial": {"bank_units": 8},
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            elements, prices, bank, source = load_squad(path, forecasts, None)
        self.assertEqual(elements, set(range(1, 16)))
        self.assertEqual(bank, 8)
        self.assertEqual(prices[1], 46)
        self.assertEqual(source, "public_status_current_price_fallback")

    def test_chip_values_are_incremental_to_normal_scoring(self):
        rows = []
        for index in range(11):
            rows.append({
                "role": "starting_xi",
                "bench_order": 0,
                "expected_points": 5.0 if index == 0 else 2.0,
                "is_captain": index == 0,
                "is_vice_captain": index == 1,
            })
        rows.append({
            "role": "bench_gk", "bench_order": 4, "expected_points": 4.0,
            "is_captain": False, "is_vice_captain": False,
        })
        rows.extend([
            {
                "role": "bench", "bench_order": order, "expected_points": points,
                "is_captain": False, "is_vice_captain": False,
            }
            for order, points in enumerate((3.0, 2.0, 1.0), start=1)
        ])
        values = _chip_week_values(pd.DataFrame(rows))
        self.assertEqual(values["triple_captain"], 5.0)
        self.assertAlmostEqual(values["bench_boost"], 9.23)

    def test_unused_transfers_roll_to_five_and_stop(self):
        positions = [1, 1, *([2] * 5), *([3] * 5), *([4] * 3)]
        rows = []
        for gameweek in range(1, 5):
            for index, position in enumerate(positions, start=1):
                rows.append({
                    "gameweek": gameweek,
                    "element": index,
                    "player_name": f"Player {index}",
                    "element_type": position,
                    "team_id": (index - 1) // 3 + 1,
                    "price": 50,
                    "expected_points": 1.0,
                })
        forecasts = pd.DataFrame(rows)
        current = set(range(1, 16))
        _, report = plan(
            forecasts, current, {element: 50 for element in current},
            bank=0, free_transfers=2, time_limit=5,
        )
        self.assertEqual([week["transfers_used"] for week in report["weeks"]], [0, 0, 0, 0])
        self.assertEqual(
            [week["free_transfers_after_roll"] for week in report["weeks"]],
            [3, 4, 5, 5],
        )

    def test_reports_soft_penalty_for_opposing_starters(self):
        positions = [1, 1, *([2] * 5), *([3] * 5), *([4] * 3)]
        forecasts = pd.DataFrame([
            {
                "gameweek": 4, "element": index, "player_name": f"Player {index}",
                "element_type": position, "team_id": (index - 1) // 3 + 1,
                "price": 50, "expected_points": 10.0 if index in (3, 13) else 1.0,
            }
            for index, position in enumerate(positions, start=1)
        ])
        current = set(range(1, 16))
        _, report = plan(
            forecasts, current, {element: 50 for element in current},
            bank=0, free_transfers=1, opponent_conflict_penalty=0.15,
            opponent_pairs={4: {(1, 5)}}, time_limit=5,
        )
        conflicts = report["weeks"][0]["opponent_conflicts"]
        self.assertTrue(conflicts)
        self.assertTrue(any(row["defensive_element"] == 3 and row["attacking_element"] == 13 for row in conflicts))
        self.assertAlmostEqual(
            report["weeks"][0]["opponent_conflict_penalty_points"],
            0.15 * len(conflicts),
        )


if __name__ == "__main__":
    unittest.main()
