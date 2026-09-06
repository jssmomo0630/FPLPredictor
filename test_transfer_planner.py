#!/usr/bin/env python3
"""Regression tests for transfer-state rules."""

import unittest
import json
import tempfile
from pathlib import Path

import pandas as pd

from plan_transfers import _chip_week_values, load_opponent_pairs, load_squad, plan


class TransferPlannerTests(unittest.TestCase):
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
