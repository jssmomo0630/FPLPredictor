#!/usr/bin/env python3
"""Chronologically replay multi-week versus myopic FPL transfer planning."""

import argparse
import json
from pathlib import Path

import pandas as pd

from build_transfer_forecasts import build_horizon
from build_inseason_candidates import build_candidates
from optimize_squad import _prepare_candidates, optimise
from plan_transfers import plan, prepare_forecasts
from train_inseason_model import train_and_predict


def as_of_predictions(canonical: pd.DataFrame, season: str, as_of_gw: int) -> pd.DataFrame:
    history = canonical[(canonical["season"] == season) & (canonical["gameweek"] <= as_of_gw)].copy()
    history = history.sort_values(["element", "gameweek"])
    latest = history.groupby("element", as_index=False).tail(1).copy()
    form = history.groupby("element").tail(5).groupby("element")["total_points"].mean()
    latest["predicted_points_gw1"] = latest["element"].map(form).fillna(0).clip(lower=0)
    latest = latest[
        latest["element_type"].isin([1, 2, 3, 4])
        & latest["now_cost"].notna() & latest["team"].notna()
    ].copy()
    latest["price"] = latest["now_cost"].astype(int)
    latest["team_id"] = latest["team"].astype(int)
    # Keep strong and cheap candidates so the historical initial solve is fast and feasible.
    pieces = []
    for _, group in latest.groupby("element_type"):
        pieces.append(pd.concat([
            group.nlargest(35, "predicted_points_gw1"), group.nsmallest(10, "price"),
        ]).drop_duplicates("element"))
    return pd.concat(pieces, ignore_index=True).drop_duplicates("element")


def direct_model_forecasts(
    canonical: pd.DataFrame,
    forecast_dataset: pd.DataFrame,
    fixture_features: pd.DataFrame,
    season: str,
    as_of_gw: int,
    horizon: int,
) -> pd.DataFrame:
    history = canonical[(canonical["season"] == season) & (canonical["gameweek"] <= as_of_gw)]
    latest = history.sort_values(["element", "gameweek"]).groupby("element", as_index=False).tail(1).copy()
    players = latest.rename(columns={
        "element": "id", "player_name": "web_name", "now_cost": "price_source",
    })
    players["now_cost"] = players["price_source"]
    players["can_select"] = True
    players["status"] = "a"
    players["chance_of_playing_next_round"] = 100
    required = [
        "id", "web_name", "element_type", "team", "now_cost", "can_select", "status",
        "chance_of_playing_next_round",
    ]
    players = players[required].dropna(subset=["id", "element_type", "team", "now_cost"])
    rows = []
    for target_gw in range(as_of_gw + 1, as_of_gw + horizon + 1):
        candidates = build_candidates(
            canonical, fixture_features, players, season,
            as_of_gw=as_of_gw, target_gw=target_gw,
        )
        predictions, _ = train_and_predict(forecast_dataset, fixture_features, candidates)
        week = predictions[[
            "element", "player_name", "element_type", "team", "price",
            "predicted_points_next_gw",
        ]].rename(columns={
            "team": "team_id", "predicted_points_next_gw": "expected_points",
        })
        week["gameweek"] = target_gw
        rows.append(week)
    return pd.concat(rows, ignore_index=True)


def actual_score(plan_rows: pd.DataFrame, canonical: pd.DataFrame, season: str, hit_costs: dict[int, float]) -> float:
    actual = canonical[canonical["season"] == season].set_index(["gameweek", "element"])["total_points"].to_dict()
    score = 0.0
    for row in plan_rows.itertuples():
        if row.role != "starting_xi":
            continue
        points = float(actual.get((int(row.gameweek), int(row.element)), 0))
        score += points * (2 if row.is_captain else 1)
    return score - sum(hit_costs.values())


