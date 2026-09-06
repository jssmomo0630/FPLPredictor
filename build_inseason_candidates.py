#!/usr/bin/env python3
"""Create next-GW candidate features from finalized current-season data only."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from build_forecast_dataset import ROLLING_STATS, WINDOWS


def build_candidates(
    canonical: pd.DataFrame,
    fixture_features: pd.DataFrame,
    players: pd.DataFrame,
    season: str,
    as_of_gw: int | None = None,
    target_gw: int | None = None,
) -> pd.DataFrame:
    history = canonical[canonical["season"] == season].copy()
    if history.empty:
        raise ValueError(f"No finalized player-gameweek data exists for {season}; use the GW1 prior")
    available_gws = sorted(history["gameweek"].astype(int).unique().tolist())
    as_of_gw = as_of_gw if as_of_gw is not None else max(available_gws)
    history = history[history["gameweek"] <= as_of_gw].sort_values(["element", "gameweek"])
    scheduled = fixture_features[
        (fixture_features["season"] == season) & (fixture_features["gameweek"] > as_of_gw)
    ]
    if target_gw is None:
        if scheduled.empty:
            raise ValueError(f"No scheduled gameweek follows GW{as_of_gw}")
        target_gw = int(scheduled["gameweek"].min())

    current = players[players["element_type"].isin([1, 2, 3, 4])].copy()
    if "can_select" in current:
        current = current[current["can_select"].fillna(False)]
    current = current.rename(columns={
        "id": "element", "web_name": "player_name", "now_cost": "price",
    })
    output = current[["element", "player_name", "element_type", "team", "price"]].copy()

    grouped = history.groupby("element", sort=False)
    records = []
    for element, player in grouped:
        row = {"element": element, "current_season_minutes": float(player["minutes"].sum())}
        for stat in ROLLING_STATS:
            values = pd.to_numeric(player[stat], errors="coerce")
            for window in WINDOWS:
                row[f"lag_{stat}_{window}"] = values.tail(window).mean()
        last_five = player.tail(5)
        appearances = int(last_five["minutes"].gt(0).sum())
        row["lag_appearances_5"] = appearances
        row["lag_start_rate_5"] = pd.to_numeric(last_five["starts"], errors="coerce").mean()
        row["lag_minutes_per_appearance_5"] = (
            last_five["minutes"].sum() / appearances if appearances else np.nan
        )
        records.append(row)
    output = output.merge(pd.DataFrame(records), on="element", how="left", validate="one_to_one")

    target_fixtures = fixture_features[
        (fixture_features["season"] == season) & (fixture_features["gameweek"] == target_gw)
    ].drop(columns=["season"])
    output = output.merge(target_fixtures, on="team", how="left", validate="many_to_one")
    if output["fixture_count"].isna().any():
        output["is_blank_gameweek"] = output["fixture_count"].isna().astype(int)
        output["fixture_count"] = output["fixture_count"].fillna(0)
    else:
        output["is_blank_gameweek"] = 0
    output["season"] = season
    output["as_of_gameweek"] = as_of_gw
    output["target_gameweek"] = target_gw
    output["ruleset"] = "bps_2026_defensive_contribution" if season >= "2026-27" else "defensive_contribution_2025"
    chance = pd.to_numeric(current.get("chance_of_playing_next_round"), errors="coerce") / 100
    status = current.get("status", pd.Series("a", index=current.index)).map(
        {"a": 1.0, "d": 0.75, "i": 0.0, "s": 0.0, "u": 0.0}
    )
    availability = chance.fillna(status).fillna(1.0)
    output["availability_factor"] = output["element"].map(dict(zip(current["element"], availability)))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build finalized-data next-GW FPL candidates")
    parser.add_argument("--canonical", default="data/canonical_gameweeks.csv")
    parser.add_argument("--fixture-features", default="data/fixture_features.csv")
    parser.add_argument("--players", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--as-of-gw", type=int)
    parser.add_argument("--target-gw", type=int)
    parser.add_argument("--output", default="data/inseason_candidates.csv")
    args = parser.parse_args()
    result = build_candidates(
        pd.read_csv(args.canonical, low_memory=False),
        pd.read_csv(args.fixture_features, low_memory=False),
        pd.read_csv(args.players, low_memory=False),
        args.season, args.as_of_gw, args.target_gw,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result):,} candidates for {args.season} GW{int(result['target_gameweek'].iloc[0])}")


if __name__ == "__main__":
    main()
