#!/usr/bin/env python3
"""Build deadline-safe team and opponent features for each team-gameweek."""

import argparse
from pathlib import Path

import pandas as pd


TEAM_OUTCOMES = {
    "goals_scored": ("team_goals_for", "sum"),
    "expected_goals": ("team_xg_for", "sum"),
    "total_points": ("team_fpl_points", "sum"),
    "goals_conceded": ("team_goals_against", "max"),
    "expected_goals_conceded": ("team_xga", "max"),
}
STRENGTH_COLUMNS = [name for name, _operation in TEAM_OUTCOMES.values()]


def _lagged_mean(data: pd.DataFrame, column: str, window: int = 5) -> pd.Series:
    key = ["season", "team"]
    shifted = data.groupby(key, sort=False)[column].shift(1)
    values = shifted.groupby([data[name] for name in key], sort=False).rolling(
        window, min_periods=1
    ).mean()
    return values.reset_index(level=key, drop=True).reindex(data.index)


def build_team_strength(player_gameweeks: pd.DataFrame) -> pd.DataFrame:
    required = {"season", "team", "gameweek", *TEAM_OUTCOMES}
    missing = required.difference(player_gameweeks.columns)
    if missing:
        raise ValueError(f"Player-gameweek data is missing: {sorted(missing)}")

    aggregations = {source: operation for source, (_name, operation) in TEAM_OUTCOMES.items()}
    team = player_gameweeks.groupby(
        ["season", "team", "gameweek"], as_index=False
    ).agg(aggregations)
    team = team.rename(columns={source: name for source, (name, _operation) in TEAM_OUTCOMES.items()})
    team = team.sort_values(["season", "team", "gameweek"]).reset_index(drop=True)
    for column in STRENGTH_COLUMNS:
        team[f"lag_{column}_5"] = _lagged_mean(team, column)
    return team


def _strength_for_targets(strength: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Calculate prior-five means for observed or future scheduled gameweeks."""
    history_groups = {
        key: group.sort_values("gameweek")
        for key, group in strength.groupby(["season", "team"], sort=False)
    }
    rows = []
    for target in targets.itertuples(index=False):
        history = history_groups.get((target.season, target.team))
        prior = history[history["gameweek"] < target.gameweek].tail(5) if history is not None else None
        row = {"season": target.season, "team": target.team, "gameweek": target.gameweek}
        for column in STRENGTH_COLUMNS:
            row[f"lag_{column}_5"] = prior[column].mean() if prior is not None and not prior.empty else pd.NA
        rows.append(row)
    return pd.DataFrame(rows)


def build_fixture_features(player_gameweeks: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    strength = build_team_strength(player_gameweeks)
    lag_columns = [f"lag_{column}_5" for column in STRENGTH_COLUMNS]

    schedule = fixtures.copy()
    targets = schedule[["season", "team", "gameweek"]].drop_duplicates()
    target_strength = _strength_for_targets(strength, targets)
    schedule["kickoff_time"] = pd.to_datetime(schedule["kickoff_time"], utc=True, errors="coerce")
    schedule = schedule.sort_values(["season", "team", "kickoff_time", "fixture"])
    schedule["previous_kickoff"] = schedule.groupby(["season", "team"])["kickoff_time"].shift(1)
    schedule["rest_days"] = (
        schedule["kickoff_time"] - schedule["previous_kickoff"]
    ).dt.total_seconds() / 86400

    opponent = target_strength.rename(
        columns={"team": "opponent_team", **{column: f"opponent_{column[4:]}" for column in lag_columns}}
    )
    schedule = schedule.merge(
        opponent, on=["season", "opponent_team", "gameweek"], how="left", validate="many_to_one"
    )
    opponent_columns = [f"opponent_{column[4:]}" for column in lag_columns]

    schedule["home_fixture"] = schedule["was_home"].astype(bool).astype(int)
    grouped = schedule.groupby(["season", "team", "gameweek"], as_index=False)
    fixture_features = grouped.agg(
        fixture_count=("fixture", "count"),
        home_fixture_count=("home_fixture", "sum"),
        mean_fixture_difficulty=("fixture_difficulty", "mean"),
        min_rest_days=("rest_days", "min"),
        **{column: (column, "mean") for column in opponent_columns},
    )
    fixture_features["away_fixture_count"] = (
        fixture_features["fixture_count"] - fixture_features["home_fixture_count"]
    )
    fixture_features["is_double_gameweek"] = (fixture_features["fixture_count"] > 1).astype(int)

    own = target_strength
    result = fixture_features.merge(
        own, on=["season", "team", "gameweek"], how="left", validate="one_to_one"
    )
    if result.duplicated(["season", "team", "gameweek"]).any():
        raise ValueError("Duplicate team-gameweek fixture features")
    return result.sort_values(["season", "team", "gameweek"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build lagged team/opponent FPL fixture features")
    parser.add_argument("--player-gameweeks", default="data/canonical_gameweeks.csv")
    parser.add_argument("--fixtures", default="data/canonical_fixtures.csv")
    parser.add_argument("--output", default="data/fixture_features.csv")
    args = parser.parse_args()

    features = build_fixture_features(
        pd.read_csv(args.player_gameweeks, low_memory=False),
        pd.read_csv(args.fixtures, low_memory=False),
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.output, index=False)
    print(f"Wrote {len(features):,} team-gameweek rows to {args.output}")
    print(features.groupby("season").agg(
        rows=("team", "size"), doubles=("is_double_gameweek", "sum")
    ).to_string())


if __name__ == "__main__":
    main()
