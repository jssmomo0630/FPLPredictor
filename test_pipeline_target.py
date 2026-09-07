import json
import tempfile
import unittest
from pathlib import Path

from run_fpl_pipeline import (
    _automated_planning_horizon,
    _chip_period_end,
    _free_transfers_from_status,
    _target_gameweek_from_status,
)


class PipelineTargetTests(unittest.TestCase):
    def test_chip_period_end_uses_the_active_half(self):
        self.assertEqual(_chip_period_end(4), 19)
        self.assertEqual(_chip_period_end(19), 19)
        self.assertEqual(_chip_period_end(20), 38)

    def test_automated_planning_horizon_is_rolling_and_stops_at_chip_expiry(self):
        self.assertEqual(_automated_planning_horizon(4), 5)
        self.assertEqual(_automated_planning_horizon(17), 3)
        self.assertEqual(_automated_planning_horizon(19), 1)
        self.assertEqual(_automated_planning_horizon(20), 5)
        self.assertEqual(_automated_planning_horizon(36), 3)
        self.assertEqual(_automated_planning_horizon(38), 1)

    def test_reads_upcoming_deadline_gameweek_from_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps({"gameweek": {"next": {"id": 4}}}), encoding="utf-8")
            self.assertEqual(_target_gameweek_from_status(str(path)), 4)

    def test_ignores_non_status_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "squad.json"
            path.write_text(json.dumps({"picks": []}), encoding="utf-8")
            self.assertIsNone(_target_gameweek_from_status(str(path)))

    def test_reads_inferred_free_transfers_from_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps({
                "squad": {"financial": {"free_transfers": 2}}
            }), encoding="utf-8")
            self.assertEqual(_free_transfers_from_status(str(path)), 2)


if __name__ == "__main__":
    unittest.main()
