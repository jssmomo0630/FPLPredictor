#!/usr/bin/env python3
"""Expand the current player forecast into a transparent multi-GW fixture horizon."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from optimize_squad import _choose_column


def fixture_multiplier(frame: pd.DataFrame) -> pd.Series:
    count = pd.to_numeric(frame["fixture_count"], errors="coerce").fillna(0).clip(lower=0)
    fdr = pd.to_numeric(frame["mean_fixture_difficulty"], errors="coerce").fillna(3).clip(1, 5)
    home = pd.to_numeric(frame["home_fixture_count"], errors="coerce").fillna(0)
    home_share = (home / count.replace(0, np.nan)).fillna(0.5)
    per_fixture = (1 + 0.12 * (3 - fdr) + 0.04 * (2 * home_share - 1)).clip(0.65, 1.35)
    return count * per_fixture


def build_horizon(
    predictions: pd.DataFrame,
    fixtures: pd.DataFrame,
    season: str,
    start_gameweek: int,
    horizon: int,
    point_column: str,
) -> pd.DataFrame:
    required = {"element", "player_name", "element_type", "price", point_column}
    if missing := required.difference(predictions.columns):
        raise ValueError(f"Predictions missing columns: {sorted(missing)}")
    team_column = "team_id" if "team_id" in predictions else "team"
    if team_column not in predictions:
        raise ValueError("Predictions need team_id or numeric team")
    player_columns = [
        "element", "player_name", "element_type", "price", point_column, team_column,
    ]
    players = predictions[player_columns].copy()
    players["team_id"] = pd.to_numeric(players[team_column], errors="coerce")
    if players["team_id"].isna().any():
        raise ValueError("Transfer forecasts require numeric team IDs")
    players["team_id"] = players["team_id"].astype(int)
    players["base_expected_points"] = pd.to_numeric(players[point_column], errors="coerce").clip(lower=0)
    players = players.dropna(subset=["base_expected_points"]).drop_duplicates("element")

    targets = fixtures[
        (fixtures["season"] == season)
        & fixtures["gameweek"].between(start_gameweek, start_gameweek + horizon - 1)
    ][["team", "gameweek", "fixture_count", "home_fixture_count", "mean_fixture_difficulty"]].copy()
    targets = targets.rename(columns={"team": "team_id"})
    if targets.empty:
        raise ValueError(f"No fixture features exist for {season} GW{start_gameweek}+{horizon - 1}")
    expected_gws = list(range(start_gameweek, start_gameweek + horizon))
    if missing_gws := sorted(set(expected_gws).difference(targets["gameweek"].unique())):
        raise ValueError(f"Fixture features are missing gameweeks: {missing_gws}")
    targets["fixture_multiplier"] = fixture_multiplier(targets)
    base = targets[targets["gameweek"] == start_gameweek][["team_id", "fixture_multiplier"]].rename(
        columns={"fixture_multiplier": "base_fixture_multiplier"}
    )
    targets = targets.merge(base, on="team_id", how="left", validate="many_to_one")
    targets["base_fixture_multiplier"] = targets["base_fixture_multiplier"].replace(0, np.nan).fillna(1.0)
    targets["relative_fixture_multiplier"] = (
        targets["fixture_multiplier"] / targets["base_fixture_multiplier"]
    ).clip(0, 2.5)
    output = players.merge(targets, on="team_id", how="inner", validate="many_to_many")
    output["expected_points"] = output["base_expected_points"] * output["relative_fixture_multiplier"]
    output["season"] = season
    output["forecast_method"] = "current_forecast_scaled_by_relative_fixture_count_fdr_and_home"
    keep = [
        "season", "gameweek", "element", "player_name", "element_type", "team_id", "price",
        "expected_points", "base_expected_points", "fixture_count", "home_fixture_count",
        "mean_fixture_difficulty", "relative_fixture_multiplier", "forecast_method",
    ]
    return output[keep].sort_values(["gameweek", "element"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fixture-scaled multi-GW transfer forecast")
    parser.add_argument("--predictions", default="data/gw1_2026-27_predictions.csv")
    parser.add_argument("--fixtures", default="data/fixture_features.csv")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--start-gameweek", type=int, required=True)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--points-column")
    parser.add_argument("--output", default="data/transfer_forecasts.csv")
    args = parser.parse_args()
    predictions = pd.read_csv(args.predictions, low_memory=False)
    point_column = _choose_column(predictions, args.points_column)
    result = build_horizon(
        predictions, pd.read_csv(args.fixtures), args.season,
        args.start_gameweek, args.horizon, point_column,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result):,} player-GW forecasts for GW{args.start_gameweek}-{args.start_gameweek + args.horizon - 1}")


if __name__ == "__main__":
    main()
