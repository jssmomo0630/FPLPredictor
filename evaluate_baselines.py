#!/usr/bin/env python3
"""Chronologically valid baseline evaluation for FPL point forecasts."""

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error


def evaluate(dataset: pd.DataFrame, test_seasons: list[str]) -> dict:
    results = {}
    for season in test_seasons:
        season_rows = dataset[dataset["season"] == season]
        source_gameweeks = sorted(season_rows["gameweek"].dropna().astype(int).unique().tolist())
        # The feature was constructed entirely from prior GWs; this is a
        # walk-forward baseline, not a same-season random split.
        rows = season_rows.dropna(
            subset=["lag_total_points_5", "target_points_1gw"]
        )
        if rows.empty:
            results[season] = {"rows": 0}
            continue
        actual = rows["target_points_1gw"]
        predicted = rows["lag_total_points_5"]
        results[season] = {
            "rows": int(len(rows)),
            "source_gameweeks_present": source_gameweeks,
            "source_complete_38_gameweeks": set(source_gameweeks) == set(range(1, 39)),
            "evaluated_gameweek_min": int(rows["gameweek"].min()),
            "evaluated_gameweek_max": int(rows["gameweek"].max()),
            "evaluation_complete_gw2_to_gw38": set(rows["gameweek"].astype(int).unique()) == set(range(2, 39)),
            "mae": round(float(mean_absolute_error(actual, predicted)), 4),
            "rmse": round(float(mean_squared_error(actual, predicted) ** 0.5), 4),
            "spearman_rank_correlation": round(float(predicted.corr(actual, method="spearman")), 4),
            "mean_prediction": round(float(predicted.mean()), 4),
            "mean_actual": round(float(actual.mean()), 4),
            "calibration_ratio": round(float(predicted.mean() / actual.mean()), 4) if actual.mean() else None,
        }
    return {"baseline": "trailing five-gameweek mean points", "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate leakage-safe FPL baseline forecasts")
    parser.add_argument("--input", default="data/forecast_dataset.csv")
    parser.add_argument("--test-seasons", nargs="+", required=True)
    parser.add_argument("--output", default="data/baseline_evaluation.json")
    args = parser.parse_args()

    report = evaluate(pd.read_csv(args.input, low_memory=False), args.test_seasons)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved evaluation to {args.output}")


if __name__ == "__main__":
    main()
