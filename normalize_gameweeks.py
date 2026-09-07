#!/usr/bin/env python3
"""Normalize vaastav historical data and official FPL API data to one GW schema.

The sources use the same FPL ``element`` identifier within a season, so that is
the authoritative player key.  Names are retained for display only.
"""

import argparse
from pathlib import Path

import pandas as pd


# Fields are deliberately source-neutral.  Outcome fields describe the completed
# gameweek; model code must lag them before using them as features.
CANONICAL_COLUMNS = [
    "season", "source", "ruleset", "element", "gameweek", "player_name", "position",
    "element_type", "team", "opponent_team", "fixture", "kickoff_time",
    "was_home", "fixture_count", "now_cost", "status", "chance_of_playing_next_round",
    "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "saves", "bonus", "bps", "defensive_contribution",
    "defensive_contribution_available",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "yellow_cards", "red_cards", "own_goals",
    "penalties_missed", "penalties_saved", "total_points",
]


def _first_present(frame: pd.DataFrame, *names: str, default=pd.NA):
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series(default, index=frame.index)


def _player_lookup(season_dir: Path, source: str) -> pd.DataFrame:
    source_players = season_dir / source / "players_raw.csv"
    players_path = source_players if source_players.exists() else season_dir / "players_raw.csv"
    players = pd.read_csv(players_path)
    columns = [
        "id", "web_name", "element_type", "team", "now_cost", "status",
        "chance_of_playing_next_round",
    ]
    return players.reindex(columns=columns).rename(columns={
        "id": "element", "web_name": "player_name_from_bootstrap",
        "element_type": "element_type_from_bootstrap", "team": "team_id_from_bootstrap",
    })


def _with_fixture_team_ids(raw: pd.DataFrame) -> pd.DataFrame:
    """Resolve historical team IDs from the fixture, not end-of-season player data."""
    if not {"fixture", "was_home", "opponent_team"}.issubset(raw.columns):
        return raw
    raw = raw.copy()
    if raw["was_home"].dtype == "object":
        raw["was_home"] = raw["was_home"].replace(
            {"True": True, "False": False, "true": True, "false": False}
        ).astype(bool)
    sides = raw[["fixture", "was_home", "opponent_team"]].drop_duplicates()
    pairs = sides.merge(sides, on="fixture", suffixes=("", "_other"))
    pairs = pairs[pairs["was_home"] != pairs["was_home_other"]]
    mapping = pairs[["fixture", "was_home", "opponent_team_other"]].rename(
        columns={"opponent_team_other": "team_id_from_fixture"}
    )
    return raw.merge(mapping, on=["fixture", "was_home"], how="left", validate="many_to_one")


def normalize_season(season: str, data_root: Path) -> pd.DataFrame:
    season_dir = data_root / season
    source_historical_path = season_dir / "vaastav" / "merged_gw.csv"
    historical_path = season_dir / "merged_gw.csv"
    official_path = season_dir / "merged_gw_enhanced.csv"
    if source_historical_path.exists():
        raw = pd.read_csv(source_historical_path)
        source = "vaastav"
    elif historical_path.exists() and "position" in pd.read_csv(historical_path, nrows=0).columns:
        raw = pd.read_csv(historical_path)
        source = "vaastav"
    elif official_path.exists():
        raw = pd.read_csv(official_path)
        source = "official_api"
    elif historical_path.exists():
        # Early versions of the current-season downloader wrote official API
        # output under this legacy filename.  Detect by schema, not filename.
        raw = pd.read_csv(historical_path)
        source = "official_api"
    else:
        raise FileNotFoundError(f"No supported merged GW file in {season_dir}")

    if source == "official_api" and "data_finalized" in raw.columns:
        raw = raw[raw["data_finalized"].fillna(False).astype(bool)].copy()
    if source == "vaastav":
        raw = _with_fixture_team_ids(raw)
    lookup = _player_lookup(season_dir, source)
    raw = raw.merge(lookup, on="element", how="left", validate="many_to_one")
    out = pd.DataFrame(index=raw.index)
    out["season"] = season
    out["source"] = source
    if season >= "2026-27":
        out["ruleset"] = "bps_2026_defensive_contribution"
    elif "defensive_contribution" in raw.columns:
        out["ruleset"] = "defensive_contribution_2025"
    else:
        out["ruleset"] = "pre_defensive_contribution"
    out["element"] = raw["element"]
    out["gameweek"] = _first_present(raw, "gameweek", "GW", "round")
    out["player_name"] = _first_present(raw, "name", "player_name_from_bootstrap")
    out["position"] = _first_present(raw, "position")
    out["element_type"] = _first_present(raw, "element_type", "element_type_from_bootstrap")
    # Team IDs, unlike names, are stable across both feeds within a season.
    out["team"] = _first_present(raw, "team_id_from_fixture", "team_id_from_bootstrap", "team")
    position_names = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    out["position"] = out["position"].fillna(out["element_type"].map(position_names))
    out["position"] = out["position"].replace({"GKP": "GK"})
    out["opponent_team"] = _first_present(raw, "opponent_team")
    out["fixture"] = _first_present(raw, "fixture")
    out["kickoff_time"] = _first_present(raw, "kickoff_time")
    out["was_home"] = _first_present(raw, "was_home")
    for column in CANONICAL_COLUMNS:
        if column not in out.columns:
            out[column] = _first_present(raw, column)
    out["defensive_contribution_available"] = "defensive_contribution" in raw.columns
    out = out[out["element_type"].isin(position_names)].copy()
    # vaastav stores a player twice in a double gameweek (one row per fixture),
    # whereas event/<gw>/live is already aggregated.  Make both sources obey the
    # same player-gameweek grain.  Fixture-level inputs belong in a companion
    # fixture schedule table, not in this outcome table.
    key = ["season", "source", "element", "gameweek"]
    out["fixture_count"] = out.groupby(key, dropna=False)["element"].transform("size")
    totals = [
        "minutes", "starts", "goals_scored", "assists", "clean_sheets",
        "goals_conceded", "saves", "bonus", "bps", "defensive_contribution",
        "expected_goals", "expected_assists", "expected_goal_involvements",
        "expected_goals_conceded", "yellow_cards", "red_cards", "own_goals",
        "penalties_missed", "penalties_saved", "total_points",
    ]
    aggregation = {column: "sum" for column in totals}
    aggregation.update({column: "first" for column in CANONICAL_COLUMNS if column not in key + totals + ["fixture_count"]})
    aggregation["fixture_count"] = "first"
    out = out.groupby(key, as_index=False, dropna=False).agg(aggregation)
    multi_fixture = out["fixture_count"] > 1
    out["was_home"] = out["was_home"].astype("object")
    out.loc[multi_fixture, ["opponent_team", "fixture", "kickoff_time", "was_home"]] = pd.NA
    return out[CANONICAL_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a canonical FPL player-gameweek table")
    parser.add_argument("--seasons", nargs="+", required=True)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--output", default="data/canonical_gameweeks.csv")
    args = parser.parse_args()

    frames = [normalize_season(season, Path(args.data_root)) for season in args.seasons]
    result = pd.concat(frames, ignore_index=True)
    duplicate_keys = result.duplicated(["season", "element", "gameweek"], keep=False)
    if duplicate_keys.any():
        raise ValueError("Duplicate (season, element, gameweek) rows: inspect double fixtures")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result):,} rows to {args.output}")
    print(result.groupby("source").size().to_string())
    print("Missing values by field:")
    print(result.isna().mean().sort_values(ascending=False).head(12).to_string())


if __name__ == "__main__":
    main()
