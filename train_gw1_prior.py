#!/usr/bin/env python3
"""Chronologically evaluate and train the dedicated FPL GW1 prior model."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "price", "has_prior_player_history", "changed_team", "promoted_team",
    "defensive_contribution_rules",
    "prior_minutes_per_team_game", "prior_minutes_per_appearance",
    "prior_points_per_team_game", "prior_points_per_appearance",
    "prior_start_rate", "prior_appearance_rate", "prior_total_points_per90",
    "prior_goals_scored_per90", "prior_assists_per90", "prior_expected_goals_per90",
    "prior_expected_assists_per90", "prior_expected_goal_involvements_per90",
    "prior_clean_sheets_per90", "prior_saves_per90", "prior_bonus_per90",
    "prior_defensive_contribution_per90", "prior_team_goals_for",
    "prior_team_goals_against", "prior_team_xg", "prior_team_fpl_points",
    "fixtures_next5", "home_fixtures_next5", "first_fixture_home",
    "mean_opponent_prior_team_goals_for_next5",
    "mean_opponent_prior_team_goals_against_next5",
    "mean_opponent_prior_team_xg_next5", "mean_opponent_prior_team_fpl_points_next5",
]

MINUTE_TARGETS = {
    "appearance_probability": "target_appearance",
    "start_probability": "target_started",
    "played_60_probability": "target_played_60",
}


def _models() -> dict[str, Pipeline]:
    return {
        "ridge": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", HistGradientBoostingRegressor(
                learning_rate=0.05, max_iter=150, max_leaf_nodes=15,
                min_samples_leaf=20, l2_regularization=1.0, random_state=42,
            )),
        ]),
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", RandomForestRegressor(
                n_estimators=300, min_samples_leaf=8, max_features=0.8,
                n_jobs=-1, random_state=42,
            )),
        ]),
    }


def _probability_model() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(C=0.5, max_iter=1000, random_state=42)),
    ])


def _predict_probability(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    target: str,
) -> np.ndarray:
    labels = train[target].astype(int)
    if labels.nunique() < 2:
        return np.full(len(test), float(labels.mean()))
    model = _probability_model()
    model.fit(train[feature_columns], labels)
    return model.predict_proba(test[feature_columns])[:, 1]


def _minute_probabilities(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, np.ndarray]:
    probabilities = {
        output: np.clip(_predict_probability(train, test, feature_columns, target), 0, 1)
        for output, target in MINUTE_TARGETS.items()
    }
    probabilities["start_probability"] = np.minimum(
        probabilities["start_probability"], probabilities["appearance_probability"]
    )
    probabilities["played_60_probability"] = np.minimum(
        probabilities["played_60_probability"], probabilities["start_probability"]
    )
    return probabilities


def _probability_metrics(actual: pd.Series, prediction: np.ndarray) -> dict:
    return {
        "brier_score": round(float(brier_score_loss(actual.astype(int), prediction)), 4),
        "mean_prediction": round(float(np.mean(prediction)), 4),
        "mean_actual": round(float(actual.mean()), 4),
    }


def _conditional_points_model(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> np.ndarray:
    appeared = train[train["target_appearance"].eq(1)]
    model = _models()["ridge"]
    model.fit(appeared[feature_columns], appeared["target_points_1gw"])
    return np.clip(model.predict(test[feature_columns]), 0, None)


def _with_positions(training: pd.DataFrame, current: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    combined = pd.concat([
        training[["element_type"]].assign(_source="training"),
        current[["element_type"]].assign(_source="current"),
    ])
    dummies = pd.get_dummies(combined["element_type"], prefix="position", dtype=int)
    training_dummies = dummies[combined["_source"].eq("training")].reset_index(drop=True)
    current_dummies = dummies[combined["_source"].eq("current")].reset_index(drop=True)
    training = pd.concat([training.reset_index(drop=True), training_dummies], axis=1)
    current = pd.concat([current.reset_index(drop=True), current_dummies], axis=1)
    return training, current, dummies.columns.tolist()


def _baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    medians = train.groupby("element_type")["prior_points_per_team_game"].median()
    overall = train["prior_points_per_team_game"].median()
    return test["prior_points_per_team_game"].fillna(test["element_type"].map(medians)).fillna(overall).to_numpy()


def _metrics(rows: pd.DataFrame, prediction: np.ndarray) -> dict:
    actual = rows["target_points_1gw"].to_numpy()
    top_predicted = np.argsort(prediction)[-10:]
    top_actual = np.argsort(actual)[-10:]
    oracle_points = actual[top_actual].sum()
    captain_index = int(np.argmax(prediction))
    return {
        "rows": int(len(rows)),
        "mae": round(float(mean_absolute_error(actual, prediction)), 4),
        "rmse": round(float(mean_squared_error(actual, prediction) ** 0.5), 4),
        "spearman_rank_correlation": round(
            float(pd.Series(prediction).corr(pd.Series(actual), method="spearman")), 4
        ),
        "mean_prediction": round(float(np.mean(prediction)), 4),
        "mean_actual": round(float(np.mean(actual)), 4),
        "top_10_overlap": round(len(set(top_predicted).intersection(top_actual)) / 10, 4),
        "top_10_points_capture": round(float(actual[top_predicted].sum() / oracle_points), 4) if oracle_points else None,
        "captain_regret": round(float(actual.max() - actual[captain_index]), 4),
    }


def evaluate(training: pd.DataFrame, feature_columns: list[str], test_seasons: list[str]) -> dict:
    results = {}
    for season in test_seasons:
        train = training[training["season"] < season].copy()
        test = training[training["season"] == season].copy()
        if train.empty or test.empty:
            raise ValueError(f"Insufficient chronological rows for {season}")
        baseline_prediction = _baseline(train, test)
        season_report = {
            "training_seasons": sorted(train["season"].unique().tolist()),
            "baseline_prior_points_per_team_game": _metrics(test, baseline_prediction),
        }
        minute_probabilities = _minute_probabilities(train, test, feature_columns)
        season_report["minutes_risk"] = {
            name: _probability_metrics(test[MINUTE_TARGETS[name]], prediction)
            for name, prediction in minute_probabilities.items()
        }
        conditional_points = _conditional_points_model(train, test, feature_columns)
        two_stage_points = minute_probabilities["appearance_probability"] * conditional_points
        season_report["two_stage_expected_points"] = _metrics(test, two_stage_points)
        season_report["minutes_risk_subgroups"] = {}
        for subgroup in ("changed_team", "promoted_team"):
            mask = test[subgroup].eq(1)
            if mask.any():
                season_report["minutes_risk_subgroups"][subgroup] = {
                    "rows": int(mask.sum()),
                    "appearance_brier_score": round(float(brier_score_loss(
                        test.loc[mask, "target_appearance"].astype(int),
                        minute_probabilities["appearance_probability"][mask.to_numpy()],
                    )), 4),
                    "points_mae": round(float(mean_absolute_error(
                        test.loc[mask, "target_points_1gw"],
                        two_stage_points[mask.to_numpy()],
                    )), 4),
                }
        for name, model in _models().items():
            model.fit(train[feature_columns], train["target_points_1gw"])
            prediction = np.clip(model.predict(test[feature_columns]), 0, None)
            season_report[name] = _metrics(test, prediction)
            if name == "ridge":
                blended = 0.75 * baseline_prediction + 0.25 * prediction
                season_report["blended_prior_ridge_25"] = _metrics(test, blended)
        results[season] = season_report
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate and train the FPL GW1 prior")
    parser.add_argument("--training", default="data/gw1_training.csv")
    parser.add_argument("--current", default="data/gw1_2026-27_candidates.csv")
    parser.add_argument("--test-seasons", nargs="+", default=["2023-24", "2024-25", "2025-26"])
    parser.add_argument("--report", default="data/gw1_prior_evaluation.json")
    parser.add_argument("--predictions", default="data/gw1_2026-27_predictions.csv")
    args = parser.parse_args()

    training = pd.read_csv(args.training, low_memory=False)
    current = pd.read_csv(args.current, low_memory=False)
    training, current, position_features = _with_positions(training, current)
    feature_columns = FEATURES + position_features

    evaluation = evaluate(training, feature_columns, args.test_seasons)
    selected = "two_stage_ridge_with_logistic_minutes_risk"
    raw_probabilities = _minute_probabilities(training, current, feature_columns)
    availability = current["availability_factor"].fillna(1.0).clip(0, 1).to_numpy()
    current["appearance_probability_before_availability"] = raw_probabilities["appearance_probability"]
    current["appearance_probability"] = raw_probabilities["appearance_probability"] * availability
    current["start_probability"] = np.minimum(
        raw_probabilities["start_probability"] * availability,
        current["appearance_probability"],
    )
    current["played_60_probability"] = np.minimum(
        raw_probabilities["played_60_probability"] * availability,
        current["start_probability"],
    )
    conditional_points = _conditional_points_model(training, current, feature_columns)
    current["predicted_points_given_appearance_gw1"] = conditional_points
    current["predicted_points_gw1_before_availability"] = (
        conditional_points * current["appearance_probability_before_availability"]
    )
    current["predicted_points_gw1"] = conditional_points * current["appearance_probability"]
    conditional_baseline = (
        current["prior_points_per_appearance"]
        .fillna(current["element_type"].map(
            training.groupby("element_type")["prior_points_per_appearance"].median()
        ))
        .fillna(training["prior_points_per_appearance"].median())
        .clip(lower=0)
    )
    baseline_expected_points = conditional_baseline * current["appearance_probability"]
    current["selection_score_gw1"] = (
        0.75 * baseline_expected_points + 0.25 * current["predicted_points_gw1"]
    )
    current["projected_minutes_gw1"] = (
        15 * (current["appearance_probability"] - current["start_probability"])
        + 45 * (current["start_probability"] - current["played_60_probability"])
        + 75 * current["played_60_probability"]
    ).clip(0, 90)
    current["model"] = selected

    output_columns = [
        "element", "code", "player_name", "team", "team_id", "element_type", "price",
        "predicted_points_gw1", "predicted_points_gw1_before_availability", "selection_score_gw1",
        "predicted_points_given_appearance_gw1", "projected_minutes_gw1",
        "appearance_probability", "appearance_probability_before_availability",
        "start_probability", "played_60_probability", "availability_factor",
        "has_prior_player_history", "changed_team", "promoted_team",
        "position_changed", "prior_points_per_team_game", "prior_minutes_per_team_game",
        "fixtures_next5", "home_fixtures_next5", "first_fixture_home",
        "mean_official_fdr_next5", "first_fixture_fdr", "penalty_order",
        "set_piece_order", "model",
    ]
    current[output_columns].sort_values("selection_score_gw1", ascending=False).to_csv(
        args.predictions, index=False
    )
    report = {
        "selected_model": selected,
        "feature_columns": feature_columns,
        "evaluation": evaluation,
        "current_candidates": int(len(current)),
        "current_with_prior_history": int(current["has_prior_player_history"].sum()),
        "current_changed_team": int(current["changed_team"].sum()),
        "current_promoted_team": int(current["promoted_team"].sum()),
        "availability_adjusted_players": int(current["availability_factor"].lt(1).sum()),
    }
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved predictions to {args.predictions}")


if __name__ == "__main__":
    main()
