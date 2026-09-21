import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from check_weekly_dashboard import evaluate


class WeeklyDashboardGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
        self.bootstrap = {'events': [
            {'id': 5, 'deadline_time': '2026-09-20T10:00:00Z', 'data_checked': True},
            {'id': 6, 'deadline_time': '2026-09-26T10:00:00Z', 'data_checked': False},
        ]}

    def _snapshot(self, root, gameweek, generated, reviewed=False):
        folder = root / '2026-27' / f'gw{gameweek:02d}' / generated.replace(':', '')
        folder.mkdir(parents=True)
        (folder / 'recommendation.json').write_text(json.dumps({
            'season': '2026-27', 'gameweek': gameweek, 'generated_at_utc': generated,
        }), encoding='utf-8')
        if reviewed:
            (folder / 'review-test.json').write_text('{}', encoding='utf-8')

    def test_generates_once_in_window_after_previous_gameweek_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = evaluate(self.bootstrap, root, self.now)
            self.assertTrue(result['should_generate'])
            self.assertTrue(result['previous_gameweek_closed'])
            self._snapshot(root, 6, '2026-09-24T10:00:00+00:00')
            self.assertFalse(evaluate(self.bootstrap, root, self.now)['should_generate'])

    def test_waits_for_previous_gameweek_and_ignores_early_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.bootstrap['events'][0]['data_checked'] = False
            result = evaluate(self.bootstrap, root, self.now)
            self.assertFalse(result['should_generate'])
            self.assertFalse(result['previous_gameweek_closed'])
            self._snapshot(root, 6, '2026-09-21T10:00:00+00:00')
            self.bootstrap['events'][0]['data_checked'] = True
            result = evaluate(self.bootstrap, root, self.now)
            self.assertTrue(result['should_generate'])
            self.assertFalse(result['has_window_snapshot'])

    def test_finalized_unreviewed_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._snapshot(root, 5, '2026-09-18T10:00:00+00:00')
            result = evaluate(self.bootstrap, root, self.now)
            self.assertTrue(result['should_review'])
            self.assertEqual(result['pending_review_count'], 1)


if __name__ == '__main__':
    unittest.main()