def replay_window(
    canonical: pd.DataFrame,
    fixture_features: pd.DataFrame,
    season: str,
    as_of_gw: int,
    horizon: int,
    free_transfers: int,
    time_limit: float,
    transfer_friction: float,
    terminal_free_transfer_value: float,
    forecast_dataset: pd.DataFrame | None,
) -> dict:
    if forecast_dataset is None:
        predictions = as_of_predictions(canonical, season, as_of_gw)
        forecasts = build_horizon(
            predictions, fixture_features, season, as_of_gw + 1, horizon, "predicted_points_gw1",
        )
    else:
        forecasts = direct_model_forecasts(
            canonical, forecast_dataset, fixture_features, season, as_of_gw, horizon,
        )
    first = forecasts[forecasts["gameweek"] == as_of_gw + 1].rename(
        columns={"expected_points": "initial_expected_points"}
    )
    initial_candidates = _prepare_candidates(first, "initial_expected_points")
    initial_squad, _ = optimise(initial_candidates, time_limit=time_limit)
    current = set(initial_squad["element"].astype(int))
    prices = forecasts.drop_duplicates("element").set_index("element")["price"].astype(int).to_dict()
    selling = {element: prices[element] for element in current}

    multi_forecasts = prepare_forecasts(forecasts, current, 15)
    multi_rows, multi_report = plan(
        multi_forecasts, current, selling, 0, free_transfers,
        transfer_friction=transfer_friction,
        terminal_free_transfer_value=terminal_free_transfer_value,
        time_limit=time_limit,
    )
    multi_hits = {week["gameweek"]: week["hit_cost"] for week in multi_report["weeks"]}
    multi_actual = actual_score(multi_rows, canonical, season, multi_hits)

    myopic_rows = []
    myopic_hits = {}
    myopic_current = set(current)
    myopic_selling = dict(selling)
    myopic_bank = 0
    myopic_free = free_transfers
    myopic_transfer_count = 0
    for gameweek in sorted(forecasts["gameweek"].unique()):
        one_week = prepare_forecasts(forecasts[forecasts["gameweek"] == gameweek], myopic_current, 15)
        rows, report = plan(
            one_week, myopic_current, myopic_selling, myopic_bank, myopic_free,
            transfer_friction=transfer_friction,
            terminal_free_transfer_value=terminal_free_transfer_value,
            time_limit=time_limit,
        )
        myopic_rows.append(rows)
        state = report["weeks"][0]
        myopic_hits[int(gameweek)] = state["hit_cost"]
        myopic_transfer_count += int(state["transfers_used"])
        myopic_current = set(rows["element"].astype(int))
        myopic_bank = int(state["bank_after"])
        myopic_free = int(state["free_transfers_after_roll"])
        myopic_selling = {element: prices[element] for element in myopic_current}
    myopic_rows = pd.concat(myopic_rows, ignore_index=True)
    myopic_actual = actual_score(myopic_rows, canonical, season, myopic_hits)
    return {
        "as_of_gameweek": as_of_gw,
        "evaluated_gameweeks": list(range(as_of_gw + 1, as_of_gw + horizon + 1)),
        "initial_free_transfers": free_transfers,
        "multi_week_realized_points_after_hits": multi_actual,
        "myopic_realized_points_after_hits": myopic_actual,
        "multi_week_minus_myopic": multi_actual - myopic_actual,
        "multi_week_transfers": sum(week["transfers_used"] for week in multi_report["weeks"]),
        "multi_week_hits": sum(multi_hits.values()),
        "myopic_transfers": myopic_transfer_count,
        "myopic_hits": sum(myopic_hits.values()),
        "multi_week_solver_status": multi_report["solver_status"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest multi-week transfer planning chronologically")
    parser.add_argument("--canonical", default="data/canonical_gameweeks.csv")
    parser.add_argument("--fixtures", default="data/fixture_features.csv")
    parser.add_argument("--forecast-dataset", default="data/forecast_dataset.csv")
    parser.add_argument(
        "--forecast-mode", choices=["direct_model", "fixture_scaled"], default="direct_model",
    )
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--as-of-gameweeks", nargs="+", type=int, default=[10, 20, 30])
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--free-transfers", type=int, default=2)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--transfer-friction", type=float, default=0.25)
    parser.add_argument("--terminal-free-transfer-value", type=float, default=0.50)
    parser.add_argument("--output", default="data/transfer_planner_evaluation.json")
    args = parser.parse_args()
    canonical = pd.read_csv(args.canonical, low_memory=False)
    fixtures = pd.read_csv(args.fixtures)
    forecast_dataset = (
        pd.read_csv(args.forecast_dataset, low_memory=False)
        if args.forecast_mode == "direct_model" else None
    )
    windows = [
        replay_window(
            canonical, fixtures, args.season, gameweek, args.horizon,
            args.free_transfers, args.time_limit, args.transfer_friction,
            args.terminal_free_transfer_value, forecast_dataset,
        )
        for gameweek in args.as_of_gameweeks
    ]
    total_multi = sum(window["multi_week_realized_points_after_hits"] for window in windows)
    total_myopic = sum(window["myopic_realized_points_after_hits"] for window in windows)
    report = {
        "season": args.season,
        "forecast_mode": args.forecast_mode,
        "method": (
            "At each as-of date, the chronological rule-aware Ridge model is fitted only through that GW and predicts each future target from then-known player form and target fixtures."
            if args.forecast_mode == "direct_model" else
            "At each as-of date, trailing-five form and then-known prices are fixture-scaled; all targets are future GWs."
        ),
        "transfer_friction": args.transfer_friction,
        "terminal_free_transfer_value": args.terminal_free_transfer_value,
        "windows": windows,
        "aggregate_multi_week_points": total_multi,
        "aggregate_myopic_points": total_myopic,
        "aggregate_improvement": total_multi - total_myopic,
        "recommendation_enabled": total_multi > total_myopic,
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
