#!/usr/bin/env python3
"""Train the rule-aware next-gameweek model and score current candidates."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_fixture_baseline import FIXTURE_FEATURES, PLAYER_FEATURES


EXTRA_RULE_FEATURES = [
    "lag_defensive_contribution_3", "lag_defensive_contribution_5",
    "lag_defensive_contribution_8",
]


def _season_start(season: str) -> int:
    return int(season.split("-")[0])


def train_and_predict(
    forecasts: pd.DataFrame,
    fixture_features: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    prediction_season = str(candidates["season"].iloc[0])
    as_of_gw = int(candidates["as_of_gameweek"].iloc[0])
    target_gw = int(candidates["target_gameweek"].iloc[0])
    forecasts = forecasts.drop(columns=["fixture_count"], errors="ignore").merge(
        fixture_features, on=["season", "team", "gameweek"], how="left", validate="many_to_one"
    )
    train = forecasts[
        (forecasts["season"].map(_season_start) < _season_start(prediction_season))
        | ((forecasts["season"] == prediction_season) & (forecasts["gameweek"] <= as_of_gw))
    ].dropna(subset=["lag_total_points_5", "target_points_1gw"]).copy()
    if train.empty:
        raise ValueError("No chronological training rows are available")

    combined_positions = pd.concat([train["position"], candidates["element_type"].map(
        {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    )], ignore_index=True)
    position_dummies = pd.get_dummies(combined_positions, prefix="position", dtype=int)
    train_positions = position_dummies.iloc[:len(train)].reset_index(drop=True)
    candidate_positions = position_dummies.iloc[len(train):].reset_index(drop=True)
    train = pd.concat([train.reset_index(drop=True), train_positions], axis=1)
    candidates = pd.concat([candidates.reset_index(drop=True), candidate_positions], axis=1)

    combined_rules = pd.concat([train["ruleset"], candidates["ruleset"]], ignore_index=True)
    rule_dummies = pd.get_dummies(combined_rules, prefix="ruleset", dtype=int)
    train_rules = rule_dummies.iloc[:len(train)].reset_index(drop=True)
    candidate_rules = rule_dummies.iloc[len(train):].reset_index(drop=True)
    train = pd.concat([train, train_rules], axis=1)
    candidates = pd.concat([candidates, candidate_rules], axis=1)

    feature_columns = (
        PLAYER_FEATURES + EXTRA_RULE_FEATURES + FIXTURE_FEATURES
        + position_dummies.columns.tolist() + rule_dummies.columns.tolist()
    )
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scaler", StandardScaler()),
        ("model", Ridge(alpha=10.0)),
    ])
    model.fit(train[feature_columns], train["target_points_1gw"])
    raw = np.clip(model.predict(candidates[feature_columns]), 0, None)
    trailing = candidates["lag_total_points_5"].fillna(pd.Series(raw, index=candidates.index))
    candidates["predicted_points_next_gw_before_availability"] = raw
    candidates["predicted_points_next_gw"] = raw * candidates["availability_factor"].fillna(1.0)
    candidates["selection_score_next_gw_before_availability"] = 0.5 * trailing + 0.5 * raw
    candidates["selection_score_next_gw"] = (
        candidates["selection_score_next_gw_before_availability"]
        * candidates["availability_factor"].fillna(1.0)
    )
    candidates["model"] = "rule_aware_ridge"
    report = {
        "prediction_season": prediction_season,
        "as_of_gameweek": as_of_gw,
        "target_gameweek": target_gw,
        "training_rows": int(len(train)),
        "training_seasons": sorted(train["season"].unique().tolist()),
        "feature_columns": feature_columns,
        "rule_note": "2026/27 BPS is marked explicitly but has no historical fitted effect yet",
    }
    return candidates.sort_values("predicted_points_next_gw", ascending=False), report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and run the in-season FPL forecast")
    parser.add_argument("--forecasts", default="data/forecast_dataset.csv")
    parser.add_argument("--fixture-features", default="data/fixture_features.csv")
    parser.add_argument("--candidates", default="data/inseason_candidates.csv")
    parser.add_argument("--output", default="data/inseason_predictions.csv")
    parser.add_argument("--report", default="data/inseason_model_report.json")
    args = parser.parse_args()
    predictions, report = train_and_predict(
        pd.read_csv(args.forecasts, low_memory=False),
        pd.read_csv(args.fixture_features, low_memory=False),
        pd.read_csv(args.candidates, low_memory=False),
    )
    predictions.to_csv(args.output, index=False)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {len(predictions):,} predictions to {args.output}")


if __name__ == "__main__":
    main()
