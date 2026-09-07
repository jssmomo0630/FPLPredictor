#!/usr/bin/env python3
"""Deadline gate and persistent deduplication for scheduled FPL advice."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def owned_availability_snapshot(status: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "element": int(player["element"]),
                "availability": player.get("availability"),
                "status": player.get("status"),
                "chance": player.get("chance_of_playing_next_round"),
            }
            for player in status.get("squad", {}).get("players", [])
            if player.get("element") is not None
        ],
        key=lambda row: row["element"],
    )


def recommendation_snapshot(advice: dict[str, Any]) -> dict[str, Any]:
    recommendation = advice.get("recommendation", {})
    chip_advice = recommendation.get("chip_advice") or {}

    def chip_slot(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            "chip": value.get("chip"),
            "gameweek": value.get("gameweek"),
        }

    return {
        "target_gameweek": advice.get("target_gameweek"),
        "transfers_out": sorted(
            int(row["element"]) for row in recommendation.get("transfers_out", [])
        ),
        "transfers_in": sorted(
            int(row["element"]) for row in recommendation.get("transfers_in", [])
        ),
        "paid_transfers": recommendation.get("paid_transfers"),
        "hit_cost_points": recommendation.get("hit_cost_points"),
        "starting_xi": sorted(
            int(row["element"]) for row in recommendation.get("starting_xi", [])
        ),
        "captain": (recommendation.get("captain") or {}).get("element"),
        "vice_captain": (recommendation.get("vice_captain") or {}).get("element"),
        "bench": [
            int(row["element"]) for row in recommendation.get("bench", [])
        ],
        "chip": {
            "recommended_now": chip_slot(chip_advice.get("recommended")),
            "next_planned": chip_slot(chip_advice.get("next_planned")),
        },
    }


def preflight(
    status: dict[str, Any],
    state: dict[str, Any],
    window_hours: float = 48.0,
    rerun_hours: float = 6.0,
) -> dict[str, Any]:
    next_event = status.get("gameweek", {}).get("next") or {}
    gameweek = next_event.get("id")
    hours = status.get("gameweek", {}).get("hours_to_deadline")
    in_window = (
        gameweek is not None
        and isinstance(hours, (int, float))
        and 0 <= float(hours) <= window_hours
    )
    same_gameweek = bool(in_window and state.get("target_gameweek") == int(gameweek))
    current_availability_hash = _hash(owned_availability_snapshot(status))
    availability_changed = bool(
        same_gameweek
        and state.get("owned_availability_hash")
        and state.get("owned_availability_hash") != current_availability_hash
    )
    last_evaluated = _parse_time(state.get("evaluated_at_utc")) if same_gameweek else None
    checked_at = _parse_time(status.get("checked_at_utc")) or datetime.now(timezone.utc)
    elapsed_hours = (
        (checked_at - last_evaluated).total_seconds() / 3600
        if last_evaluated is not None else None
    )
    first_in_window = bool(in_window and not same_gameweek)
    interval_due = bool(
        in_window and same_gameweek
        and (elapsed_hours is None or elapsed_hours >= rerun_hours)
    )
    should_run = bool(first_in_window or availability_changed or interval_due)
    reasons = []
    if first_in_window:
        reasons.append("entered_48h_window")
    if availability_changed:
        reasons.append("owned_availability_changed")
    if interval_due:
        reasons.append("six_hour_refresh_due")
    if not in_window:
        reasons.append("outside_48h_window")
    elif not should_run:
        reasons.append("waiting_for_six_hour_refresh")
    return {
        "target_gameweek": int(gameweek) if gameweek is not None else None,
        "hours_to_deadline": hours,
        "in_window": in_window,
        "should_run": should_run,
        "owned_availability_changed": availability_changed,
        "hours_since_last_evaluation": round(elapsed_hours, 3) if elapsed_hours is not None else None,
        "reasons": reasons,
    }


def compare_and_update(
    status: dict[str, Any],
    advice: dict[str, Any],
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    gameweek = int(advice["target_gameweek"])
    same_gameweek = state.get("target_gameweek") == gameweek
    owned_snapshot = owned_availability_snapshot(status)
    owned_hash = _hash(owned_snapshot)
    recommendation = recommendation_snapshot(advice)
    recommendation_hash = _hash(recommendation)
    first_recommendation = not same_gameweek or not state.get("recommendation_hash")
    availability_changed = bool(
        same_gameweek
        and state.get("owned_availability_hash")
        and state.get("owned_availability_hash") != owned_hash
    )
    recommendation_changed = bool(
        same_gameweek
        and state.get("recommendation_hash")
        and state.get("recommendation_hash") != recommendation_hash
    )
    should_email = bool(first_recommendation or availability_changed or recommendation_changed)
    reasons = []
    if first_recommendation:
        reasons.append("first_recommendation_for_gameweek")
    if availability_changed:
        reasons.append("owned_availability_changed")
    if recommendation_changed:
        reasons.append("recommendation_changed")
    if not reasons:
        reasons.append("duplicate_recommendation")

    evaluated_at = status.get("checked_at_utc") or datetime.now(timezone.utc).isoformat()
    updated_state = {
        "schema_version": 1,
        "entry_id": status.get("entry_id"),
        "target_gameweek": gameweek,
        "evaluated_at_utc": evaluated_at,
        "owned_availability": owned_snapshot,
        "owned_availability_hash": owned_hash,
        "recommendation": recommendation,
        "recommendation_hash": recommendation_hash,
        "last_email_at_utc": evaluated_at if should_email else state.get("last_email_at_utc"),
        "last_email_reasons": reasons if should_email else state.get("last_email_reasons", []),
    }
    decision = {
        "should_email": should_email,
        "first_recommendation": first_recommendation,
        "owned_availability_changed": availability_changed,
        "recommendation_changed": recommendation_changed,
        "reasons": reasons,
    }
    return decision, updated_state


def _write_outputs(path: str | None, values: dict[str, Any]) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if isinstance(value, bool):
                rendered = str(value).lower()
            elif value is None:
                rendered = ""
            elif isinstance(value, (list, dict)):
                rendered = json.dumps(value, separators=(",", ":"))
            else:
                rendered = str(value)
            handle.write(f"{key}={rendered}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate and deduplicate scheduled FPL advice")
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate = subparsers.add_parser("gate")
    gate.add_argument("--status", default="artifacts/fpl_status.json")
    gate.add_argument("--state", default=".fpl-monitor/state.json")
    gate.add_argument("--window-hours", type=float, default=48.0)
    gate.add_argument("--rerun-hours", type=float, default=6.0)
    gate.add_argument("--github-output")
    compare = subparsers.add_parser("compare")
    compare.add_argument("--status", default="artifacts/fpl_status.json")
    compare.add_argument("--advice", default="artifacts/fpl_advice.json")
    compare.add_argument("--state", default=".fpl-monitor/state.json")
    compare.add_argument("--github-output")
    args = parser.parse_args()

    status = json.loads(Path(args.status).read_text(encoding="utf-8"))
    state_path = Path(args.state)
    state = _read_state(state_path)
    if args.command == "gate":
        result = preflight(status, state, args.window_hours, args.rerun_hours)
        _write_outputs(args.github_output, result)
    else:
        advice = json.loads(Path(args.advice).read_text(encoding="utf-8"))
        result, updated_state = compare_and_update(status, advice, state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(updated_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _write_outputs(args.github_output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
