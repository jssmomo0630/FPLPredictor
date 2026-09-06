#!/usr/bin/env python3
"""Blend the preseason prior with an in-season next-GW forecast by evidence."""

import argparse

import pandas as pd


def blend_forecasts(
    prior: pd.DataFrame,
    current: pd.DataFrame,
    prior_column: str = "predicted_points_gw1",
    current_column: str = "predicted_points_next_gw",
    minutes_column: str = "current_season_minutes",
) -> pd.DataFrame:
    """Increase in-season weight smoothly, capped to retain prior stability."""
    required_prior = {"element", prior_column}
    required_current = {"element", current_column, minutes_column}
    if missing := required_prior.difference(prior.columns):
        raise ValueError(f"Prior input is missing: {sorted(missing)}")
    if missing := required_current.difference(current.columns):
        raise ValueError(f"Current input is missing: {sorted(missing)}")
    result = prior.merge(
        current[["element", current_column, minutes_column]],
        on="element", how="left", validate="one_to_one",
    )
    minutes = pd.to_numeric(result[minutes_column], errors="coerce").fillna(0).clip(lower=0)
    result["inseason_weight"] = (minutes / (minutes + 450)).clip(upper=0.85)
    result["prior_weight"] = 1 - result["inseason_weight"]
    current_points = result[current_column].fillna(result[prior_column])
    result["blended_points_next_gw"] = (
        result["prior_weight"] * result[prior_column]
        + result["inseason_weight"] * current_points
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
