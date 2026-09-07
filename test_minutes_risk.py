"""Focused regression tests for preseason minutes risk and autosubs."""

import unittest

import numpy as np
import pandas as pd

from optimize_squad import _prepare_candidates, optimise
from train_gw1_prior import _minute_probabilities


class MinutesRiskTests(unittest.TestCase):
    def test_probability_hierarchy_is_enforced(self):
        rows = 120
        training = pd.DataFrame({
            "feature": np.linspace(-2, 2, rows),
            "target_appearance": [index % 3 != 0 for index in range(rows)],
            "target_started": [index % 4 != 0 for index in range(rows)],
            "target_played_60": [index % 5 != 0 for index in range(rows)],
        })
        probabilities = _minute_probabilities(training, training, ["feature"])
        appearance = probabilities["appearance_probability"]
        start = probabilities["start_probability"]
        played_60 = probabilities["played_60_probability"]
        self.assertTrue(np.all((0 <= played_60) & (played_60 <= start)))
        self.assertTrue(np.all((start <= appearance) & (appearance <= 1)))

    def test_optimizer_uses_selected_starter_nonappearance_risk(self):
        positions = [1] * 4 + [2] * 10 + [3] * 10 + [4] * 8
        raw = pd.DataFrame({
            "element": range(1, len(positions) + 1),
            "player_name": [f"Player {index}" for index in range(1, len(positions) + 1)],
            "element_type": positions,
            "price": 50,
            "team_id": [(index - 1) // 3 + 1 for index in range(1, len(positions) + 1)],
            "predicted_points_gw1": np.linspace(6, 2, len(positions)),
            "appearance_probability": np.linspace(0.98, 0.65, len(positions)),
        })
        candidates = _prepare_candidates(raw, "predicted_points_gw1")
        squad, report = optimise(candidates, time_limit=5)
        self.assertEqual(
            report["autosub_probability_mode"], "player_nonappearance_risk_iterative"
        )
        probabilities = report["outfield_bench_use_probabilities_by_order"]
        self.assertGreater(probabilities[0], probabilities[1])
        self.assertGreater(probabilities[1], probabilities[2])
        starting_gk = squad[
            squad["role"].eq("starting_xi") & squad["element_type"].eq(1)
        ].iloc[0]
        self.assertAlmostEqual(
            report["bench_goalkeeper_use_probability"],
            1 - starting_gk["appearance_probability"],
        )


if __name__ == "__main__":
    unittest.main()
