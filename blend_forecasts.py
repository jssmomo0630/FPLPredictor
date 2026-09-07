#!/usr/bin/env python3
"""Blend the preseason prior with an in-season next-GW forecast by evidence."""

import argparse

import numpy as np
import pandas as pd


OPPORTUNITY_PRIOR_GAMEWEEKS = 2.0
CHANGED_TEAM_OPPORTUNITY_PRIOR_GAMEWEEKS = 0.5


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _probability_before_availability(
    frame: pd.DataFrame,
    probability_column: str,
    availability: pd.Series,
    fallback: pd.Series,
) -> pd.Series:
    probability = _numeric(frame, probability_column, np.nan)
    restored = probability.div(availability.replace(0, np.nan))
    return restored.fillna(fallback).clip(0, 1)


def _update_role_probabilities(result: pd.DataFrame) -> pd.DataFrame:
    """Update preseason opportunity estimates using up to five finalized GWs."""
    preseason_availability = _numeric(result, "availability_factor", 1.0).clip(0, 1)
    prior_appearance = _numeric(
        result, "appearance_probability_before_availability", np.nan
    ).fillna(_numeric(result, "appearance_probability", 1.0)).clip(0, 1)
    prior_start = _probability_before_availability(
        result, "start_probability", preseason_availability, prior_appearance
    )
    prior_played_60 = _probability_before_availability(
        result, "played_60_probability", preseason_availability, prior_start
    )

    observations = _numeric(result, "role_observation_gameweeks").clip(0, 5)
    appearances = _numeric(result, "role_appearances").clip(0, observations)
    starts = _numeric(result, "role_starts").clip(0, appearances)
    played_60 = _numeric(result, "role_played_60").clip(0, starts)
    changed_team = _numeric(result, "changed_team").gt(0)
    prior_strength = pd.Series(
        np.where(
            changed_team,
            CHANGED_TEAM_OPPORTUNITY_PRIOR_GAMEWEEKS,
            OPPORTUNITY_PRIOR_GAMEWEEKS,
        ),
        index=result.index,
        dtype=float,
    )
    denominator = prior_strength + observations
    appearance_before_availability = (
        prior_strength * prior_appearance + appearances
    ).div(denominator).clip(0, 1)
    start_before_availability = (
        prior_strength * prior_start + starts
    ).div(denominator).clip(0, appearance_before_availability)
    played_60_before_availability = (
        prior_strength * prior_played_60 + played_60
    ).div(denominator).clip(0, start_before_availability)

    current_availability = _numeric(
        result, "current_availability_factor", 1.0
    ).clip(0, 1)
    prior_projected_minutes = _numeric(result, "projected_minutes_gw1", np.nan)
    prior_conditional_minutes = prior_projected_minutes.div(
        prior_appearance.replace(0, np.nan)
    )
    fallback_conditional_minutes = (
        15 * (prior_appearance - prior_start)
        + 45 * (prior_start - prior_played_60)
        + 75 * prior_played_60
    ).div(prior_appearance.replace(0, np.nan))
    result["preseason_conditional_minutes"] = (
        prior_conditional_minutes.fillna(fallback_conditional_minutes).fillna(0).clip(0, 90)
    )
    result["preseason_appearance_probability"] = prior_appearance
    result["opportunity_prior_gameweeks"] = prior_strength
    result["appearance_probability_before_availability"] = appearance_before_availability
    result["appearance_probability"] = appearance_before_availability * current_availability
    result["start_probability"] = np.minimum(
        start_before_availability * current_availability,
        result["appearance_probability"],
    )
    result["played_60_probability"] = np.minimum(
        played_60_before_availability * current_availability,
        result["start_probability"],
    )
    result["availability_factor"] = current_availability
    result["projected_minutes_next_gw"] = (
        15 * (result["appearance_probability"] - result["start_probability"])
        + 45 * (result["start_probability"] - result["played_60_probability"])
        + 75 * result["played_60_probability"]
    ).clip(0, 90)
    result["current_role_conditional_minutes"] = result[
        "projected_minutes_next_gw"
    ].div(result["appearance_probability"].replace(0, np.nan)).fillna(0).clip(0, 90)
    result["role_duration_factor"] = result[
        "current_role_conditional_minutes"
    ].div(result["preseason_conditional_minutes"].replace(0, np.nan)).fillna(0).clip(0, 1.5)
    return result


