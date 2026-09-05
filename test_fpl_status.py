"""Tests for the read-only FPL status monitor and decision gate."""

import unittest
from datetime import datetime, timedelta, timezone

from check_fpl_status import build_status


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def bootstrap(deadline_hours: float | None, flagged: bool = True) -> dict:
    events = [{
        "id": 2,
        "name": "Gameweek 2",
        "deadline_time": (NOW - timedelta(days=7)).isoformat(),
        "finished": True,
        "data_checked": True,
        "is_current": True,
        "is_next": False,
        "average_entry_score": 52,
        "highest_score": 121,
    }]
    if deadline_hours is not None:
        events.append({
            "id": 3,
            "name": "Gameweek 3",
            "deadline_time": (NOW + timedelta(hours=deadline_hours)).isoformat(),
            "finished": False,
            "data_checked": False,
            "is_current": False,
            "is_next": True,
        })
    return {
        "events": events,
        "teams": [{"id": 1, "name": "Example FC"}],
        "elements": [{
            "id": 10,
            "web_name": "Available",
            "team": 1,
            "element_type": 3,
            "status": "a",
            "chance_of_playing_next_round": None,
            "news": "",
        }, {
            "id": 11,
            "web_name": "Flagged",
            "team": 1,
            "element_type": 2,
            "status": "d" if flagged else "a",
            "chance_of_playing_next_round": 50 if flagged else 100,
            "news": "Late fitness test" if flagged else "",
        }],
    }


PICKS = {"picks": [
    {"element": 10, "position": 1, "is_captain": True, "is_vice_captain": False},
    {"element": 11, "position": 2, "is_captain": False, "is_vice_captain": True},
]}


class FplStatusTests(unittest.TestCase):
    def report(self, deadline_hours: float | None, flagged: bool = True) -> dict:
        return build_status(
            bootstrap(deadline_hours, flagged), PICKS, 123, 2, NOW, "America/Los_Angeles"
        )

    def test_six_hour_window_runs_recommendation(self):
        report = self.report(5)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["decision"]["action"], "run_recommendation")
        self.assertEqual(report["decision"]["trigger_key"], "gw3:deadline_6h")
        self.assertEqual(report["squad"]["availability_counts"]["doubtful"], 1)

    def test_twenty_four_hour_window_runs_preview(self):
        report = self.report(20, flagged=False)
        self.assertEqual(report["decision"]["trigger_key"], "gw3:deadline_24h")
        self.assertEqual(report["gameweek"]["deadline_time_local"], "2026-09-06T01:00:00-07:00")

    def test_far_deadline_reports_availability_only_when_flagged(self):
        self.assertEqual(self.report(48, flagged=True)["decision"]["action"], "send_status_update")
        self.assertEqual(self.report(48, flagged=False)["decision"]["action"], "no_action")

    def test_no_future_deadline_marks_season_complete(self):
        report = self.report(None)
        self.assertEqual(report["decision"]["action"], "season_complete")
        self.assertIsNone(report["gameweek"]["deadline_time_utc"])


if __name__ == "__main__":
    unittest.main()
