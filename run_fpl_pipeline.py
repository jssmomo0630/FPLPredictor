#!/usr/bin/env python3
"""Unified entry point for preseason and finalized-data in-season forecasts."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from fpl_pipeline_config import (
    CURRENT_SEASON,
    HISTORICAL_SEASONS,
    VAASTAV_REF,
    missing_historical_seasons,
)



def _run(root: Path, *arguments: str) -> None:
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    subprocess.run(
        [sys.executable, *arguments], cwd=root, check=True, env=environment
    )


def _finalized_gameweeks(events_path: Path) -> list[int]:
    if not events_path.exists():
        return []
    events = pd.read_csv(events_path)
    if "data_checked" not in events:
        return []
    return sorted(events.loc[events["data_checked"].fillna(False).astype(bool), "id"].astype(int).tolist())


def _target_gameweek_from_status(path: str | None) -> int | None:
    if not path or Path(path).suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    next_event = payload.get("gameweek", {}).get("next")
    if isinstance(next_event, dict) and next_event.get("id") is not None:
        return int(next_event["id"])
    return None


def _free_transfers_from_status(path: str | None) -> int | None:
    if not path or Path(path).suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        value = payload.get("squad", {}).get("financial", {}).get("free_transfers")
        return int(value) if value is not None else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _chip_period_end(gameweek: int) -> int:
    if 1 <= gameweek <= 19:
        return 19
    if 20 <= gameweek <= 38:
        return 38
    raise ValueError(f"Gameweek {gameweek} is outside the supported FPL season")


def _automated_planning_horizon(gameweek: int, maximum: int = 5) -> int:
    """Use a short rolling horizon, truncated only at the active chip-set expiry."""
    return min(maximum, _chip_period_end(gameweek) - gameweek + 1)


def _ensure_historical_data(
    root: Path,
    data: Path,
    seasons: list[str],
    vaastav_ref: str,
    refresh: bool,
) -> None:
    requested = seasons if refresh else missing_historical_seasons(data, seasons)
    if not requested:
        print("Historical inputs are present.")
        return
    print(f"Downloading historical inputs for: {', '.join(requested)}")
    arguments = [
        "download_history_data.py",
        "--data-root", str(data),
        "--ref", vaastav_ref,
        "--seasons", *requested,
        "--no-summary",
    ]
    if not refresh:
        arguments.append("--skip-existing")
    _run(root, *arguments)
    missing = missing_historical_seasons(data, seasons)
    if missing:
        raise RuntimeError(f"Missing historical inputs after download: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the current FPL forecast pipeline")
    parser.add_argument("--season", default=CURRENT_SEASON)
    parser.add_argument("--historical-seasons", nargs="+", default=list(HISTORICAL_SEASONS))
    parser.add_argument("--vaastav-ref", default=VAASTAV_REF)
    parser.add_argument(
        "--refresh-history", action="store_true",
        help="Redownload all historical inputs instead of only missing seasons",
    )
    parser.add_argument("--refresh", action="store_true", help="Refresh official data before forecasting")
    parser.add_argument(
        "--experimental-transfers", action="store_true",
        help="Generate the experimental multi-GW transfer advisory (used by Actions)",
    )
    parser.add_argument("--current-squad", help="Current 15-player CSV or entry-snapshot JSON")
    parser.add_argument(
        "--free-transfers", type=int,
        help="Override available free transfers; otherwise infer them from a status JSON",
    )
    parser.add_argument("--bank", type=float, help="Current bank in millions")
    parser.add_argument(
        "--target-gameweek", type=int,
        help="Upcoming deadline gameweek; inferred from a status JSON when available",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    historical = list(args.historical_seasons)
    _ensure_historical_data(
        root, data, historical, args.vaastav_ref, refresh=args.refresh_history
    )
    if args.refresh:
        _run(root, "download_current_season.py", "--season", args.season)

    _run(root, "normalize_gameweeks.py", "--seasons", *historical, "--output", "data/canonical_gameweeks.csv")
    gw1_candidates = f"data/gw1_{args.season}_candidates.csv"
    gw1_predictions = f"data/gw1_{args.season}_predictions.csv"
    _run(
        root, "build_gw1_dataset.py", "--current-season", args.season,
        "--current-output", gw1_candidates,
    )
    _run(
        root, "train_gw1_prior.py", "--current", gw1_candidates,
        "--predictions", gw1_predictions,
    )

    finalized = _finalized_gameweeks(data / args.season / "events.csv")
    requested_target = args.target_gameweek or _target_gameweek_from_status(args.current_squad)
    if not finalized:
        predictions = gw1_predictions
        target_gameweek = requested_target or 1
        print(f"No finalized {args.season} gameweeks. Using {predictions}")
    else:
        target_gameweek = requested_target or max(finalized) + 1
        if target_gameweek <= max(finalized):
            raise SystemExit(
                f"Target GW{target_gameweek} is not after latest finalized GW{max(finalized)}"
            )
        seasons = [*historical, args.season]
        _run(root, "normalize_gameweeks.py", "--seasons", *seasons, "--output", "data/canonical_gameweeks.csv")
        _run(root, "normalize_fixtures.py", "--seasons", *seasons, "--output", "data/canonical_fixtures.csv")
        _run(root, "build_forecast_dataset.py")
        _run(root, "build_fixture_features.py")
        _run(
            root, "build_inseason_candidates.py", "--players", f"data/{args.season}/players_raw.csv",
            "--season", args.season, "--target-gw", str(target_gameweek),
        )
        _run(root, "train_inseason_model.py")
        _run(root, "blend_forecasts.py", "--prior", gw1_predictions,
             "--current", "data/inseason_predictions.csv")
        predictions = "data/blended_next_gw_predictions.csv"
        print(f"Current forecast: {predictions}")
    _run(root, "optimize_squad.py", "--predictions", predictions)
    _run(root, "evaluate_squad_optimizer.py", "--predictions", predictions)
    print("Current squad: data/optimal_squad.csv and data/optimal_squad.json")
    if args.experimental_transfers:
        if not args.current_squad:
            raise SystemExit("--experimental-transfers requires --current-squad")
        seasons = [*historical, args.season]
        _run(root, "normalize_fixtures.py", "--seasons", *seasons, "--output", "data/canonical_fixtures.csv")
        _run(root, "build_fixture_features.py")
        planning_horizon = _automated_planning_horizon(target_gameweek)
        _run(
            root, "build_transfer_forecasts.py", "--predictions", predictions,
            "--season", args.season, "--start-gameweek", str(target_gameweek),
            "--horizon", str(planning_horizon),
        )
        free_transfers = (
            args.free_transfers
            if args.free_transfers is not None
            else (_free_transfers_from_status(args.current_squad) or 1)
        )
        transfer_args = [
            "plan_transfers.py", "--current-squad", args.current_squad,
            "--free-transfers", str(free_transfers),
            "--season", args.season,
            "--horizon", str(planning_horizon),
            "--chip-horizon", str(planning_horizon),
        ]
        if args.bank is not None:
            transfer_args.extend(["--bank", str(args.bank)])
        _run(root, *transfer_args)
        print("Experimental transfer advisory: data/transfer_plan.csv and data/transfer_plan.json")


if __name__ == "__main__":
    main()
