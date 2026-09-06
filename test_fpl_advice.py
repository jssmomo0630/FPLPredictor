import unittest
from unittest import mock

from build_fpl_advice import build_advice
from summarize_fpl_advice import build_summary


def sample_inputs():
    status = {
        "read_only": True,
        "entry_id": 123,
        "gameweek": {"next": {"id": 4}, "deadline_time_local": "2026-09-12T05:30:00-07:00", "hours_to_deadline": 20},
        "squad": {"source_event_id": 3, "financial": {"bank_units": 7}},
    }
    plan = {
        "initial_free_transfers": 1,
        "selling_price_source": "public_status_current_price_fallback",
        "selling_price_warning": "Fallback prices.",
        "forecast_note": "Forecast only.",
        "weeks": [{
            "gameweek": 4,
            "transfers_used": 1,
            "paid_transfers": 0,
            "hit_cost": 0,
            "bank_after": 5,
            "transfers_out": [{"element": 1, "player_name": "Old", "selling_price": 50}],
            "transfers_in": [{"element": 16, "player_name": "New", "price": 52}],
            "opponent_conflicts": [{
                "defensive_player": "Starter 2", "attacking_player": "Starter 9",
                "penalty_points": 0.15,
            }],
            "opponent_conflict_penalty_points": 0.15,
        }],
        "opponent_conflict_penalty": 0.15,
        "chip_advice": {"recommendation": "Save all chips", "recommended": None, "method_note": "Method."},
    }
    rows = []
    positions = ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"]
    for index, position in enumerate(positions, start=1):
        rows.append({
            "gameweek": "4", "element": str(index + 15), "player_name": f"Starter {index}",
            "position": position, "team_id": str(index), "price": "50", "expected_points": "4.5",
            "role": "starting_xi", "bench_order": "0",
            "is_captain": str(index == 1), "is_vice_captain": str(index == 2),
        })
    for order, position in enumerate(("MID", "DEF", "FWD", "GK"), start=1):
        rows.append({
            "gameweek": "4", "element": str(30 + order), "player_name": f"Bench {order}",
            "position": position, "team_id": str(order), "price": "45", "expected_points": "2.0",
            "role": "bench_gk" if position == "GK" else "bench", "bench_order": str(4 if position == "GK" else order),
            "is_captain": "False", "is_vice_captain": "False",
        })
    return status, plan, rows


class AdviceTests(unittest.TestCase):
    def test_builds_advisory_only_report(self):
        advice = build_advice(*sample_inputs())
        self.assertTrue(advice["advisory_only"])
        self.assertEqual(advice["recommendation"]["headline"], "Make 1 transfer(s): Old → New")
        self.assertEqual(advice["assumptions"]["bank_from_locked_squad_millions"], 0.7)
        self.assertEqual(advice["assumptions"]["free_transfers_assumed"], 1)
        self.assertEqual(len(advice["recommendation"]["starting_xi"]), 11)
        self.assertEqual(advice["recommendation"]["opponent_conflict_penalty_points"], 0.15)

    def test_ai_summary_falls_back_without_key(self):
        advice = build_advice(*sample_inputs())
        result = build_summary(advice, None, "test-model")
        self.assertFalse(result["used_ai"])
        self.assertEqual(result["summary"], advice["deterministic_summary"])

    @mock.patch("summarize_fpl_advice.gemini_summary", return_value="Concise verified summary.")
    def test_ai_summary_is_optional(self, gemini):
        advice = build_advice(*sample_inputs())
        result = build_summary(advice, "secret", "test-model")
        self.assertTrue(result["used_ai"])
        self.assertEqual(result["summary"], "Concise verified summary.")
        gemini.assert_called_once_with(advice, "secret", "test-model")


if __name__ == "__main__":
    unittest.main()
