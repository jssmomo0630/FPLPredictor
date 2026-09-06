#!/usr/bin/env python3
"""Compare the exact squad optimiser with a deterministic greedy upgrade heuristic."""

import argparse
import json
from pathlib import Path

import pandas as pd

from optimize_squad import (
    POSITION_NAMES,
    SQUAD_POSITION_COUNTS,
    _choose_column,
    _lineup_objective,
    _prepare_candidates,
    optimise,
)


def greedy_squad(candidates: pd.DataFrame, budget: int) -> set[int]:
    """Build the cheapest legal squad, then greedily take the largest point upgrade."""
    selected: set[int] = set()
    club_counts: dict[str, int] = {}
    for position, count in SQUAD_POSITION_COUNTS.items():
        pool = candidates[candidates["element_type"] == position].sort_values(
            ["price", "expected_points", "element"], ascending=[True, False, True]
        )
        for i, row in pool.iterrows():
            club = row["club"]
            if club_counts.get(club, 0) >= 3:
                continue
            selected.add(i)
            club_counts[club] = club_counts.get(club, 0) + 1
            if sum(candidates.loc[list(selected), "element_type"].eq(position)) == count:
                break
    if len(selected) != 15:
        raise RuntimeError("Greedy baseline could not construct a legal initial squad")
    cost = int(candidates.loc[list(selected), "price"].sum())
    if cost > budget:
        raise RuntimeError("Cheapest greedy squad exceeds the budget")

    while True:
        best = None
        for current in selected:
            current_row = candidates.loc[current]
            alternatives = candidates[
                (candidates["element_type"] == current_row["element_type"])
                & ~candidates.index.isin(selected)
                & (candidates["expected_points"] > current_row["expected_points"])
            ]
            for replacement, replacement_row in alternatives.iterrows():
                extra_cost = int(replacement_row["price"] - current_row["price"])
                if cost + extra_cost > budget:
                    continue
                new_club = replacement_row["club"]
                old_club = current_row["club"]
                adjusted_club_count = club_counts.get(new_club, 0) - int(new_club == old_club)
                if adjusted_club_count >= 3:
                    continue
                gain = float(replacement_row["expected_points"] - current_row["expected_points"])
                candidate_move = (gain, -extra_cost, -int(replacement_row["element"]), current, replacement)
                if best is None or candidate_move > best:
                    best = candidate_move
        if best is None:
            break
        _, _, _, current, replacement = best
        old_club = candidates.at[current, "club"]
        new_club = candidates.at[replacement, "club"]
        cost += int(candidates.at[replacement, "price"] - candidates.at[current, "price"])
        club_counts[old_club] -= 1
        club_counts[new_club] = club_counts.get(new_club, 0) + 1
        selected.remove(current)
        selected.add(replacement)
    return selected


def assign_greedy_roles(
    candidates: pd.DataFrame,
    selected: set[int],
    bench_probabilities: tuple[float, float, float],
    bench_gk_probability: float,
    vice_probability: float,
) -> tuple[dict, dict]:
    squad = candidates.loc[list(selected)]
    best = None
    for defenders in range(3, 6):
        for midfielders in range(2, 6):
            forwards = 10 - defenders - midfielders
            if not 1 <= forwards <= 3:
                continue
            counts = {1: 1, 2: defenders, 3: midfielders, 4: forwards}
            starters = set()
            for position, count in counts.items():
                starters.update(squad[squad["element_type"] == position].nlargest(count, "expected_points").index)
            ordered_starters = squad.loc[list(starters)].sort_values(
                ["expected_points", "element"], ascending=[False, True]
            )
            captain_idx, vice_idx = ordered_starters.index[:2]
            bench_gk_idx = next(i for i in selected if candidates.at[i, "element_type"] == 1 and i not in starters)
            outfield_bench = squad.loc[
                [i for i in selected if i not in starters and candidates.at[i, "element_type"] != 1]
            ].sort_values(["expected_points", "element"], ascending=[False, True]).index.tolist()
            objective = _lineup_objective(
                candidates,
                set(candidates.loc[list(starters), "element"].astype(int)),
                int(candidates.at[captain_idx, "element"]), int(candidates.at[vice_idx, "element"]),
                int(candidates.at[bench_gk_idx, "element"]),
                candidates.loc[outfield_bench, "element"].astype(int).tolist(),
                bench_probabilities, bench_gk_probability, vice_probability,
            )
            if best is None or objective["objective"] > best[0]["objective"]:
                best = (objective, {
                    "starter_indices": starters, "captain_index": captain_idx,
                    "vice_index": vice_idx, "bench_gk_index": bench_gk_idx,
                    "bench_indices": outfield_bench,
                    "formation": f"{defenders}-{midfielders}-{forwards}",
                })
    if best is None:
        raise RuntimeError("Greedy squad cannot form a legal lineup")
    best[0]["total_cost"] = int(squad["price"].sum())
    best[0]["formation"] = best[1]["formation"]
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark exact versus greedy squad selection")
    parser.add_argument("--predictions", default="data/gw1_2026-27_predictions.csv")
    parser.add_argument("--points-column")
    parser.add_argument("--budget", type=float, default=100.0)
    parser.add_argument("--output", default="data/squad_optimizer_evaluation.json")
    args = parser.parse_args()
    raw = pd.read_csv(args.predictions, low_memory=False)
    point_column = _choose_column(raw, args.points_column)
    candidates = _prepare_candidates(raw, point_column)
    budget = int(round(args.budget * 10))
    bench_probabilities = (0.15, 0.05, 0.02)
    bench_gk_probability = 0.05
    vice_probability = 0.05
    _, exact = optimise(
        candidates, budget, bench_probabilities, bench_gk_probability, vice_probability,
    )
    selected = greedy_squad(candidates, budget)
    greedy, _ = assign_greedy_roles(
        candidates, selected, bench_probabilities, bench_gk_probability, vice_probability,
    )
    improvement = exact["objective"] - greedy["objective"]
    report = {
        "prediction_input": args.predictions,
        "point_column": point_column,
        "comparison_note": "The baseline starts from the cheapest legal squad and repeatedly takes the largest affordable same-position expected-points upgrade, then chooses its best legal XI.",
        "exact": exact,
        "greedy": greedy,
        "objective_improvement": improvement,
        "objective_improvement_percent": 100 * improvement / greedy["objective"],
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
