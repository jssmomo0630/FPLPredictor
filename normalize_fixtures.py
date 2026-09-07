#!/usr/bin/env python3
"""Build a canonical one-team-per-fixture schedule from FPL data sources."""

import argparse
from pathlib import Path

import pandas as pd


COLUMNS = [
    "season", "source", "fixture", "gameweek", "team", "opponent_team",
    "was_home", "kickoff_time", "fixture_difficulty", "started", "finished",
    "finished_provisional",
]


def _vaastav_paths(season_dir: Path) -> tuple[Path, Path] | None:
    nested = season_dir / "vaastav"
    if (nested / "merged_gw.csv").exists():
        return nested / "merged_gw.csv", nested / "players_raw.csv"
    merged = season_dir / "merged_gw.csv"
    if merged.exists() and "position" in pd.read_csv(merged, nrows=0).columns:
        return merged, season_dir / "players_raw.csv"
    return None


def normalize_vaastav(season: str, season_dir: Path) -> pd.DataFrame:
    paths = _vaastav_paths(season_dir)
    if paths is None:
        return pd.DataFrame(columns=COLUMNS)
    merged_path, _players_path = paths
    raw = pd.read_csv(merged_path, low_memory=False)
    gameweek = "GW" if "GW" in raw.columns else "round"
    sides = raw[["fixture", gameweek, "team", "opponent_team", "was_home", "kickoff_time"]].drop_duplicates()
    home = sides[sides["was_home"].astype(bool)].rename(columns={
        gameweek: "gameweek", "team": "home_name", "opponent_team": "away_id",
    })
    away = sides[~sides["was_home"].astype(bool)].rename(columns={
        gameweek: "gameweek", "team": "away_name", "opponent_team": "home_id",
    })
    matches = home.merge(
        away[["fixture", "away_name", "home_id"]], on="fixture", how="inner", validate="one_to_one"
    )
    common = ["fixture", "gameweek", "kickoff_time"]
    home_rows = matches[common].assign(
        season=season, source="vaastav", team=matches["home_id"],
        opponent_team=matches["away_id"], was_home=True,
    )
    away_rows = matches[common].assign(
        season=season, source="vaastav", team=matches["away_id"],
        opponent_team=matches["home_id"], was_home=False,
    )
    schedule = pd.concat([home_rows, away_rows], ignore_index=True)
    schedule["fixture_difficulty"] = pd.NA
    schedule["started"] = True
    schedule["finished"] = True
    schedule["finished_provisional"] = False
    return schedule[COLUMNS]


def normalize_official(season: str, season_dir: Path) -> pd.DataFrame:
    path = season_dir / "fixtures_canonical.csv"
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    raw = pd.read_csv(path)
    raw["source"] = "official_api"
    for column in COLUMNS:
        if column not in raw:
            raw[column] = pd.NA
    raw["season"] = season
    return raw[COLUMNS]


def normalize_season(season: str, data_root: Path) -> pd.DataFrame:
    season_dir = data_root / season
    vaastav = normalize_vaastav(season, season_dir)
    return vaastav if not vaastav.empty else normalize_official(season, season_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create canonical FPL team-fixture schedule")
    parser.add_argument("--seasons", nargs="+", required=True)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--output", default="data/canonical_fixtures.csv")
    args = parser.parse_args()

    frames = [normalize_season(season, Path(args.data_root)) for season in args.seasons]
    result = pd.concat(frames, ignore_index=True)
    if result.empty:
        raise ValueError("No fixture data found")
    if result.duplicated(["season", "fixture", "team"]).any():
        raise ValueError("Duplicate (season, fixture, team) rows")
    if not result.groupby(["season", "fixture"]).size().eq(2).all():
        raise ValueError("Every fixture must have exactly two team rows")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result):,} team-fixture rows to {args.output}")
    print(result.groupby("season").agg(fixtures=("fixture", "nunique"), gameweeks=("gameweek", "nunique")).to_string())


if __name__ == "__main__":
    main()
