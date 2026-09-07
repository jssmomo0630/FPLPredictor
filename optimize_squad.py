#!/usr/bin/env python3
"""Optimise an FPL squad, lineup, bench order, captain, and vice-captain."""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model


SQUAD_POSITION_COUNTS = {1: 2, 2: 5, 3: 5, 4: 3}
POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
DEFAULT_POINT_COLUMNS = [
    "blended_points_next_gw", "predicted_points_next_gw", "predicted_points_gw1",
]
DEFAULT_BENCH_PROBABILITIES = (0.15, 0.05, 0.02)


def _choose_column(frame: pd.DataFrame, requested: str | None) -> str:
    if requested:
        if requested not in frame:
            raise ValueError(f"Point column {requested!r} does not exist")
        return requested
    for column in DEFAULT_POINT_COLUMNS:
        if column in frame:
            return column
    raise ValueError(f"No expected-points column found; tried {DEFAULT_POINT_COLUMNS}")


def _prepare_candidates(frame: pd.DataFrame, point_column: str) -> pd.DataFrame:
    required = {"element", "player_name", "element_type", "price", point_column}
    if missing := required.difference(frame.columns):
        raise ValueError(f"Prediction input is missing columns: {sorted(missing)}")
    club_column = "team_id" if "team_id" in frame and frame["team_id"].notna().all() else "team"
    if club_column not in frame:
        raise ValueError("Prediction input needs team_id or team for the club constraint")
    candidates = frame.copy()
    candidates["element"] = pd.to_numeric(candidates["element"], errors="raise").astype(int)
    candidates["element_type"] = pd.to_numeric(candidates["element_type"], errors="coerce")
    candidates["price"] = pd.to_numeric(candidates["price"], errors="coerce")
    candidates["expected_points"] = pd.to_numeric(candidates[point_column], errors="coerce")
    candidates["minutes_risk_available"] = "appearance_probability" in frame
    appearance = (
        candidates["appearance_probability"]
        if "appearance_probability" in candidates
        else pd.Series(1.0, index=candidates.index)
    )
    candidates["appearance_probability"] = pd.to_numeric(
        appearance, errors="coerce"
    ).fillna(1.0).clip(0, 1)
    candidates = candidates[
        candidates["element_type"].isin(SQUAD_POSITION_COUNTS)
        & candidates["price"].gt(0) & candidates["expected_points"].notna()
    ].copy()
    candidates["element_type"] = candidates["element_type"].astype(int)
    candidates["price"] = candidates["price"].round().astype(int)
    candidates["expected_points"] = candidates["expected_points"].clip(lower=0)
    candidates["club"] = candidates[club_column].astype(str)
    candidates = candidates.sort_values("element").drop_duplicates("element", keep="last").reset_index(drop=True)
    for position, count in SQUAD_POSITION_COUNTS.items():
        if (candidates["element_type"] == position).sum() < count:
            raise ValueError(f"Not enough {POSITION_NAMES[position]} candidates")
    return candidates


def _lineup_objective(
    candidates: pd.DataFrame,
    starter: set[int],
    captain: int,
    vice: int,
    bench_gk: int,
    bench_slots: list[int],
    bench_probabilities: tuple[float, float, float] | None,
    bench_gk_probability: float,
    vice_probability: float,
) -> dict:
    points = candidates.set_index("element")["expected_points"].to_dict()
    appearances = candidates.set_index("element")["appearance_probability"].to_dict()
    positions = candidates.set_index("element")["element_type"].to_dict()
    starting = sum(points[element] for element in starter)
    captain_bonus = points[captain]
    vice_fallback = vice_probability * points[vice]
    if bench_probabilities is None:
        starting_gk = next(element for element in starter if positions[element] == 1)
        bench_gk_use_probability = 1 - appearances[starting_gk]
        outfield_nonappearance_risk = sum(
            1 - appearances[element] for element in starter if positions[element] != 1
        )
        outfield_probabilities = tuple(
            1 - math.exp(-outfield_nonappearance_risk) * sum(
                outfield_nonappearance_risk ** power / math.factorial(power)
                for power in range(required_absences)
            )
            for required_absences in (1, 2, 3)
        )
        autosub_mode = "player_nonappearance_risk"
    else:
        bench_gk_use_probability = bench_gk_probability
        outfield_probabilities = bench_probabilities
        autosub_mode = "fixed_override"
    bench_gk_value = bench_gk_use_probability * points[bench_gk]
    outfield_bench_value = sum(
        probability * points[element]
        for element, probability in zip(bench_slots, outfield_probabilities)
    )
    return {
        "starting_xi_points": float(starting),
        "captain_bonus": float(captain_bonus),
        "vice_captain_fallback_value": float(vice_fallback),
        "bench_gk_expected_value": float(bench_gk_value),
        "outfield_bench_expected_value": float(outfield_bench_value),
        "autosub_probability_mode": autosub_mode,
        "outfield_bench_use_probabilities_by_order": list(outfield_probabilities),
        "bench_goalkeeper_use_probability": float(bench_gk_use_probability),
        "objective": float(starting + captain_bonus + vice_fallback + bench_gk_value + outfield_bench_value),
    }


