#!/usr/bin/env python3
"""
Download Current Season Data (FPL API)
=====================================

Consolidated script to fetch current-season data from the official
Fantasy Premier League API, download live gameweek data, flatten it,
and produce a merged gameweek CSV for modeling.

Features:
- Downloads bootstrap-static JSON and writes CSV components under data/<season>
- Detects finished/current gameweeks and downloads event/{gw}/live JSONs
- Flattens GW JSON into per-GW CSVs with key stats
- Creates merged_gw_enhanced.csv from all downloaded GWs

Usage:
- python download_current_season.py               # defaults to season 2025-26
- python download_current_season.py --season 2025-26 --max-gw 10
"""

import argparse
import json
import os
from datetime import datetime
from typing import List

import pandas as pd
import requests


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def fetch_bootstrap() -> dict:
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def save_bootstrap_components(data: dict, season_dir: str) -> None:
    ensure_dir(season_dir)
    with open(os.path.join(season_dir, "bootstrap_static.json"), "w") as f:
        json.dump(data, f, indent=2)

    components = {
        "events": data.get("events", []),
        "teams": data.get("teams", []),
        "elements": data.get("elements", []),
        "element_types": data.get("element_types", []),
        "phases": data.get("phases", []),
    }
    for name, comp in components.items():
        if comp:
            df = pd.DataFrame(comp)
            csv = os.path.join(season_dir, f"{name}.csv")
            df.to_csv(csv, index=False)
            print(f"Saved {os.path.basename(csv)} ({len(df)} rows)")


def detect_gameweeks(bootstrap: dict, max_gw: int = None) -> List[int]:
    events = bootstrap.get("events", [])
    finished = [e.get("id") for e in events if e.get("finished")]
    current = next((e.get("id") for e in events if e.get("is_current")), None)
    gws = list(sorted(set([*finished, *( [current] if current else [] )])))
    if max_gw is not None:
        gws = [gw for gw in gws if gw <= max_gw]
    return gws


def download_gw_live(gw: int, gws_dir: str) -> dict:
    ensure_dir(gws_dir)
    url = f"https://fantasy.premierleague.com/api/event/{gw}/live/"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    with open(os.path.join(gws_dir, f"gw{gw}_live.json"), "w") as f:
        json.dump(data, f, indent=2)
    return data


def flatten_gw(data: dict, gw: int, season: str) -> pd.DataFrame:
    elements = data.get("elements", [])
    rows = []
    for el in elements:
        row = {
            "element": el.get("id"),
            "gameweek": gw,
            "season": season,
        }
        stats = el.get("stats", {})
        for k, v in stats.items():
            row[k] = v
        row["explain"] = str(el.get("explain", ""))
        row["modified"] = el.get("modified", "")
        rows.append(row)
    df = pd.DataFrame(rows)
    if "total_points" not in df.columns:
        df["total_points"] = 0
    return df


def build_merged_gw(gws_dir: str, out_path: str) -> None:
    frames = []
    for fn in sorted(os.listdir(gws_dir)):
        if fn.startswith("gw") and fn.endswith(".csv") and not fn.endswith("_enhanced.csv"):
            path = os.path.join(gws_dir, fn)
            try:
                frames.append(pd.read_csv(path))
            except Exception:
                pass
    if not frames:
        print("No GW CSVs to merge.")
        return
    merged = pd.concat(frames, ignore_index=True)
    merged.to_csv(out_path, index=False)
    print(f"Created merged file: {out_path} ({len(merged)} rows)")


def main():
    parser = argparse.ArgumentParser(description="Download current-season FPL data and build merged GW file")
    parser.add_argument("--season", default="2025-26", help="Season folder name, e.g. 2025-26")
    parser.add_argument("--max-gw", type=int, default=None, help="Optional cap on gameweek number")
    args = parser.parse_args()

    season_dir = os.path.join("data", args.season)
    gws_dir = os.path.join(season_dir, "gws")

    print("=== Current Season Downloader ===")
    print(f"Season: {args.season}")
    print(f"Timestamp: {datetime.now()}")

    # 1) Bootstrap
    print("\nFetching bootstrap-static...")
    bootstrap = fetch_bootstrap()
    save_bootstrap_components(bootstrap, season_dir)

    # 2) Determine GWs to download
    gws = detect_gameweeks(bootstrap, max_gw=args.max_gw)
    print(f"Gameweeks to download: {gws}")

    # 3) Download GW live JSONs and write per-GW CSVs
    for gw in gws:
        print(f"\n-- GW{gw} --")
        data = download_gw_live(gw, gws_dir)
        df = flatten_gw(data, gw, args.season)
        out_csv = os.path.join(gws_dir, f"gw{gw}.csv")
        df.to_csv(out_csv, index=False)
        print(f"Saved {os.path.basename(out_csv)} ({len(df)} rows)")

    # 4) Build merged file (enhanced)
    out_merged = os.path.join(season_dir, "merged_gw_enhanced.csv")
    build_merged_gw(gws_dir, out_merged)

    print("\nDone.")


if __name__ == "__main__":
    main()

