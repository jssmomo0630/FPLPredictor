#!/usr/bin/env python3
"""
Download Historical FPL Data (vaastav)
======================================

Consolidated script to fetch historical FPL data from the
vaastav/Fantasy-Premier-League repository.

Features:
- Downloads players_raw.csv and gws/merged_gw.csv per season
- Optional per‑GW files (gw1.csv ...)
- Optional clean before download
- Basic verification and summary output

Usage examples:
- python download_history_data.py
- python download_history_data.py --seasons 2020-21 2021-22 2022-23 2023-24 2024-25 --per-gw
- python download_history_data.py --clean
"""

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd

from fpl_pipeline_config import HISTORICAL_SEASONS, VAASTAV_REF

DEFAULT_SEASONS = list(HISTORICAL_SEASONS)
BASE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{ref}/data"


def _validate_csv(path: Path, required: set[str], any_of: set[str] | None = None) -> None:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        columns = set(next(csv.reader(handle)))
    missing = required - columns
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {sorted(missing)}")
    if any_of and not columns.intersection(any_of):
        raise ValueError(f"{path.name} requires one of these columns: {sorted(any_of)}")


def download_file(
    url: str,
    out_path: Path,
    required: set[str],
    any_of: set[str] | None = None,
    timeout: int = 30,
    skip_existing: bool = False,
) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if skip_existing and out_path.is_file() and out_path.stat().st_size:
        _validate_csv(out_path, required, any_of)
        print(f"  HIT {out_path.name} ({out_path.stat().st_size:,} bytes)")
        return True
    temporary = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        with temporary.open("wb") as f:
            f.write(r.content)
        _validate_csv(temporary, required, any_of)
        temporary.replace(out_path)
        print(f"  OK  {out_path.name} ({len(r.content):,} bytes)")
        return True
    except Exception as e:
        temporary.unlink(missing_ok=True)
        print(f"  ERR {out_path.name}: {e}")
        return False


def download_season(
    season: str,
    data_root: Path,
    ref: str,
    per_gw: bool = False,
    skip_existing: bool = False,
) -> dict:
    print(f"\n== Season {season} ==")
    season_dir = data_root / season / "vaastav"
    season_dir.mkdir(parents=True, exist_ok=True)
    (season_dir / "gws").mkdir(parents=True, exist_ok=True)

    results = {"players_raw.csv": False, "merged_gw.csv": False, "gw_files": 0}
    base_url = BASE_URL.format(ref=ref)

    # players_raw.csv
    players_url = f"{base_url}/{season}/players_raw.csv"
    results["players_raw.csv"] = download_file(
        players_url,
        season_dir / "players_raw.csv",
        {"id", "web_name", "element_type"},
        skip_existing=skip_existing,
    )

    # merged_gw.csv
    merged_url = f"{base_url}/{season}/gws/merged_gw.csv"
    results["merged_gw.csv"] = download_file(
        merged_url,
        season_dir / "merged_gw.csv",
        {"element", "total_points", "position"},
        {"GW", "round"},
        skip_existing=skip_existing,
    )

    # Optional per-GW files
    if per_gw:
        gw_downloaded = 0
        for gw in range(1, 39):
            gw_url = f"{base_url}/{season}/gws/gw{gw}.csv"
            gw_path = season_dir / "gws" / f"gw{gw}.csv"
            ok = download_file(
                gw_url,
                gw_path,
                {"element", "total_points"},
                skip_existing=skip_existing,
            )
            if not ok:
                # stop when unavailable (some seasons are incomplete)
                break
            gw_downloaded += 1
        results["gw_files"] = gw_downloaded
        print(f"  GW  downloaded {gw_downloaded} per-GW files")

    return results


def verify_season(season: str, data_root: Path) -> dict:
    season_dir = data_root / season / "vaastav"
    out = {"season": season, "players": None, "merged_rows": None, "gw_files": 0}
    try:
        pr = season_dir / "players_raw.csv"
        if pr.exists():
            df = pd.read_csv(pr)
            out["players"] = len(df)
    except Exception:
        pass
    try:
        mgw = season_dir / "merged_gw.csv"
        if mgw.exists():
            df = pd.read_csv(mgw)
            out["merged_rows"] = len(df)
    except Exception:
        pass
    gws_dir = season_dir / "gws"
    if gws_dir.is_dir():
        out["gw_files"] = len(list(gws_dir.glob("gw*.csv")))
    return out


def write_summary(seasons: list, data_root: Path, path: Path | None = None) -> None:
    path = path or data_root / "download_summary.json"
    summary = {
        "generated_at": datetime.now().isoformat(),
        "seasons": [verify_season(s, data_root) for s in seasons],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written: {path}")


def clean_seasons(seasons: list, data_root: Path) -> None:
    for season in seasons:
        season_dir = data_root / season / "vaastav"
        if season_dir.exists():
            shutil.rmtree(season_dir)
            print(f"Removed {season_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download historical FPL data from vaastav")
    parser.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS, help="Seasons to download e.g. 2023-24 2024-25")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--ref", default=VAASTAV_REF, help="Immutable vaastav Git revision")
    parser.add_argument("--per-gw", action="store_true", help="Also download per-GW files")
    parser.add_argument("--clean", action="store_true", help="Remove existing vaastav folders before downloading")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse valid existing compact files")
    parser.add_argument("--no-summary", action="store_true", help="Skip writing download summary JSON")
    args = parser.parse_args()
    data_root = Path(args.data_root)

    print("=== Historical FPL Data (vaastav) ===")
    print(f"Seasons: {args.seasons}")
    print(f"Revision: {args.ref}")
    print(f"Per-GW:  {'on' if args.per_gw else 'off'}")

    if args.clean:
        print("Cleaning existing season folders...")
        clean_seasons(args.seasons, data_root)

    all_results = {}
    for s in args.seasons:
        all_results[s] = download_season(
            s, data_root, args.ref, per_gw=args.per_gw, skip_existing=args.skip_existing
        )

    failed = [
        season for season, result in all_results.items()
        if not result["players_raw.csv"] or not result["merged_gw.csv"]
    ]
    if failed:
        raise SystemExit(f"Historical download failed for: {', '.join(failed)}")

    print("\n=== Verification ===")
    for s in args.seasons:
        v = verify_season(s, data_root)
        print(f"{s}: players={v['players']}, merged_rows={v['merged_rows']}, gw_files={v['gw_files']}")

    if not args.no_summary:
        write_summary(args.seasons, data_root)

    print("\nDone.")


if __name__ == "__main__":
    sys.exit(main())
