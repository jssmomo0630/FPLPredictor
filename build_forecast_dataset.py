#!/usr/bin/env python3
"""Build leakage-safe FPL player-gameweek forecast datasets.

Each output row targets the points scored in its ``gameweek``.  Every feature is
shifted first, so it uses only gameweeks strictly earlier than the target.
"""

import argparse
from pathlib import Path

import pandas as pd


ROLLING_STATS = [
    "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "saves", "bonus", "defensive_contribution", "expected_goals",
    "expected_assists", "expected_goal_involvements", "yellow_cards",
    "red_cards", "total_points",
]
WINDOWS = (3, 5, 8)
FEATURE_COLUMNS = [
    *(f"lag_{stat}_{window}" for stat in ROLLING_STATS for window in WINDOWS),
    "lag_appearances_5", "lag_start_rate_5", "lag_minutes_per_appearance_5",
    "fixture_count",
]
TARGET_COLUMNS = ("target_points_1gw", "target_points_3gw", "target_points_5gw")


def _lagged_rolling(
    data: pd.DataFrame, key: list[str], column: str, window: int, statistic: str = "mean"
) -> pd.Series:
    """Vectorised group rolling statistic after shifting by one gameweek."""
    shifted = data.groupby(key, sort=False)[column].shift(1)
    rolling = shifted.groupby([data[name] for name in key], sort=False).rolling(window, min_periods=1)
    values = getattr(rolling, statistic)()
    return values.reset_index(level=key, drop=True).reindex(data.index)


def _future_group_sum(data: pd.DataFrame, key: list[str], horizon: int) -> pd.Series:
    """Vectorised target sum for the target GW and its following fixtures."""
    reverse = data.iloc[::-1]
    values = reverse.groupby(key, sort=False)["total_points"].rolling(
        horizon, min_periods=horizon
    ).sum()
    return values.reset_index(level=key, drop=True).reindex(data.index)


def build_dataset(canonical: pd.DataFrame) -> pd.DataFrame:
    required = {"season", "element", "gameweek", "total_points", *ROLLING_STATS}
    missing = required.difference(canonical.columns)
    if missing:
        raise ValueError(f"Canonical input is missing columns: {sorted(missing)}")

    data = canonical.copy()
    data["gameweek"] = pd.to_numeric(data["gameweek"], errors="raise")
    data = data.sort_values(["season", "element", "gameweek"]).reset_index(drop=True)
    key = ["season", "element"]

    if data.duplicated(key + ["gameweek"]).any():
        raise ValueError("Input has duplicate (season, element, gameweek) rows")

    for stat in ROLLING_STATS:
        values = pd.to_numeric(data[stat], errors="coerce")
        data[stat] = values
        for window in WINDOWS:
            # shift happens before rolling: target GW values can never enter a feature
            data[f"lag_{stat}_{window}"] = _lagged_rolling(data, key, stat, window)

    prior_minutes = _lagged_rolling(data, key, "minutes", 5, "sum")
    appeared = data["minutes"].gt(0).astype(int)
    data["_appeared"] = appeared
    data["lag_appearances_5"] = _lagged_rolling(data, key, "_appeared", 5, "sum")
    # ``lag_starts_5`` is already the mean of the preceding observations.
    data["lag_start_rate_5"] = data["lag_starts_5"]
    data["lag_minutes_per_appearance_5"] = (
        prior_minutes / data["lag_appearances_5"].replace(0, pd.NA)
    )

    data["target_points_1gw"] = data["total_points"]
    for horizon in (3, 5):
        data[f"target_points_{horizon}gw"] = _future_group_sum(data, key, horizon)

    identity = [
        "season", "element", "gameweek", "player_name", "position", "element_type",
        "team", "source", "ruleset",
    ]
    available_identity = [column for column in identity if column in data.columns]
    return data[available_identity + FEATURE_COLUMNS + list(TARGET_COLUMNS)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a leakage-safe FPL forecast dataset")
    parser.add_argument("--input", default="data/canonical_gameweeks.csv")
    parser.add_argument("--output", default="data/forecast_dataset.csv")
    args = parser.parse_args()

    dataset = build_dataset(pd.read_csv(args.input, low_memory=False))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output, index=False)
    print(f"Wrote {len(dataset):,} rows to {args.output}")
    print(f"Features: {len(FEATURE_COLUMNS)} | 1-GW usable rows: {dataset['lag_total_points_5'].notna().sum():,}")


if __name__ == "__main__":
    main()
