import json
import tempfile
import unittest
from pathlib import Path

from build_weekly_dashboard import build_site, collect_dashboard_data


class WeeklyDashboardTests(unittest.TestCase):
    def _snapshot(self, root, stamp, points, reviewed=False):
        directory = root / '2026-27' / 'gw06' / stamp
        directory.mkdir(parents=True)
        report = {
            'schema_version': 1, 'season': '2026-27', 'gameweek': 6,
            'generated_at_utc': f'2026-10-08T{stamp[9:11]}:00:00+00:00',
            'fixed_xi_expected_points': points,
        }
        (directory / 'recommendation.json').write_text(json.dumps(report), encoding='utf-8')
        if reviewed:
            (directory / 'review-1.json').write_text(json.dumps({'fixed_xi_actual_points': 70}), encoding='utf-8')

    def test_collects_versions_and_latest_gameweek(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._snapshot(root, '20261008T010000Z', 50)
            self._snapshot(root, '20261008T070000Z', 55, reviewed=True)
            data = collect_dashboard_data(root)
            self.assertEqual(len(data['snapshots']), 2)
            self.assertEqual(data['snapshots'][0]['report']['fixed_xi_expected_points'], 55)
            self.assertEqual(data['snapshots'][0]['review']['fixed_xi_actual_points'], 70)
            self.assertEqual(len(data['latest_by_gameweek']), 1)

    def test_builds_static_site_and_empty_site(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'site'
            data = build_site(Path(folder) / 'missing', output, Path('dashboard'))
            self.assertEqual(data['snapshots'], [])
            self.assertTrue((output / 'index.html').is_file())
            self.assertTrue((output / '.nojekyll').is_file())
            parsed = json.loads((output / 'data/dashboard.json').read_text(encoding='utf-8'))
            self.assertEqual(parsed['schema_version'], 1)


if __name__ == '__main__':
    unittest.main()
