import json
import tempfile
import unittest
from pathlib import Path

from run_fpl_pipeline import _target_gameweek_from_status


class PipelineTargetTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
