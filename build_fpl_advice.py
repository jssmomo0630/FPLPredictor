#!/usr/bin/env python3
"""Combine public FPL status and optimizer output into advisory-only JSON."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _player(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "element": int(row["element"]),
        "player_name": row["player_name"],
        "position": row["position"],
        "team_id": int(row["team_id"]),
        "price_millions": int(float(row["price"])) / 10,
        "expected_points": round(float(row["expected_points"]), 3),
        "is_captain": _truthy(row.get("is_captain")),
        "is_vice_captain": _truthy(row.get("is_vice_captain")),
    }


def build_advice(
    status: dict[str, Any],
    plan: dict[str, Any],
    plan_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if status.get("read_only") is not True:
        raise ValueError("Status input must be marked read_only=true")
    next_event = status.get("gameweek", {}).get("next") or {}
    target_gameweek = next_event.get("id")
    if target_gameweek is None:
        raise ValueError("No upcoming gameweek is available for advice")
    target_gameweek = int(target_gameweek)
    week = next(
        (row for row in plan.get("weeks", []) if int(row["gameweek"]) == target_gameweek),
        None,
    )
    if week is None:
        raise ValueError(f"Transfer plan does not contain GW{target_gameweek}")
    selected = [row for row in plan_rows if int(row["gameweek"]) == target_gameweek]
    if len(selected) != 15:
        raise ValueError(f"Expected 15 planned players for GW{target_gameweek}, got {len(selected)}")

    starters = [_player(row) for row in selected if row.get("role") == "starting_xi"]
    bench = [_player(row) | {"bench_order": int(row["bench_order"])} for row in selected if row.get("role") != "starting_xi"]
    bench.sort(key=lambda row: row["bench_order"])
    if len(starters) != 11 or len(bench) != 4:
        raise ValueError("Planned lineup must contain 11 starters and four bench players")
    captain = next((row for row in starters if row["is_captain"]), None)
    vice = next((row for row in starters if row["is_vice_captain"]), None)
    if captain is None or vice is None:
        raise ValueError("Planned lineup must identify a captain and vice-captain")

    transfers_in = week.get("transfers_in", [])
    transfers_out = week.get("transfers_out", [])
    transfer_count = int(week.get("transfers_used", len(transfers_in)))
    if transfer_count:
        pairs = [
            f"{outgoing.get('player_name')} → {incoming.get('player_name')}"
            for outgoing, incoming in zip(transfers_out, transfers_in)
        ]
        headline = f"Make {transfer_count} transfer(s): " + ", ".join(pairs)
    else:
        headline = "Roll the transfer; keep the published squad"

    bank_units = status.get("squad", {}).get("financial", {}).get("bank_units")
    financial = status.get("squad", {}).get("financial", {})
    inferred_free_transfers = financial.get("free_transfers")
    planned_free_transfers = int(plan.get("initial_free_transfers", 1))
    if inferred_free_transfers is not None and planned_free_transfers == int(inferred_free_transfers):
        free_transfer_warning = (
            f"The {planned_free_transfers} free transfers were inferred from public history at "
            "the previous deadline. Transfers made after that deadline are not publicly visible."
        )
    elif inferred_free_transfers is not None:
        free_transfer_warning = (
            f"The planner used an override of {planned_free_transfers}; public history inferred "
            f"{int(inferred_free_transfers)} before any pending transfers."
        )
    else:
        free_transfer_warning = (
            f"The planner assumed {planned_free_transfers} free transfers because no public-history "
            "estimate was available."
        )
    source_event = status.get("squad", {}).get("source_event_id")
    deterministic_summary = (
        f"{headline}. Start {', '.join(row['player_name'] for row in starters)}. "
        f"Captain {captain['player_name']} and vice-captain {vice['player_name']}. "
        f"Bench order: {', '.join(row['player_name'] for row in bench)}."
    )
    chip_advice = plan.get("chip_advice", {})
    return {
        "schema_version": 1,
        "read_only": True,
        "advisory_only": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entry_id": status.get("entry_id"),
        "target_gameweek": target_gameweek,
        "deadline_time_local": status.get("gameweek", {}).get("deadline_time_local"),
        "hours_to_deadline": status.get("gameweek", {}).get("hours_to_deadline"),
        "source_squad_gameweek": source_event,
        "recommendation": {
            "headline": headline,
            "transfers_used": transfer_count,
            "paid_transfers": int(week.get("paid_transfers", 0)),
            "hit_cost_points": float(week.get("hit_cost", 0)),
            "transfers_out": transfers_out,
            "transfers_in": transfers_in,
            "bank_after_millions": int(week.get("bank_after", 0)) / 10,
            "starting_xi": starters,
            "captain": captain,
            "vice_captain": vice,
            "bench": bench,
            "chip_advice": {
                "recommendation": chip_advice.get("recommendation"),
                "recommended": chip_advice.get("recommended"),
                "chip_period": chip_advice.get("chip_period"),
                "method_note": chip_advice.get("method_note"),
            },
            "opponent_conflicts": week.get("opponent_conflicts", []),
            "opponent_conflict_penalty_points": float(
                week.get("opponent_conflict_penalty_points", 0)
            ),
        },
        "deterministic_summary": deterministic_summary,
        "assumptions": {
            "free_transfers_assumed": planned_free_transfers,
            "free_transfers_status_estimate": inferred_free_transfers,
            "free_transfers_source": financial.get("free_transfers_source"),
            "bank_from_locked_squad_millions": bank_units / 10 if isinstance(bank_units, (int, float)) else None,
            "selling_price_source": plan.get("selling_price_source"),
            "selling_price_warning": plan.get("selling_price_warning"),
            "public_squad_warning": (
                f"Based on the public squad locked at the GW{source_event} deadline; "
                "transfers made afterward are not visible without authentication."
            ),
            "free_transfer_warning": free_transfer_warning,
            "forecast_warning": plan.get("forecast_note"),
            "opponent_conflict_method": (
                "Each starting MID/FWD versus an opposing starting GK/DEF receives a "
                f"{float(plan.get('opponent_conflict_penalty', 0)):.2f}-point soft penalty. "
                "It is not prohibited because fixture difficulty is already reflected in forecasts."
            ),
        },
        "prohibited_actions": [
            "submit transfers",
            "activate chips",
            "change captain or vice-captain",
            "change lineup or bench order",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a read-only FPL recommendation report")
    parser.add_argument("--status", default="artifacts/fpl_status.json")
    parser.add_argument("--plan", default="data/transfer_plan.json")
    parser.add_argument("--plan-rows", default="data/transfer_plan.csv")
    parser.add_argument("--output", default="artifacts/fpl_advice.json")
    args = parser.parse_args()
    advice = build_advice(
        json.loads(Path(args.status).read_text(encoding="utf-8")),
        json.loads(Path(args.plan).read_text(encoding="utf-8")),
        _load_rows(Path(args.plan_rows)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(advice, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "target_gameweek": advice["target_gameweek"],
        "headline": advice["recommendation"]["headline"],
        "advisory_only": advice["advisory_only"],
    }, indent=2))


if __name__ == "__main__":
    main()
