"""Regression tests for reproducible historical-data bootstrapping."""

import csv
import tempfile
import unittest
from pathlib import Path

from fpl_pipeline_config import historical_source_paths, missing_historical_seasons


def _write_csv(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(columns)


class HistoricalSourceTests(unittest.TestCase):
    def test_nested_vaastav_layout_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(root / "2025-26" / "vaastav" / "players_raw.csv", ["id"])
            _write_csv(root / "2025-26" / "vaastav" / "merged_gw.csv", ["element"])
            self.assertIsNotNone(historical_source_paths(root, "2025-26"))
            self.assertEqual(missing_historical_seasons(root, ["2025-26"]), [])

    def test_legacy_vaastav_layout_requires_position_column(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(root / "2024-25" / "players_raw.csv", ["id"])
            _write_csv(root / "2024-25" / "merged_gw.csv", ["element", "position"])
            self.assertIsNotNone(historical_source_paths(root, "2024-25"))

    def test_legacy_official_snapshot_is_not_historical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_csv(root / "2025-26" / "players_raw.csv", ["id"])
            _write_csv(root / "2025-26" / "merged_gw.csv", ["element", "gameweek"])
            self.assertIsNone(historical_source_paths(root, "2025-26"))
            self.assertEqual(missing_historical_seasons(root, ["2025-26"]), ["2025-26"])


if __name__ == "__main__":
    unittest.main()
