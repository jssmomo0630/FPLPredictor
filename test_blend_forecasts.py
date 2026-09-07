"""Regression tests for separating player ability from current opportunity."""

import unittest

import pandas as pd

from blend_forecasts import blend_forecasts


class BlendForecastTests(unittest.TestCase):
    @staticmethod
    def _prior(changed_team: int = 0) -> pd.DataFrame:
        return pd.DataFrame({
            "element": [1],
            "predicted_points_gw1": [4.0],
            "predicted_points_given_appearance_gw1": [5.0],
            "appearance_probability": [0.8],
            "appearance_probability_before_availability": [0.8],
            "start_probability": [0.7],
            "played_60_probability": [0.6],
            "projected_minutes_gw1": [51.0],
            "availability_factor": [1.0],
            "changed_team": [changed_team],
        })

    @staticmethod
    def _current(**overrides) -> pd.DataFrame:
        values = {
            "element": [1],
            "predicted_points_next_gw": [0.4],
            "predicted_points_next_gw_before_availability": [0.4],
            "current_season_minutes": [0.0],
            "availability_factor": [1.0],
            "role_observation_gameweeks": [3],
            "role_appearances": [0],
            "role_starts": [0],
            "role_played_60": [0],
        }
        values.update({key: [value] for key, value in overrides.items()})
        return pd.DataFrame(values)

    def test_zero_minutes_reduces_opportunity_without_erasing_ability(self):
        result = blend_forecasts(self._prior(), self._current()).iloc[0]
        self.assertAlmostEqual(result["blended_points_given_appearance_next_gw"], 5.0)
        self.assertAlmostEqual(result["appearance_probability"], 0.32)
        self.assertAlmostEqual(result["blended_points_next_gw"], 1.6)

    def test_changed_club_weakens_the_old_opportunity_prior(self):
        unchanged = blend_forecasts(self._prior(), self._current()).iloc[0]
        changed = blend_forecasts(self._prior(changed_team=1), self._current()).iloc[0]
        self.assertLess(changed["opportunity_prior_gameweeks"], unchanged["opportunity_prior_gameweeks"])
        self.assertLess(changed["appearance_probability"], unchanged["appearance_probability"])
        self.assertLess(changed["blended_points_next_gw"], unchanged["blended_points_next_gw"])

    def test_current_starts_quickly_confirm_playing_opportunity(self):
        current = self._current(
            current_season_minutes=270,
            predicted_points_next_gw=4.5,
            predicted_points_next_gw_before_availability=4.5,
            role_appearances=3,
            role_starts=3,
            role_played_60=3,
        )
        result = blend_forecasts(self._prior(), current).iloc[0]
        self.assertGreater(result["appearance_probability"], 0.9)
        self.assertGreater(result["start_probability"], 0.85)
        self.assertGreater(result["played_60_probability"], 0.8)

    def test_repeated_cameos_reduce_points_through_role_duration(self):
        current = self._current(
            current_season_minutes=45,
            predicted_points_next_gw=1.0,
            predicted_points_next_gw_before_availability=1.0,
            role_appearances=3,
            role_starts=0,
            role_played_60=0,
        )
        result = blend_forecasts(self._prior(), current).iloc[0]
        self.assertGreater(result["appearance_probability"], 0.8)
        self.assertLess(result["role_duration_factor"], 0.6)
        self.assertLess(result["blended_points_next_gw"], 2.5)

    def test_current_availability_is_applied_after_role_update(self):
        result = blend_forecasts(
            self._prior(), self._current(availability_factor=0.0)
        ).iloc[0]
        self.assertEqual(result["appearance_probability"], 0.0)
        self.assertEqual(result["blended_points_next_gw"], 0.0)


if __name__ == "__main__":
    unittest.main()
