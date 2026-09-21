import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from optimize_squad import _prepare_candidates, optimise, _validate_solution
from weekly_recommendations import build_report, next_deadline, review_report, save_snapshot


class WeeklyRecommendationTests(unittest.TestCase):
    def setUp(self):
        positions = [1, 1, *([2] * 5), *([3] * 5), *([4] * 3)]
        self.predictions = pd.DataFrame([
            {'element': i, 'player_name': f'Player {i}', 'element_type': pos,
             'team_id': (i-1)//3+1, 'price': 50, 'predicted_points_next_gw': float(i)/3}
            for i, pos in enumerate(positions, 1)
        ])
        squad, result = optimise(_prepare_candidates(self.predictions, 'predicted_points_next_gw'), time_limit=2)
        _validate_solution(squad, 1000)
        self.optimized = {'prediction_input_sha256': 'test', 'budget_millions': 100,
                          'squad': squad.to_dict('records'), 'result': result, 'assumptions': {}}
        self.event = {'id': 6, 'deadline_time': '2026-09-26T10:00:00Z', 'data_checked': False}
        self.bootstrap = {'teams': [{'id': i, 'short_name': f'T{i}'} for i in range(1, 6)],
                          'events': [self.event]}
        self.now = datetime(2026, 9, 24, tzinfo=timezone.utc)

    def report(self):
        return build_report(self.predictions, self.optimized, self.bootstrap,
                            '2026-27', self.event, self.now, 'test')

    def test_independent_rankings_and_budget_valid_squad(self):
        report = self.report()
        self.assertEqual(len(report['squad']), 15)
        self.assertEqual(report['top_players'][0]['element'], 15)
        self.assertEqual(report['cost_millions'], 75)
        self.assertEqual(len(report['top_by_position']['DEF']), 5)
        self.assertAlmostEqual(report['value_picks'][0]['points_per_million'], 1)

    def test_rejects_late_snapshot_and_mismatched_forecast(self):
        with self.assertRaisesRegex(ValueError, 'after its deadline'):
            build_report(self.predictions, self.optimized, self.bootstrap, '2026-27', self.event,
                         datetime(2026, 9, 27, tzinfo=timezone.utc), 'test')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            build_report(self.predictions, self.optimized, self.bootstrap, '2026-27', self.event,
                         self.now, 'different')

    def test_snapshot_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = save_snapshot(self.report(), Path(folder))
            self.assertTrue((path / 'recommendation.md').is_file())
            with self.assertRaises(FileExistsError):
                save_snapshot(self.report(), Path(folder))

    def test_review_gates_finalization_and_scores_same_metric(self):
        report = self.report()
        live = {'elements': [{'id': i, 'stats': {'total_points': 2, 'minutes': 90}} for i in range(1, 16)]}
        with self.assertRaisesRegex(ValueError, 'not finalized'):
            review_report(report, self.bootstrap, live)
        self.event['data_checked'] = True
        result = review_report(report, self.bootstrap, live)
        self.assertEqual(result['fixed_xi_actual_points'], 24)
        self.assertEqual(result['top10_actual_points'], 20)
        self.assertAlmostEqual(result['fixed_xi_error'], 24-report['fixed_xi_expected_points'])
        live['elements'].pop()
        with self.assertRaisesRegex(ValueError, 'missing forecast players'):
            review_report(report, self.bootstrap, live)

    def test_next_deadline_skips_in_progress_gameweek(self):
        bootstrap = {'events': [{'id': 5, 'deadline_time': '2026-09-20T10:00:00Z'}, self.event]}
        self.assertEqual(next_deadline(bootstrap, self.now)['id'], 6)


if __name__ == '__main__':
    unittest.main()
