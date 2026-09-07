#!/usr/bin/env python3
"""Evaluate a leakage-safe fixture-aware baseline on held-out seasons."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PLAYER_FEATURES = [
    "lag_total_points_3", "lag_total_points_5", "lag_total_points_8",
    "lag_minutes_3", "lag_minutes_5", "lag_starts_5",
    "lag_goals_scored_5", "lag_assists_5", "lag_expected_goals_5",
    "lag_expected_assists_5",
]
FIXTURE_FEATURES = [
    "fixture_count", "home_fixture_count", "away_fixture_count",
    "is_double_gameweek", "min_rest_days",
    "lag_team_goals_for_5", "lag_team_xg_for_5", "lag_team_fpl_points_5",
    "lag_team_goals_against_5", "lag_team_xga_5",
    "opponent_team_goals_for_5", "opponent_team_xg_for_5",
    "opponent_team_fpl_points_5", "opponent_team_goals_against_5",
    "opponent_team_xga_5",
]


def _season_start(season: str) -> int:
    return int(str(season).split("-")[0])


def _selection_metrics(rows: pd.DataFrame, predictions: np.ndarray) -> dict:
    scored = rows[["gameweek", "target_points_1gw"]].copy()
    scored["prediction"] = predictions
    overlaps, captures, regrets = [], [], []
    for _gameweek, group in scored.groupby("gameweek"):
        predicted_top = group.nlargest(10, "prediction")
        actual_top = group.nlargest(10, "target_points_1gw")
        overlaps.append(len(set(predicted_top.index).intersection(actual_top.index)) / 10)
        oracle_points = actual_top["target_points_1gw"].sum()
        captures.append(
            predicted_top["target_points_1gw"].sum() / oracle_points if oracle_points else np.nan
        )
        captain = group.nlargest(1, "prediction")["target_points_1gw"].iloc[0]
        regrets.append(group["target_points_1gw"].max() - captain)
    return {
        "top_10_overlap": round(float(np.nanmean(overlaps)), 4),
        "top_10_points_capture": round(float(np.nanmean(captures)), 4),
        "captain_regret": round(float(np.nanmean(regrets)), 4),
    }


def _metrics(rows: pd.DataFrame, predictions: np.ndarray) -> dict:
    actual = rows["target_points_1gw"].to_numpy()
    result = {
        "rows": int(len(rows)),
        "mae": round(float(mean_absolute_error(actual, predictions)), 4),
        "rmse": round(float(mean_squared_error(actual, predictions) ** 0.5), 4),
        "spearman_rank_correlation": round(
            float(pd.Series(predictions).corr(pd.Series(actual), method="spearman")), 4
        ),
        "mean_prediction": round(float(np.mean(predictions)), 4),
        "mean_actual": round(float(np.mean(actual)), 4),
        "calibration_ratio": round(float(np.mean(predictions) / np.mean(actual)), 4),
    }
    result.update(_selection_metrics(rows, predictions))
    return result


def evaluate(forecasts: pd.DataFrame, fixture_features: pd.DataFrame, test_seasons: list[str]) -> dict:
    # The player table's fixture_count is replaced by the schedule-derived value.
    forecasts = forecasts.drop(columns=["fixture_count"], errors="ignore")
    data = forecasts.merge(
        fixture_features, on=["season", "team", "gameweek"], how="left", validate="many_to_one"
    )
    if data["fixture_count"].isna().any():
        raise ValueError("Some player-gameweek rows have no fixture feature match")

    position_dummies = pd.get_dummies(data["position"], prefix="position", dtype=int)
    data = pd.concat([data, position_dummies], axis=1)
    feature_columns = PLAYER_FEATURES + FIXTURE_FEATURES + position_dummies.columns.tolist()
    reports = {}
    for season in test_seasons:
        split = _season_start(season)
        train = data[data["season"].map(_season_start) < split].dropna(
            subset=["lag_total_points_5", "target_points_1gw"]
        )
        test = data[data["season"] == season].dropna(
            subset=["lag_total_points_5", "target_points_1gw"]
        )
        if train.empty or test.empty:
            raise ValueError(f"Insufficient chronological data for {season}")

        model = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=10.0)),
        ])
        model.fit(train[feature_columns], train["target_points_1gw"])
        fixture_prediction = np.clip(model.predict(test[feature_columns]), 0, None)
        trailing_prediction = test["lag_total_points_5"].to_numpy()
        reports[season] = {
            "training_seasons": sorted(train["season"].unique().tolist()),
            "training_rows": int(len(train)),
            "evaluated_gameweeks": sorted(test["gameweek"].astype(int).unique().tolist()),
            "trailing_five_baseline": _metrics(test, trailing_prediction),
            "fixture_aware_ridge": _metrics(test, fixture_prediction),
        }
    return {"features": feature_columns, "results": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate fixture-aware FPL baseline")
    parser.add_argument("--forecasts", default="data/forecast_dataset.csv")
    parser.add_argument("--fixtures", default="data/fixture_features.csv")
    parser.add_argument("--test-seasons", nargs="+", required=True)
    parser.add_argument("--output", default="data/fixture_baseline_evaluation.json")
    args = parser.parse_args()

    report = evaluate(
        pd.read_csv(args.forecasts, low_memory=False),
        pd.read_csv(args.fixtures, low_memory=False),
        args.test_seasons,
    )
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved evaluation to {args.output}")


if __name__ == "__main__":
    main()
