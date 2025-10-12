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
import os
import sys
import json
from datetime import datetime
import requests
import pandas as pd

DEFAULT_SEASONS = [
    "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"
]

BASE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def download_file(url: str, out_path: str, timeout: int = 30) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        print(f"  OK  {os.path.basename(out_path)} ({len(r.content):,} bytes)")
        return True
    except Exception as e:
        print(f"  ERR {os.path.basename(out_path)}: {e}")
        return False


def download_season(season: str, per_gw: bool = False) -> dict:
    print(f"\n== Season {season} ==")
    season_dir = os.path.join("data", season)
    ensure_dir(season_dir)
    ensure_dir(os.path.join(season_dir, "gws"))

    results = {"players_raw.csv": False, "merged_gw.csv": False, "gw_files": 0}

    # players_raw.csv
    players_url = f"{BASE_URL}/{season}/players_raw.csv"
    results["players_raw.csv"] = download_file(players_url, os.path.join(season_dir, "players_raw.csv"))

    # merged_gw.csv
    merged_url = f"{BASE_URL}/{season}/gws/merged_gw.csv"
    results["merged_gw.csv"] = download_file(merged_url, os.path.join(season_dir, "merged_gw.csv"))

    # Optional per-GW files
    if per_gw:
        gw_downloaded = 0
        for gw in range(1, 39):
            gw_url = f"{BASE_URL}/{season}/gws/gw{gw}.csv"
            gw_path = os.path.join(season_dir, "gws", f"gw{gw}.csv")
            ok = download_file(gw_url, gw_path)
            if not ok:
                # stop when unavailable (some seasons are incomplete)
                break
            gw_downloaded += 1
        results["gw_files"] = gw_downloaded
        print(f"  GW  downloaded {gw_downloaded} per-GW files")

    return results


def verify_season(season: str) -> dict:
    season_dir = os.path.join("data", season)
    out = {"season": season, "players": None, "merged_rows": None, "gw_files": 0}
    try:
        pr = os.path.join(season_dir, "players_raw.csv")
        if os.path.exists(pr):
            df = pd.read_csv(pr)
            out["players"] = len(df)
    except Exception:
        pass
    try:
        mgw = os.path.join(season_dir, "merged_gw.csv")
        if os.path.exists(mgw):
            df = pd.read_csv(mgw)
            out["merged_rows"] = len(df)
    except Exception:
        pass
    gws_dir = os.path.join(season_dir, "gws")
    if os.path.isdir(gws_dir):
        out["gw_files"] = len([f for f in os.listdir(gws_dir) if f.startswith("gw") and f.endswith(".csv")])
    return out


def write_summary(seasons: list, path: str = "data/download_summary.json") -> None:
    summary = {
        "generated_at": datetime.now().isoformat(),
        "seasons": [verify_season(s) for s in seasons],
    }
    ensure_dir(os.path.dirname(path))
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written: {path}")


def clean_seasons(seasons: list) -> None:
    import shutil
    for season in seasons:
        season_dir = os.path.join("data", season)
        if os.path.exists(season_dir):
            shutil.rmtree(season_dir)
            print(f"Removed {season_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download historical FPL data from vaastav")
    parser.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS, help="Seasons to download e.g. 2023-24 2024-25")
    parser.add_argument("--per-gw", action="store_true", help="Also download per-GW files")
    parser.add_argument("--clean", action="store_true", help="Remove existing season folders before downloading")
    parser.add_argument("--no-summary", action="store_true", help="Skip writing download summary JSON")
    args = parser.parse_args()

    print("=== Historical FPL Data (vaastav) ===")
    print(f"Seasons: {args.seasons}")
    print(f"Per-GW:  {'on' if args.per_gw else 'off'}")

    if args.clean:
        print("Cleaning existing season folders...")
        clean_seasons(args.seasons)

    all_results = {}
    for s in args.seasons:
        all_results[s] = download_season(s, per_gw=args.per_gw)

    print("\n=== Verification ===")
    for s in args.seasons:
        v = verify_season(s)
        print(f"{s}: players={v['players']}, merged_rows={v['merged_rows']}, gw_files={v['gw_files']}")

    if not args.no_summary:
        write_summary(args.seasons)

    print("\nDone.")


if __name__ == "__main__":
    sys.exit(main())