def optimise(
    candidates: pd.DataFrame,
    budget: int = 1000,
    bench_probabilities: tuple[float, float, float] | None = None,
    bench_gk_probability: float = 0.05,
    vice_probability: float = 0.05,
    time_limit: float = 30.0,
) -> tuple[pd.DataFrame, dict]:
    """Return an exact CP-SAT solution and its objective breakdown."""
    dynamic_autosubs = bench_probabilities is None and candidates["minutes_risk_available"].all()
    if dynamic_autosubs:
        probabilities = DEFAULT_BENCH_PROBABILITIES
        goalkeeper_probability = bench_gk_probability
        result = None
        breakdown = None
        iterations = 0
        per_solve_limit = max(2.0, time_limit / 4)
        for iterations in range(1, 5):
            result, breakdown = optimise(
                candidates, budget, probabilities, goalkeeper_probability,
                vice_probability, per_solve_limit,
            )
            starter_ids = set(
                result.loc[result["role"].eq("starting_xi"), "element"].astype(int)
            )
            captain_id = int(result.loc[result["is_captain"], "element"].iloc[0])
            vice_id = int(result.loc[result["is_vice_captain"], "element"].iloc[0])
            bench_gk_id = int(result.loc[result["role"].eq("bench_gk"), "element"].iloc[0])
            bench_ids = (
                result.loc[result["role"].eq("bench")]
                .sort_values("bench_order")["element"].astype(int).tolist()
            )
            risk_breakdown = _lineup_objective(
                candidates, starter_ids, captain_id, vice_id, bench_gk_id, bench_ids,
                None, goalkeeper_probability, vice_probability,
            )
            updated_probabilities = tuple(
                risk_breakdown["outfield_bench_use_probabilities_by_order"]
            )
            updated_goalkeeper_probability = risk_breakdown[
                "bench_goalkeeper_use_probability"
            ]
            converged = (
                max(abs(a - b) for a, b in zip(probabilities, updated_probabilities)) < 0.005
                and abs(goalkeeper_probability - updated_goalkeeper_probability) < 0.005
            )
            probabilities = updated_probabilities
            goalkeeper_probability = updated_goalkeeper_probability
            if converged:
                break
        risk_breakdown.update({
            key: value for key, value in breakdown.items()
            if key not in risk_breakdown
        })
        risk_breakdown["autosub_probability_mode"] = "player_nonappearance_risk_iterative"
        risk_breakdown["autosub_iterations"] = iterations
        return result, risk_breakdown
    if bench_probabilities is None:
        bench_probabilities = DEFAULT_BENCH_PROBABILITIES
    if bench_probabilities is not None and sorted(bench_probabilities, reverse=True) != list(bench_probabilities):
        raise ValueError("Outfield bench probabilities must be non-increasing by bench order")
    probability_values = (*bench_probabilities, bench_gk_probability, vice_probability)
    if any(not 0 <= value <= 1 for value in probability_values):
        raise ValueError("Substitution and fallback probabilities must be between zero and one")

    model = cp_model.CpModel()
    indices = list(candidates.index)
    squad = {i: model.new_bool_var(f"squad_{i}") for i in indices}
    starter = {i: model.new_bool_var(f"starter_{i}") for i in indices}
    captain = {i: model.new_bool_var(f"captain_{i}") for i in indices}
    vice = {i: model.new_bool_var(f"vice_{i}") for i in indices}
    bench_gk = {i: model.new_bool_var(f"bench_gk_{i}") for i in indices}
    bench = {(i, slot): model.new_bool_var(f"bench_{slot}_{i}") for i in indices for slot in range(3)}

    for i in indices:
        position = int(candidates.at[i, "element_type"])
        model.add(squad[i] == starter[i] + bench_gk[i] + sum(bench[i, slot] for slot in range(3)))
        model.add(captain[i] <= starter[i])
        model.add(vice[i] <= starter[i])
        model.add(captain[i] + vice[i] <= 1)
        if position == 1:
            for slot in range(3):
                model.add(bench[i, slot] == 0)
        else:
            model.add(bench_gk[i] == 0)

    model.add(sum(squad.values()) == 15)
    model.add(sum(starter.values()) == 11)
    model.add(sum(bench_gk.values()) == 1)
    for slot in range(3):
        model.add(sum(bench[i, slot] for i in indices) == 1)
    model.add(sum(captain.values()) == 1)
    model.add(sum(vice.values()) == 1)
    model.add(sum(int(candidates.at[i, "price"]) * squad[i] for i in indices) <= budget)

    for position, count in SQUAD_POSITION_COUNTS.items():
        position_indices = [i for i in indices if int(candidates.at[i, "element_type"]) == position]
        model.add(sum(squad[i] for i in position_indices) == count)
    gks = [i for i in indices if int(candidates.at[i, "element_type"]) == 1]
    defenders = [i for i in indices if int(candidates.at[i, "element_type"]) == 2]
    midfielders = [i for i in indices if int(candidates.at[i, "element_type"]) == 3]
    forwards = [i for i in indices if int(candidates.at[i, "element_type"]) == 4]
    model.add(sum(starter[i] for i in gks) == 1)
    model.add(sum(starter[i] for i in defenders) >= 3)
    model.add(sum(starter[i] for i in midfielders) >= 2)
    model.add(sum(starter[i] for i in forwards) >= 1)
    for club in candidates["club"].unique():
        members = [i for i in indices if candidates.at[i, "club"] == club]
        model.add(sum(squad[i] for i in members) <= 3)

    scale = 10000
    point_units = {i: int(round(float(candidates.at[i, "expected_points"]) * scale)) for i in indices}
    objective = []
    for i in indices:
        objective.extend([point_units[i] * starter[i], point_units[i] * captain[i]])
        objective.append(int(round(point_units[i] * vice_probability)) * vice[i])
        objective.append(int(round(point_units[i] * bench_gk_probability)) * bench_gk[i])
        for slot, probability in enumerate(bench_probabilities):
            objective.append(int(round(point_units[i] * probability)) * bench[i, slot])
    model.maximize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"No feasible squad found; solver status {solver.status_name(status)}")

    chosen = []
    for i in indices:
        if not solver.value(squad[i]):
            continue
        row = candidates.loc[i].to_dict()
        row["position"] = POSITION_NAMES[int(row["element_type"])]
        if solver.value(starter[i]):
            row["role"] = "starting_xi"
            row["bench_order"] = 0
        elif solver.value(bench_gk[i]):
            row["role"] = "bench_gk"
            row["bench_order"] = 4
        else:
            slot = next(slot for slot in range(3) if solver.value(bench[i, slot]))
            row["role"] = "bench"
            row["bench_order"] = slot + 1
        row["is_captain"] = bool(solver.value(captain[i]))
        row["is_vice_captain"] = bool(solver.value(vice[i]))
        chosen.append(row)
    result = pd.DataFrame(chosen).sort_values(["role", "bench_order", "element"]).reset_index(drop=True)
    starter_ids = set(result.loc[result["role"] == "starting_xi", "element"].astype(int))
    captain_id = int(result.loc[result["is_captain"], "element"].iloc[0])
    vice_id = int(result.loc[result["is_vice_captain"], "element"].iloc[0])
    bench_gk_id = int(result.loc[result["role"] == "bench_gk", "element"].iloc[0])
    bench_ids = result.loc[result["role"] == "bench"].sort_values("bench_order")["element"].astype(int).tolist()
    breakdown = _lineup_objective(
        candidates, starter_ids, captain_id, vice_id, bench_gk_id, bench_ids,
        None if dynamic_autosubs else bench_probabilities,
        bench_gk_probability, vice_probability,
    )
    breakdown.update({
        "solver_status": solver.status_name(status),
        "solver_objective_units": int(round(solver.objective_value)),
        "total_cost": int(result["price"].sum()),
        "formation": "-".join(str(int((result.loc[result["role"] == "starting_xi", "element_type"] == p).sum())) for p in (2, 3, 4)),
    })
    return result, breakdown


