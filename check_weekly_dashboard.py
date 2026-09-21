"""Cheap scheduling gate for weekly forecast generation and finalized reviews."""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


BOOTSTRAP_URL = 'https://fantasy.premierleague.com/api/bootstrap-static/'


def _utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def evaluate(bootstrap, snapshot_root, now, window_hours=48):
    future = [event for event in bootstrap['events'] if _utc(event['deadline_time']) > now]
    event = min(future, key=lambda row: _utc(row['deadline_time'])) if future else None
    hours = ((_utc(event['deadline_time']) - now).total_seconds() / 3600) if event else None
    previous = None
    has_window_snapshot = False
    if event:
        earlier = [row for row in bootstrap['events'] if int(row['id']) < int(event['id'])]
        previous = max(earlier, key=lambda row: int(row['id'])) if earlier else None
        window_start = _utc(event['deadline_time']) - timedelta(hours=window_hours)
        pattern = f"*/gw{int(event['id']):02d}/*/recommendation.json"
        for path in snapshot_root.glob(pattern):
            report = json.loads(path.read_text(encoding='utf-8'))
            generated = _utc(report['generated_at_utc'])
            if window_start <= generated < _utc(event['deadline_time']):
                has_window_snapshot = True
    previous_closed = previous is None or previous.get('data_checked') is True
    should_generate = (event is not None and hours <= window_hours and previous_closed
                       and not has_window_snapshot)

    finalized = {int(row['id']) for row in bootstrap['events'] if row.get('data_checked') is True}
    pending_reviews = []
    for path in snapshot_root.glob('*/*/*/recommendation.json'):
        report = json.loads(path.read_text(encoding='utf-8'))
        if int(report['gameweek']) in finalized and not list(path.parent.glob('review-*.json')):
            pending_reviews.append(str(path))
    return {
        'should_generate': should_generate,
        'should_review': bool(pending_reviews),
        'target_gameweek': int(event['id']) if event else None,
        'previous_gameweek': int(previous['id']) if previous else None,
        'previous_gameweek_closed': previous_closed,
        'has_window_snapshot': has_window_snapshot,
        'hours_to_deadline': round(hours, 2) if hours is not None else None,
        'pending_review_count': len(pending_reviews),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-root', type=Path, required=True)
    parser.add_argument('--bootstrap', type=Path)
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--window-hours', type=float, default=48)
    args = parser.parse_args()
    if args.bootstrap:
        bootstrap = json.loads(args.bootstrap.read_text(encoding='utf-8'))
    else:
        request = urllib.request.Request(BOOTSTRAP_URL, headers={'User-Agent': 'FPLPredictor/1.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            bootstrap = json.load(response)
    result = evaluate(bootstrap, args.snapshot_root, datetime.now(timezone.utc), args.window_hours)
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as handle:
            for key, value in result.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                handle.write(f'{key}={value}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
