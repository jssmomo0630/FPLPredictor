import unittest

from monitor_fpl_advice import compare_and_update, preflight


def status(hours=47.5, checked="2026-09-10T06:00:00+00:00", player_status="a"):
    return {
        "checked_at_utc": checked,
        "entry_id": 123,
        "gameweek": {"next": {"id": 4}, "hours_to_deadline": hours},
        "squad": {"players": [{
            "element": 1,
            "availability": "available" if player_status == "a" else "unavailable",
            "status": player_status,
            "chance_of_playing_next_round": None if player_status == "a" else 0,
        }]},
    }


def advice(captain=1, next_chip_gameweek=None, next_chip_gain=5.0):
    chip_advice = {"recommended": None, "next_planned": None}
    if next_chip_gameweek is not None:
        chip_advice["next_planned"] = {
            "chip": "triple_captain",
            "gameweek": next_chip_gameweek,
            "net_gain": next_chip_gain,
        }
    return {
        "target_gameweek": 4,
        "recommendation": {
            "transfers_out": [], "transfers_in": [], "paid_transfers": 0,
            "hit_cost_points": 0, "starting_xi": [{"element": i} for i in range(1, 12)],
            "captain": {"element": captain}, "vice_captain": {"element": 2},
            "bench": [{"element": i} for i in range(12, 16)],
            "chip_advice": chip_advice,
        },
    }


class MonitorTests(unittest.TestCase):
    def test_first_hour_inside_window_runs(self):
        result = preflight(status(), {})
        self.assertTrue(result["should_run"])
        self.assertIn("entered_48h_window", result["reasons"])

    def test_outside_window_does_not_run(self):
        self.assertFalse(preflight(status(hours=48.1), {})["should_run"])

    def test_waits_until_six_hours_after_unchanged_result(self):
        _, state = compare_and_update(status(), advice(), {})
        current = status(checked="2026-09-10T10:00:00+00:00")
        self.assertFalse(preflight(current, state)["should_run"])
        current["checked_at_utc"] = "2026-09-10T12:01:00+00:00"
        self.assertTrue(preflight(current, state)["should_run"])

    def test_owned_injury_triggers_early_rerun(self):
        _, state = compare_and_update(status(), advice(), {})
        injured = status(checked="2026-09-10T07:00:00+00:00", player_status="i")
        result = preflight(injured, state)
        self.assertTrue(result["should_run"])
        self.assertIn("owned_availability_changed", result["reasons"])

    def test_unchanged_recommendation_is_deduplicated(self):
        first, state = compare_and_update(status(), advice(), {})
        second, _ = compare_and_update(status(), advice(), state)
        self.assertTrue(first["should_email"])
        self.assertFalse(second["should_email"])

    def test_changed_recommendation_or_owned_status_emails(self):
        _, state = compare_and_update(status(), advice(), {})
        changed_advice, _ = compare_and_update(status(), advice(captain=3), state)
        self.assertTrue(changed_advice["recommendation_changed"])
        injured = status(player_status="i")
        changed_status, _ = compare_and_update(injured, advice(), state)
        self.assertTrue(changed_status["owned_availability_changed"])
        self.assertTrue(changed_status["should_email"])

    def test_changed_next_chip_slot_is_a_material_recommendation_change(self):
        _, state = compare_and_update(status(), advice(next_chip_gameweek=7), {})
        changed, _ = compare_and_update(
            status(), advice(next_chip_gameweek=10), state
        )
        self.assertTrue(changed["recommendation_changed"])
        self.assertTrue(changed["should_email"])

    def test_small_chip_value_change_does_not_send_a_duplicate(self):
        _, state = compare_and_update(
            status(), advice(next_chip_gameweek=7, next_chip_gain=5.0), {}
        )
        changed, _ = compare_and_update(
            status(), advice(next_chip_gameweek=7, next_chip_gain=5.1), state
        )
        self.assertFalse(changed["recommendation_changed"])
        self.assertFalse(changed["should_email"])


if __name__ == "__main__":
    unittest.main()