def blend_forecasts(
    prior: pd.DataFrame,
    current: pd.DataFrame,
    prior_column: str = "predicted_points_gw1",
    current_column: str = "predicted_points_next_gw",
    minutes_column: str = "current_season_minutes",
) -> pd.DataFrame:
    """Blend ability slowly while updating current playing opportunity quickly."""
    required_prior = {"element", prior_column, "appearance_probability"}
    required_current = {
        "element", current_column, minutes_column, "availability_factor",
        "role_observation_gameweeks", "role_appearances", "role_starts",
        "role_played_60",
    }
    if missing := required_prior.difference(prior.columns):
        raise ValueError(f"Prior input is missing: {sorted(missing)}")
    if missing := required_current.difference(current.columns):
        raise ValueError(f"Current input is missing: {sorted(missing)}")
    current_columns = list(required_current)
    if "predicted_points_next_gw_before_availability" in current:
        current_columns.append("predicted_points_next_gw_before_availability")
    current_input = current[current_columns].rename(
        columns={"availability_factor": "current_availability_factor"}
    )
    result = prior.merge(
        current_input,
        on="element", how="left", validate="one_to_one",
    )
    result = _update_role_probabilities(result)
    minutes = pd.to_numeric(result[minutes_column], errors="coerce").fillna(0).clip(lower=0)
    result["inseason_weight"] = (minutes / (minutes + 450)).clip(upper=0.85)
    result["inseason_ability_weight"] = result["inseason_weight"]
    result["prior_weight"] = 1 - result["inseason_weight"]
    prior_expected = pd.to_numeric(result[prior_column], errors="coerce").fillna(0).clip(lower=0)
    prior_conditional = _numeric(
        result, "predicted_points_given_appearance_gw1", np.nan
    ).fillna(
        prior_expected.div(
            result["preseason_appearance_probability"].replace(0, np.nan)
        )
    ).fillna(prior_expected).clip(0, 20)
    current_before_availability = _numeric(
        result, "predicted_points_next_gw_before_availability", np.nan
    )
    if current_before_availability.isna().all():
        current_before_availability = pd.to_numeric(
            result[current_column], errors="coerce"
        ).div(result["availability_factor"].replace(0, np.nan))
    current_conditional = current_before_availability.div(
        result["appearance_probability_before_availability"].clip(lower=0.05)
    ).fillna(prior_conditional).clip(0, 20)
    result["blended_points_given_preseason_role_appearance_next_gw"] = (
        result["prior_weight"] * prior_conditional
        + result["inseason_weight"] * current_conditional
    )
    result["blended_points_given_appearance_next_gw"] = (
        result["blended_points_given_preseason_role_appearance_next_gw"]
        * result["role_duration_factor"]
    )
    result["blended_points_next_gw_before_availability"] = (
        result["blended_points_given_appearance_next_gw"]
        * result["appearance_probability_before_availability"]
    )
    result["blended_points_next_gw"] = (
        result["blended_points_given_appearance_next_gw"]
        * result["appearance_probability"]
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Blend preseason and in-season FPL forecasts")
    parser.add_argument("--prior", default="data/gw1_2026-27_predictions.csv")
    parser.add_argument("--current", required=True)
    parser.add_argument("--output", default="data/blended_next_gw_predictions.csv")
    parser.add_argument("--prior-column", default="predicted_points_gw1")
    parser.add_argument("--current-column", default="predicted_points_next_gw")
    parser.add_argument("--minutes-column", default="current_season_minutes")
    args = parser.parse_args()
    result = blend_forecasts(
        pd.read_csv(args.prior), pd.read_csv(args.current),
        args.prior_column, args.current_column, args.minutes_column,
    )
    result.to_csv(args.output, index=False)
    print(f"Wrote {len(result):,} blended forecasts to {args.output}")


if __name__ == "__main__":
    main()
