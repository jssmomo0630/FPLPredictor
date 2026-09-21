"""Build a dependency-free static dashboard from weekly recommendation snapshots."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ASSET_NAMES = ('index.html', 'styles.css', 'app.js')


def _read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def collect_dashboard_data(snapshot_root: Path):
    snapshots = []
    for path in sorted(snapshot_root.glob('*/*/*/recommendation.json')):
        report = _read_json(path)
        if report.get('schema_version') != 1:
            continue
        reviews = sorted(path.parent.glob('review-*.json'))
        review = _read_json(reviews[-1]) if reviews else None
        snapshots.append({'report': report, 'review': review})

    snapshots.sort(key=lambda item: item['report']['generated_at_utc'], reverse=True)
    latest_by_gameweek = {}
    for item in snapshots:
        key = f"{item['report']['season']}-gw{item['report']['gameweek']:02d}"
        latest_by_gameweek.setdefault(key, item)

    return {
        'schema_version': 1,
        'snapshots': snapshots,
        'latest_by_gameweek': list(latest_by_gameweek.values()),
    }


def build_site(snapshot_root: Path, output: Path, assets: Path):
    data = collect_dashboard_data(snapshot_root)
    if output.exists():
        shutil.rmtree(output)
    (output / 'data').mkdir(parents=True)
    for name in ASSET_NAMES:
        shutil.copyfile(assets / name, output / name)
    (output / '.nojekyll').write_text('', encoding='utf-8')
    (output / 'data' / 'dashboard.json').write_text(
        json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-root', type=Path, default=Path('artifacts/weekly'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/weekly-dashboard'))
    parser.add_argument('--assets', type=Path, default=Path('dashboard'))
    args = parser.parse_args()
    data = build_site(args.snapshot_root, args.output, args.assets)
    print(f"Built {args.output} with {len(data['snapshots'])} forecast snapshot(s)")


if __name__ == '__main__':
    main()