def _validate_solution(squad: pd.DataFrame, budget: int) -> None:
    if len(squad) != 15 or squad["element"].nunique() != 15:
        raise AssertionError("Solution must contain 15 distinct players")
    counts = squad.groupby("element_type").size().to_dict()
    if counts != SQUAD_POSITION_COUNTS:
        raise AssertionError(f"Invalid squad position counts: {counts}")
    if int(squad["price"].sum()) > budget:
        raise AssertionError("Solution exceeds budget")
    if squad.groupby("club").size().max() > 3:
        raise AssertionError("Solution exceeds three-player club limit")
    starters = squad[squad["role"] == "starting_xi"]
    starter_counts = starters.groupby("element_type").size().to_dict()
    if len(starters) != 11 or starter_counts.get(1) != 1 or starter_counts.get(2, 0) < 3 or starter_counts.get(3, 0) < 2 or starter_counts.get(4, 0) < 1:
        raise AssertionError(f"Illegal starting formation: {starter_counts}")
    if squad["is_captain"].sum() != 1 or squad["is_vice_captain"].sum() != 1:
        raise AssertionError("Exactly one captain and vice-captain are required")
    if not squad.loc[squad["is_captain"] | squad["is_vice_captain"], "role"].eq("starting_xi").all():
        raise AssertionError("Captain and vice-captain must start")


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimise the current FPL squad and lineup")
    parser.add_argument("--predictions", default="data/gw1_2026-27_predictions.csv")
    parser.add_argument("--points-column")
    parser.add_argument("--budget", type=float, default=100.0, help="Budget in millions")
    parser.add_argument(
        "--bench-probabilities", nargs=3, type=float,
        help="Override risk-driven autosub probabilities with three fixed values",
    )
    parser.add_argument("--bench-gk-probability", type=float, default=0.05)
    parser.add_argument("--vice-probability", type=float, default=0.05)
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--output", default="data/optimal_squad.csv")
    parser.add_argument("--report", default="data/optimal_squad.json")
    args = parser.parse_args()

    input_path = Path(args.predictions)
    raw = pd.read_csv(input_path, low_memory=False)
    point_column = _choose_column(raw, args.points_column)
    candidates = _prepare_candidates(raw, point_column)
    budget = int(round(args.budget * 10))
    probabilities = tuple(args.bench_probabilities) if args.bench_probabilities else None
    squad, breakdown = optimise(
        candidates, budget, probabilities, args.bench_gk_probability,
        args.vice_probability, args.time_limit,
    )
    _validate_solution(squad, budget)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    squad.to_csv(output_path, index=False)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "prediction_input": str(input_path),
        "prediction_input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "point_column": point_column,
        "candidate_count": int(len(candidates)),
        "budget": budget,
        "budget_millions": budget / 10,
        "assumptions": {
            "autosub_probability_mode": breakdown["autosub_probability_mode"],
            "outfield_bench_use_probabilities_by_order": breakdown[
                "outfield_bench_use_probabilities_by_order"
            ],
            "bench_goalkeeper_use_probability": breakdown[
                "bench_goalkeeper_use_probability"
            ],
            "vice_captain_fallback_probability": args.vice_probability,
            "note": "Risk-driven autosub probabilities use selected starters' nonappearance probabilities; expected points already include player appearance risk.",
        },
        "result": breakdown,
        "squad": squad[[
            "element", "player_name", "position", "club", "price", "expected_points",
            "appearance_probability",
            "role", "bench_order", "is_captain", "is_vice_captain",
        ]].to_dict(orient="records"),
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(breakdown, indent=2))
    print(squad[["player_name", "position", "price", "expected_points", "role", "bench_order", "is_captain", "is_vice_captain"]].to_string(index=False))
    print(f"Wrote {output_path} and {report_path}")


if __name__ == "__main__":
    main()
