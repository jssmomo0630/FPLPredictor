"""Independent weekly picks, immutable forecast snapshots, and finalized reviews."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fpl_pipeline_config import CURRENT_SEASON
from optimize_squad import POSITION_NAMES, _choose_column, _prepare_candidates


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return result.astimezone(timezone.utc)


def next_deadline(bootstrap, now):
    events = [event for event in bootstrap['events'] if utc(event['deadline_time']) > now]
    if not events:
        raise ValueError('No future gameweek deadline is available')
    return min(events, key=lambda event: utc(event['deadline_time']))


def build_report(predictions, optimized, bootstrap, season, event, now, prediction_hash):
    if now >= utc(event['deadline_time']):
        raise ValueError('Cannot publish a new recommendation after its deadline')
    if optimized['prediction_input_sha256'] != prediction_hash:
        raise ValueError('Optimized squad does not match the forecast input')
    column = _choose_column(predictions, None)
    candidates = _prepare_candidates(predictions, column)
    teams = {str(team['id']): team['short_name'] for team in bootstrap['teams']}
    players = []
    for row in candidates.to_dict('records'):
        points = float(row['expected_points'])
        price = float(row['price']) / 10
        players.append({
            'element': int(row['element']), 'name': row['player_name'],
            'position': POSITION_NAMES[int(row['element_type'])],
            'team': teams.get(row['club'], row['club']), 'price_millions': price,
            'expected_points': points, 'points_per_million': points / price,
            'appearance_probability': float(row['appearance_probability'])
                if row['minutes_risk_available'] else None,
        })
    players.sort(key=lambda player: (-player['expected_points'], player['element']))
    by_id = {player['element']: player for player in players}
    squad = [by_id[row['element']] | {
        key: row[key] for key in ('role', 'bench_order', 'is_captain', 'is_vice_captain')
    } for row in optimized['squad']]
    starters = [row for row in squad if row['role'] == 'starting_xi']
    fixed_xi_points = sum(row['expected_points'] * (2 if row['is_captain'] else 1)
                          for row in starters)
    return {
        'schema_version': 1, 'season': season, 'gameweek': int(event['id']),
        'generated_at_utc': now.isoformat(), 'deadline_time': event['deadline_time'],
        'forecast_sha256': prediction_hash, 'point_column': column,
        'budget_millions': optimized['budget_millions'],
        'cost_millions': sum(row['price_millions'] for row in squad),
        'solver': optimized['result'], 'assumptions': optimized['assumptions'],
        'fixed_xi_expected_points': fixed_xi_points,
        'squad': squad, 'players': players,
        'top_players': players[:10],
        'top_by_position': {pos: [p for p in players if p['position'] == pos][:5]
                            for pos in POSITION_NAMES.values()},
        'value_picks': sorted(players, key=lambda p: (-p['points_per_million'], p['element']))[:10],
        'method': 'One-gameweek squad from scratch; no owned squad, transfers, hits, or chips. '
                  'Rankings use expected points, not realized outcomes. Value is points per £m, '
                  'not a separate prediction. Availability is already included in forecasts.',
        'review_method': 'Score the published starting XI with double captain points and no '
                         'autosubs or vice-captain fallback. This fixed-XI benchmark is not an '
                         'official FPL entry score. Bench outcomes and minutes are reported separately.',
    }


def render_markdown(report):
    lines = [f"# {report['season']} GW{report['gameweek']} recommendations", '',
             f"Generated: {report['generated_at_utc']}", f"Deadline: {report['deadline_time']}", '',
             report['method'], '', f"Squad cost: £{report['cost_millions']:.1f}m / "
             f"£{report['budget_millions']:.1f}m. Solver: {report['solver']['solver_status']}.",
             f"Fixed XI + captain forecast: {report['fixed_xi_expected_points']:.1f} points.", '',
             '## Recommended squad', '', '| Player | Position | Role | £m | Expected points |',
             '| --- | --- | --- | ---: | ---: |']
    for player in sorted(report['squad'], key=lambda p: (p['bench_order'], p['position'], p['element'])):
        name = player['name'].replace('|', '\\|')
        badge = ' (C)' if player['is_captain'] else ' (VC)' if player['is_vice_captain'] else ''
        role = 'XI' if player['role'] == 'starting_xi' else f"Bench {player['bench_order']}"
        lines.append(f"| {name}{badge} | {player['position']} | {role} | "
                     f"{player['price_millions']:.1f} | {player['expected_points']:.2f} |")
    for label, picks in [('Top expected points', report['top_players']),
                         *[(f'Top {pos}', picks) for pos, picks in report['top_by_position'].items()],
                         ('Value picks (points per £m)', report['value_picks'])]:
        lines += ['', f'## {label}', '']
        for player in picks:
            lines.append(f"- {player['name']} ({player['team']}, {player['position']}): "
                         f"{player['expected_points']:.2f} points; £{player['price_millions']:.1f}m; "
                         f"{player['points_per_million']:.2f} points/£m.")
    return '\n'.join(lines + ['', report['review_method'], ''])


def save_snapshot(report, output):
    stamp = utc(report['generated_at_utc']).strftime('%Y%m%dT%H%M%S%fZ')
    directory = output / report['season'] / f"gw{report['gameweek']:02d}" / stamp
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'recommendation.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (directory / 'recommendation.md').write_text(render_markdown(report), encoding='utf-8')
    return directory


def review_report(report, bootstrap, live):
    event = next(event for event in bootstrap['events'] if event['id'] == report['gameweek'])
    if event['deadline_time'] != report['deadline_time']:
        raise ValueError('Result event does not match the snapshot deadline/season')
    if event.get('data_checked') is not True:
        raise ValueError('Gameweek results are not finalized (data_checked is false)')
    if utc(report['generated_at_utc']) >= utc(report['deadline_time']):
        raise ValueError('Cannot evaluate a post-deadline forecast as a pre-deadline prediction')
    actuals = {int(row['id']): row['stats'] for row in live['elements']}
    missing = {row['element'] for row in report['players']} - actuals.keys()
    if missing:
        raise ValueError(f'Actual results missing forecast players: {sorted(missing)}')
    outcomes = [{**player, 'actual_points': actuals[player['element']]['total_points'],
                 'actual_minutes': actuals[player['element']]['minutes'],
                 'error': actuals[player['element']]['total_points'] - player['expected_points']}
                for player in report['players']]
    by_id = {row['element']: row for row in outcomes}
    squad = [row | {'actual_points': by_id[row['element']]['actual_points'],
                    'actual_minutes': by_id[row['element']]['actual_minutes']}
             for row in report['squad']]
    actual_xi = sum(row['actual_points'] * (2 if row['is_captain'] else 1)
                    for row in squad if row['role'] == 'starting_xi')
    return {
        'schema_version': 1, 'season': report['season'], 'gameweek': report['gameweek'],
        'forecast_sha256': report['forecast_sha256'],
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
        'method': report['review_method'],
        'fixed_xi_expected_points': report['fixed_xi_expected_points'],
        'fixed_xi_actual_points': actual_xi,
        'fixed_xi_error': actual_xi - report['fixed_xi_expected_points'],
        'all_players_mae': sum(abs(row['error']) for row in outcomes) / len(outcomes),
        'top10_actual_points': sum(by_id[row['element']]['actual_points'] for row in report['top_players']),
        'biggest_positive_errors': sorted(outcomes, key=lambda row: -row['error'])[:5],
        'biggest_negative_errors': sorted(outcomes, key=lambda row: row['error'])[:5],
        'squad': squad, 'players': outcomes,
    }


def save_review(snapshot, data_root):
    report = json.loads(snapshot.read_text(encoding='utf-8'))
    directory = data_root / report['season']
    bootstrap_path = directory / 'bootstrap_static.json'
    bootstrap = json.loads(bootstrap_path.read_text(encoding='utf-8'))
    event = next(e for e in bootstrap['events'] if e['id'] == report['gameweek'])
    if event.get('data_checked') is not True:
        raise ValueError('Gameweek results are not finalized (data_checked is false)')
    live_path = directory / 'gws' / f"gw{report['gameweek']}_live.json"
    result = review_report(report, bootstrap, json.loads(live_path.read_text(encoding='utf-8')))
    result['snapshot_sha256'] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    result['results_sha256'] = hashlib.sha256(live_path.read_bytes()).hexdigest()
    output = snapshot.parent / ('review-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    generate = commands.add_parser('generate', help='Refresh data, forecast, and archive independent picks')
    generate.add_argument('--season', default=CURRENT_SEASON)
    generate.add_argument('--output-root', type=Path, default=Path('artifacts/weekly'))
    review = commands.add_parser('review', help='Evaluate a saved prediction using locally refreshed results')
    review.add_argument('--snapshot', required=True, type=Path)
    pending = commands.add_parser('review-pending', help='Evaluate every finalized snapshot without a review')
    pending.add_argument('--snapshot-root', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.command == 'generate':
        started = datetime.now(timezone.utc)
        subprocess.run([sys.executable, 'download_current_season.py', '--season', args.season], cwd=root, check=True)
        bootstrap = json.loads((root / 'data' / args.season / 'bootstrap_static.json').read_text(encoding='utf-8'))
        event = next_deadline(bootstrap, started)
        subprocess.run([sys.executable, 'run_fpl_pipeline.py', '--season', args.season,
                        '--target-gameweek', str(event['id'])], cwd=root, check=True)
        optimized = json.loads((root / 'data/optimal_squad.json').read_text(encoding='utf-8'))
        source = root / optimized['prediction_input']
        report = build_report(pd.read_csv(source), optimized, bootstrap, args.season, event,
                              datetime.now(timezone.utc), hashlib.sha256(source.read_bytes()).hexdigest())
        report['provenance'] = {
            'refresh_started_at_utc': started.isoformat(),
            'finalized_gameweeks': [e['id'] for e in bootstrap['events'] if e.get('data_checked')],
            'bootstrap_sha256': hashlib.sha256(
                (root / 'data' / args.season / 'bootstrap_static.json').read_bytes()).hexdigest(),
            'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in ('weekly_recommendations.py', 'run_fpl_pipeline.py',
                             'train_gw1_prior.py', 'train_inseason_model.py',
                             'blend_forecasts.py', 'optimize_squad.py')},
        }
        print(save_snapshot(report, args.output_root.resolve()))
    elif args.command == 'review':
        try:
            print(save_review(args.snapshot, root / 'data'))
        except ValueError as error:
            raise SystemExit(str(error)) from error
    else:
        created = []
        for snapshot in sorted(args.snapshot_root.glob('*/*/*/recommendation.json')):
            if list(snapshot.parent.glob('review-*.json')):
                continue
            try:
                created.append(str(save_review(snapshot, root / 'data')))
            except (ValueError, FileNotFoundError, StopIteration):
                continue
        print(json.dumps({'reviews_created': created}, indent=2))


if __name__ == '__main__':
    main()
