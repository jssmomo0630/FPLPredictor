#!/usr/bin/env python3
"""Plan FPL transfers over several gameweeks with rolled free transfers and hits."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from ortools.sat.python import cp_model

from optimize_squad import (
    POSITION_NAMES,
    SQUAD_POSITION_COUNTS,
    _prepare_candidates,
    optimise,
)


CHIPS = ("wildcard", "free_hit", "triple_captain", "bench_boost")
CHIP_PERIODS = (
    {"number": 1, "start_gameweek": 1, "end_gameweek": 19},
    {"number": 2, "start_gameweek": 20, "end_gameweek": 38},
)
DEFAULT_CHIP_RESERVE_VALUES = {
    "wildcard": 15.0,
    "free_hit": 12.0,
    "triple_captain": 12.0,
    "bench_boost": 12.0,
}
BENCH_WEIGHTS = (0.15, 0.05, 0.02)
CHIP_NAME_MAP = {
    "wildcard": "wildcard",
    "freehit": "free_hit",
    "3xc": "triple_captain",
    "bboost": "bench_boost",
}


def load_opponent_pairs(
    path: Path,
    season: str,
    gameweeks: list[int],
) -> dict[int, set[tuple[int, int]]]:
    """Return unordered team pairs that meet in each requested gameweek."""
    frame = pd.read_csv(path, low_memory=False)
    required = {"season", "gameweek", "team", "opponent_team"}
    if missing := required.difference(frame.columns):
        raise ValueError(f"Fixture input is missing: {sorted(missing)}")
    frame = frame[
        (frame["season"].astype(str) == season)
        & (pd.to_numeric(frame["gameweek"], errors="coerce").isin(gameweeks))
    ].copy()
    pairs = {gameweek: set() for gameweek in gameweeks}
    for row in frame.itertuples(index=False):
        gameweek = int(row.gameweek)
        team = int(row.team)
        opponent = int(row.opponent_team)
        if team != opponent:
            pairs[gameweek].add(tuple(sorted((team, opponent))))
    return pairs


def load_squad(path: Path, forecasts: pd.DataFrame, bank_override: int | None) -> tuple[set[int], dict[int, int], int, str]:
    """Load our optimiser CSV/JSON or a public entry-picks JSON snapshot."""
    bank = bank_override
    selling_prices: dict[int, int] = {}
    source = "unknown"
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        if "element" not in frame:
            raise ValueError("Squad CSV requires an element column")
        elements = set(pd.to_numeric(frame["element"], errors="raise").astype(int))
        if "selling_price" in frame:
            selling_prices = dict(zip(frame["element"].astype(int), frame["selling_price"].astype(int)))
            source = "csv_true_selling_price"
        else:
            source = "csv_current_price_fallback"
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "picks" in payload:
            picks = payload["picks"]
            elements = {int(row["element"]) for row in picks}
            raw_picks = payload.get("raw", {}).get("picks", [])
            selling_prices = {
                int(row["element"]): int(row["selling_price"])
                for row in raw_picks if row.get("selling_price") is not None
            }
            if bank is None:
                bank = int(payload.get("entry_history", {}).get("bank", 0))
            source = "entry_snapshot_true_selling_price" if selling_prices else "entry_snapshot_current_price_fallback"
        elif "squad" in payload:
            squad_payload = payload["squad"]
            if isinstance(squad_payload, dict):
                rows = squad_payload.get("players", [])
                financial = squad_payload.get("financial", {})
                if bank is None and financial.get("bank_units") is not None:
                    bank = int(financial["bank_units"])
                source_prefix = "public_status"
            else:
                rows = squad_payload
                source_prefix = "optimizer_json"
            elements = {int(row["element"]) for row in rows}
            selling_prices = {
                int(row["element"]): int(row["selling_price"])
                for row in rows if row.get("selling_price") is not None
            }
            source = (
                f"{source_prefix}_current_price_fallback"
                if not selling_prices else f"{source_prefix}_true_selling_price"
            )
        else:
            raise ValueError("Unsupported squad JSON: expected picks or squad")
    if len(elements) != 15:
        raise ValueError(f"Current squad must contain 15 distinct elements, got {len(elements)}")
    prices = forecasts.drop_duplicates("element").set_index("element")["price"].astype(int).to_dict()
    if missing := elements.difference(prices):
        raise ValueError(f"Current squad elements absent from forecasts: {sorted(missing)}")
    for element in elements:
        selling_prices.setdefault(element, prices[element])
    return elements, selling_prices, int(bank or 0), source


def chip_period_for_gameweek(gameweek: int) -> dict[str, int]:
    for period in CHIP_PERIODS:
        if period["start_gameweek"] <= gameweek <= period["end_gameweek"]:
            return dict(period)
    raise ValueError(f"Gameweek {gameweek} is outside the supported FPL season")


def snapshot_used_chips(path: Path, target_gameweek: int | None = None) -> set[str]:
    """Return chips used in the target half-season.

    Public entry history contains chip uses from the full season. A chip used in
    the first half must not make its refreshed second-half copy unavailable.
    Rows without an event remain conservatively unavailable because their period
    cannot be identified.
    """
    if path.suffix.lower() != ".json":
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    used = payload.get("metadata", {}).get("chips_used", [])
    if isinstance(payload.get("squad"), dict):
        used = payload["squad"].get("used_chips", used)
    period = (
        chip_period_for_gameweek(target_gameweek)
        if target_gameweek is not None else None
    )
    names = set()
    for row in used:
        if isinstance(row, dict):
            event = row.get("event")
            if period is not None and event is not None:
                event = int(event)
                if not period["start_gameweek"] <= event <= period["end_gameweek"]:
                    continue
            names.add(row.get("name"))
        else:
            names.add(row)
    return {CHIP_NAME_MAP[name] for name in names if name in CHIP_NAME_MAP}


def prepare_forecasts(frame: pd.DataFrame, current: set[int], max_candidates_per_position: int) -> pd.DataFrame:
    required = {"gameweek", "element", "player_name", "element_type", "team_id", "price", "expected_points"}
    if missing := required.difference(frame.columns):
        raise ValueError(f"Transfer forecast is missing: {sorted(missing)}")
    frame = frame.copy()
    for column in ["gameweek", "element", "element_type", "team_id", "price"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
    frame["expected_points"] = pd.to_numeric(frame["expected_points"], errors="coerce").fillna(0).clip(lower=0)
    gameweeks = sorted(frame["gameweek"].unique())
    if gameweeks != list(range(min(gameweeks), max(gameweeks) + 1)):
        raise ValueError("Forecast gameweeks must be consecutive")
    coverage = frame.groupby("element")["gameweek"].nunique()
    complete = set(coverage[coverage == len(gameweeks)].index)
    if missing := current.difference(complete):
        raise ValueError(f"Current players lack full-horizon forecasts: {sorted(missing)}")
    horizon_score = frame.groupby(["element", "element_type"])["expected_points"].sum().reset_index()
    keep = set(current)
    for _, group in horizon_score.groupby("element_type"):
        keep.update(group.nlargest(max_candidates_per_position, "expected_points")["element"].astype(int))
    return frame[frame["element"].isin(keep & complete)].sort_values(["gameweek", "element"]).reset_index(drop=True)


def _planned_week_value(rows: pd.DataFrame) -> float:
    starters = rows[rows["role"].eq("starting_xi")]
    value = float(starters["expected_points"].sum())
    value += float(starters.loc[starters["is_captain"], "expected_points"].iloc[0])
    value += 0.05 * float(starters.loc[starters["is_vice_captain"], "expected_points"].iloc[0])
    bench_gk = rows[rows["role"].eq("bench_gk")]
    value += 0.05 * float(bench_gk["expected_points"].iloc[0])
    bench = rows[rows["role"].eq("bench")].sort_values("bench_order")
    value += sum(
        probability * float(points)
        for probability, points in zip(BENCH_WEIGHTS, bench["expected_points"])
    )
    return value


def _chip_week_values(rows: pd.DataFrame) -> dict[str, float]:
    captain_points = float(
        rows.loc[rows["is_captain"], "expected_points"].iloc[0]
    )
    bench_gk = rows.loc[rows["role"].eq("bench_gk"), "expected_points"]
    outfield_bench = rows[rows["role"].eq("bench")].sort_values("bench_order")[
        "expected_points"
    ]
    normal_bench_value = 0.05 * float(bench_gk.iloc[0]) + sum(
        probability * float(points)
        for probability, points in zip(BENCH_WEIGHTS, outfield_bench)
    )
    full_bench_value = float(bench_gk.sum() + outfield_bench.sum())
    return {
        "triple_captain": captain_points,
        "bench_boost": full_bench_value - normal_bench_value,
    }


def _optimise_points_frame(
    frame: pd.DataFrame,
    budget: int,
    time_limit: float,
) -> tuple[pd.DataFrame, dict]:
    candidates = _prepare_candidates(frame, "expected_points")
    return optimise(
        candidates,
        budget=budget,
        bench_probabilities=BENCH_WEIGHTS,
        bench_gk_probability=0.05,
        vice_probability=0.05,
        time_limit=time_limit,
    )


def advise_chips(
    forecasts: pd.DataFrame,
    plan_rows: pd.DataFrame,
    plan_report: dict,
    available_chips: set[str] | None = None,
    reserve_values: dict[str, float] | None = None,
    discount: float = 0.90,
    time_limit: float = 5.0,
    period_start_gameweek: int | None = None,
    period_end_gameweek: int | None = None,
) -> dict:
    """Estimate chip gains against the no-chip transfer plan."""
    available = set(CHIPS if available_chips is None else available_chips)
    unknown = available.difference(CHIPS)
    if unknown:
        raise ValueError(f"Unknown chips: {sorted(unknown)}")
    reserves = {**DEFAULT_CHIP_RESERVE_VALUES, **(reserve_values or {})}
    all_gameweeks = [
        int(value) for value in sorted(plan_rows["gameweek"].astype(int).unique())
    ]
    gameweeks = [
        gameweek for gameweek in all_gameweeks
        if (period_start_gameweek is None or gameweek >= period_start_gameweek)
        and (period_end_gameweek is None or gameweek <= period_end_gameweek)
    ]
    if not gameweeks:
        raise ValueError("No forecast gameweeks fall within the active chip period")
    week_reports = {int(row["gameweek"]): row for row in plan_report["weeks"]}
    baseline_values = {
        gameweek: _planned_week_value(
            plan_rows[plan_rows["gameweek"].eq(gameweek)]
        )
        for gameweek in gameweeks
    }
    options: list[dict] = []

    for gameweek in gameweeks:
        week_rows = plan_rows[plan_rows["gameweek"].eq(gameweek)]
        simple_values = _chip_week_values(week_rows)
        for chip in ("triple_captain", "bench_boost"):
            if chip in available:
                gross = simple_values[chip]
                options.append({
                    "chip": chip,
                    "gameweek": gameweek,
                    "gross_gain": gross,
                    "reserve_value": reserves[chip],
                    "net_gain": gross - reserves[chip],
                })

        if "free_hit" in available:
            pool = forecasts[forecasts["gameweek"].eq(gameweek)].copy()
            budget = int(week_rows["price"].sum()) + int(
                week_reports[gameweek]["bank_after"]
            )
            _, ideal = _optimise_points_frame(pool, budget, time_limit)
            gross = ideal["objective"] - baseline_values[gameweek]
            options.append({
                "chip": "free_hit",
                "gameweek": gameweek,
                "gross_gain": gross,
                "reserve_value": reserves["free_hit"],
                "net_gain": gross - reserves["free_hit"],
            })

    if "wildcard" in available:
        for start_index, gameweek in enumerate(gameweeks):
            remaining = gameweeks[start_index:]
            aggregate = forecasts[forecasts["gameweek"].isin(remaining)].copy()
            aggregate["_weight"] = aggregate["gameweek"].map({
                value: discount ** offset for offset, value in enumerate(remaining)
            })
            aggregate["weighted_points"] = (
                aggregate["expected_points"] * aggregate["_weight"]
            )
            identity = [
                "element", "player_name", "element_type", "team_id", "price"
            ]
            aggregate = aggregate.groupby(identity, as_index=False).agg(
                expected_points=("weighted_points", "sum")
            )
            week_rows = plan_rows[plan_rows["gameweek"].eq(gameweek)]
            budget = int(week_rows["price"].sum()) + int(
                week_reports[gameweek]["bank_after"]
            )
            wildcard_squad, _ = _optimise_points_frame(
                aggregate, budget, time_limit
            )
            wildcard_ids = set(wildcard_squad["element"].astype(int))
            wildcard_value = 0.0
            baseline_value = 0.0
            for offset, future_gameweek in enumerate(remaining):
                selected = forecasts[
                    forecasts["gameweek"].eq(future_gameweek)
                    & forecasts["element"].isin(wildcard_ids)
                ].copy()
                _, selected_value = _optimise_points_frame(
                    selected, int(selected["price"].sum()), time_limit
                )
                weight = discount ** offset
                wildcard_value += weight * selected_value["objective"]
                baseline_value += weight * baseline_values[future_gameweek]
                baseline_value -= weight * float(
                    week_reports[future_gameweek]["hit_cost"]
                )
            gross = wildcard_value - baseline_value
            options.append({
                "chip": "wildcard",
                "gameweek": gameweek,
                "gross_gain": gross,
                "reserve_value": reserves["wildcard"],
                "net_gain": gross - reserves["wildcard"],
            })

    options.sort(key=lambda row: row["net_gain"], reverse=True)
    for row in options:
        for key in ("gross_gain", "reserve_value", "net_gain"):
            row[key] = round(float(row[key]), 3)
    best_by_chip = {
        chip: next((row for row in options if row["chip"] == chip), None)
        for chip in CHIPS
    }
    recommended = next((row for row in options if row["net_gain"] > 0), None)
    return {
        "available_chips": sorted(available),
        "chip_period": {
            "start_gameweek": period_start_gameweek,
            "end_gameweek": period_end_gameweek,
            "forecast_reaches_expiry": (
                period_end_gameweek is not None
                and max(gameweeks) >= period_end_gameweek
            ),
        },
        "reserve_values": reserves,
        "recommended": recommended,
        "recommendation": (
            f"Use {recommended['chip']} in GW{recommended['gameweek']}"
            if recommended else "Save all chips in the forecast horizon"
        ),
        "best_by_chip": best_by_chip,
        "options": options,
        "method_note": (
            "Triple Captain and Bench Boost use the planned lineup. Free Hit compares "
            "with the best one-week squad. Wildcard compares with the best persistent "
            "squad over the remaining horizon. Reserve values represent future optionality."
        ),
    }


def plan(
    forecasts: pd.DataFrame,
    current: set[int],
    selling_prices: dict[int, int],
    bank: int,
    free_transfers: int,
    discount: float = 0.90,
    max_free_transfers: int = 5,
    hit_cost: float = 4.0,
    transfer_friction: float = 0.25,
    opponent_conflict_penalty: float = 0.15,
    opponent_pairs: dict[int, set[tuple[int, int]]] | None = None,
    terminal_free_transfer_value: float = 0.50,
    time_limit: float = 60.0,
) -> tuple[pd.DataFrame, dict]:
    if not 1 <= free_transfers <= max_free_transfers:
        raise ValueError(f"Free transfers must be between 1 and {max_free_transfers}")
    gameweeks = [int(value) for value in sorted(forecasts["gameweek"].unique())]
    players = forecasts.drop_duplicates("element").set_index("element")
    elements = sorted(players.index.astype(int))
    points = forecasts.set_index(["gameweek", "element"])["expected_points"].to_dict()
    prices = players["price"].astype(int).to_dict()
    positions = players["element_type"].astype(int).to_dict()
    clubs = players["team_id"].astype(int).to_dict()
    sale_values = {element: selling_prices.get(element, prices[element]) for element in elements}

    model = cp_model.CpModel()
    own = {(e, t): model.new_bool_var(f"own_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    transfer_in = {(e, t): model.new_bool_var(f"in_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    transfer_out = {(e, t): model.new_bool_var(f"out_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    start = {(e, t): model.new_bool_var(f"start_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    captain = {(e, t): model.new_bool_var(f"captain_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    vice = {(e, t): model.new_bool_var(f"vice_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    bench_gk = {(e, t): model.new_bool_var(f"bench_gk_{e}_{t}") for e in elements for t in range(len(gameweeks))}
    bench = {(e, t, slot): model.new_bool_var(f"bench_{slot}_{e}_{t}") for e in elements for t in range(len(gameweeks)) for slot in range(3)}
    transfers = [model.new_int_var(0, 15, f"transfers_{t}") for t in range(len(gameweeks))]
    paid = [model.new_int_var(0, 15, f"paid_{t}") for t in range(len(gameweeks))]
    free_before = [model.new_int_var(1, max_free_transfers, f"free_before_{t}") for t in range(len(gameweeks))]
    free_after = [model.new_int_var(1, max_free_transfers, f"free_after_{t}") for t in range(len(gameweeks))]
    bank_after = [model.new_int_var(0, 3000, f"bank_after_{t}") for t in range(len(gameweeks))]
    model.add(free_before[0] == free_transfers)

    for t, gameweek in enumerate(gameweeks):
        for element in elements:
            previous = int(element in current) if t == 0 else own[element, t - 1]
            model.add(own[element, t] == previous + transfer_in[element, t] - transfer_out[element, t])
            model.add(transfer_in[element, t] + transfer_out[element, t] <= 1)
            if t == 0:
                model.add(transfer_in[element, t] <= 1 - previous)
                model.add(transfer_out[element, t] <= previous)
            else:
                model.add(transfer_in[element, t] + previous <= 1)
                model.add(transfer_out[element, t] <= previous)
            model.add(own[element, t] == start[element, t] + bench_gk[element, t] + sum(bench[element, t, slot] for slot in range(3)))
            model.add(captain[element, t] <= start[element, t])
            model.add(vice[element, t] <= start[element, t])
            model.add(captain[element, t] + vice[element, t] <= 1)
            if positions[element] == 1:
                for slot in range(3):
                    model.add(bench[element, t, slot] == 0)
            else:
                model.add(bench_gk[element, t] == 0)

        model.add(transfers[t] == sum(transfer_in[element, t] for element in elements))
        model.add(transfers[t] == sum(transfer_out[element, t] for element in elements))
        model.add(paid[t] >= transfers[t] - free_before[t])
        remaining = model.new_int_var(0, max_free_transfers, f"free_remaining_{t}")
        model.add_max_equality(remaining, [free_before[t] - transfers[t], 0])
        model.add_min_equality(free_after[t], [remaining + 1, max_free_transfers])
        if t + 1 < len(gameweeks):
            model.add(free_before[t + 1] == free_after[t])

        prior_bank = bank if t == 0 else bank_after[t - 1]
        model.add(
            bank_after[t] == prior_bank
            + sum(sale_values[element] * transfer_out[element, t] for element in elements)
            - sum(prices[element] * transfer_in[element, t] for element in elements)
        )
        model.add(sum(own[element, t] for element in elements) == 15)
        model.add(sum(start[element, t] for element in elements) == 11)
        model.add(sum(bench_gk[element, t] for element in elements) == 1)
        model.add(sum(captain[element, t] for element in elements) == 1)
        model.add(sum(vice[element, t] for element in elements) == 1)
        for slot in range(3):
            model.add(sum(bench[element, t, slot] for element in elements) == 1)
        for position, count in SQUAD_POSITION_COUNTS.items():
            members = [e for e in elements if positions[e] == position]
            model.add(sum(own[e, t] for e in members) == count)
        model.add(sum(start[e, t] for e in elements if positions[e] == 1) == 1)
        model.add(sum(start[e, t] for e in elements if positions[e] == 2) >= 3)
        model.add(sum(start[e, t] for e in elements if positions[e] == 3) >= 2)
        model.add(sum(start[e, t] for e in elements if positions[e] == 4) >= 1)
        for club in set(clubs.values()):
            model.add(sum(own[e, t] for e in elements if clubs[e] == club) <= 3)

    scale = 10000
    bench_probabilities = (0.15, 0.05, 0.02)
    opponent_pairs = opponent_pairs or {}
    conflict_vars: dict[tuple[int, int, int], cp_model.IntVar] = {}
    objective_terms = []
    for t, gameweek in enumerate(gameweeks):
        week_weight = discount ** t
        for element in elements:
            units = int(round(float(points[gameweek, element]) * scale * week_weight))
            objective_terms.extend([units * start[element, t], units * captain[element, t]])
            objective_terms.append(int(round(units * 0.05)) * vice[element, t])
            objective_terms.append(int(round(units * 0.05)) * bench_gk[element, t])
            for slot, probability in enumerate(bench_probabilities):
                objective_terms.append(int(round(units * probability)) * bench[element, t, slot])
        objective_terms.append(-int(round(hit_cost * scale * week_weight)) * paid[t])
        objective_terms.append(-int(round(transfer_friction * scale * week_weight)) * transfers[t])
        if opponent_conflict_penalty > 0:
            defensive_players = [element for element in elements if positions[element] in (1, 2)]
            attacking_players = [element for element in elements if positions[element] in (3, 4)]
            for defensive in defensive_players:
                for attacker in attacking_players:
                    fixture = tuple(sorted((clubs[defensive], clubs[attacker])))
                    if fixture not in opponent_pairs.get(gameweek, set()):
                        continue
                    conflict = model.new_bool_var(f"opponent_conflict_{gameweek}_{defensive}_{attacker}")
                    model.add(conflict <= start[defensive, t])
                    model.add(conflict <= start[attacker, t])
                    model.add(conflict >= start[defensive, t] + start[attacker, t] - 1)
                    conflict_vars[t, defensive, attacker] = conflict
                    penalty_units = int(round(opponent_conflict_penalty * scale * week_weight))
                    objective_terms.append(-penalty_units * conflict)
    objective_terms.append(int(round(terminal_free_transfer_value * scale * (discount ** len(gameweeks)))) * free_after[-1])
    model.maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"No transfer plan found: {solver.status_name(status)}")

    rows = []
    weeks = []
    for t, gameweek in enumerate(gameweeks):
        ins = [e for e in elements if solver.value(transfer_in[e, t])]
        outs = [e for e in elements if solver.value(transfer_out[e, t])]
        conflicts = [
            {
                "defensive_element": defensive,
                "defensive_player": players.at[defensive, "player_name"],
                "defensive_team_id": clubs[defensive],
                "attacking_element": attacker,
                "attacking_player": players.at[attacker, "player_name"],
                "attacking_team_id": clubs[attacker],
                "penalty_points": opponent_conflict_penalty,
            }
            for (week_index, defensive, attacker), variable in conflict_vars.items()
            if week_index == t and solver.value(variable)
        ]
        for element in elements:
            if not solver.value(own[element, t]):
                continue
            if solver.value(start[element, t]):
                role, bench_order = "starting_xi", 0
            elif solver.value(bench_gk[element, t]):
                role, bench_order = "bench_gk", 4
            else:
                slot = next(slot for slot in range(3) if solver.value(bench[element, t, slot]))
                role, bench_order = "bench", slot + 1
            rows.append({
                "gameweek": gameweek, "element": element,
                "player_name": players.at[element, "player_name"],
                "position": POSITION_NAMES[positions[element]], "team_id": clubs[element],
                "price": prices[element], "expected_points": points[gameweek, element],
                "role": role, "bench_order": bench_order,
                "is_captain": bool(solver.value(captain[element, t])),
                "is_vice_captain": bool(solver.value(vice[element, t])),
            })
        weeks.append({
            "gameweek": gameweek,
            "free_transfers_before": solver.value(free_before[t]),
            "transfers_used": solver.value(transfers[t]),
            "paid_transfers": solver.value(paid[t]),
            "hit_cost": hit_cost * solver.value(paid[t]),
            "free_transfers_after_roll": solver.value(free_after[t]),
            "bank_after": solver.value(bank_after[t]),
            "transfers_in": [{"element": e, "player_name": players.at[e, "player_name"], "price": prices[e]} for e in ins],
            "transfers_out": [{"element": e, "player_name": players.at[e, "player_name"], "selling_price": sale_values[e]} for e in outs],
            "opponent_conflicts": conflicts,
            "opponent_conflict_penalty_points": round(
                opponent_conflict_penalty * len(conflicts), 3
            ),
        })
    report = {
        "solver_status": solver.status_name(status),
        "objective_units": int(round(solver.objective_value)),
        "gameweeks": gameweeks,
        "discount": discount,
        "hit_cost": hit_cost,
        "transfer_friction": transfer_friction,
        "opponent_conflict_penalty": opponent_conflict_penalty,
        "terminal_free_transfer_value": terminal_free_transfer_value,
        "initial_free_transfers": free_transfers,
        "initial_bank": bank,
        "max_free_transfers": max_free_transfers,
        "weeks": weeks,
    }
    return pd.DataFrame(rows), report


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan free-transfer-aware multi-GW FPL moves")
    parser.add_argument("--forecasts", default="data/transfer_forecasts.csv")
    parser.add_argument("--current-squad", required=True)
    parser.add_argument("--free-transfers", type=int, default=1)
    parser.add_argument("--bank", type=float, help="Bank in millions; otherwise read snapshot or use zero")
    parser.add_argument("--start-gameweek", type=int)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--discount", type=float, default=0.90)
    parser.add_argument("--transfer-friction", type=float, default=0.25)
    parser.add_argument(
        "--opponent-conflict-penalty", type=float, default=0.15,
        help=(
            "Soft expected-point penalty for each starting MID/FWD facing a starting "
            "GK/DEF; fixture difficulty remains in the player forecast"
        ),
    )
    parser.add_argument("--fixtures", default="data/canonical_fixtures.csv")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--terminal-free-transfer-value", type=float, default=0.50)
    parser.add_argument("--max-candidates-per-position", type=int, default=20)
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument(
        "--unavailable-chips", nargs="*", choices=CHIPS, default=[],
        help="Chips already used or otherwise unavailable",
    )
    parser.add_argument("--wildcard-reserve-value", type=float, default=15.0)
    parser.add_argument("--free-hit-reserve-value", type=float, default=12.0)
    parser.add_argument("--triple-captain-reserve-value", type=float, default=12.0)
    parser.add_argument("--bench-boost-reserve-value", type=float, default=12.0)
    parser.add_argument(
        "--chip-time-limit", type=float, default=3.0,
        help="Solver limit for each chip counterfactual",
    )
    parser.add_argument("--output", default="data/transfer_plan.csv")
    parser.add_argument("--report", default="data/transfer_plan.json")
    args = parser.parse_args()
    raw_forecasts = pd.read_csv(args.forecasts, low_memory=False)
    if args.start_gameweek is not None:
        raw_forecasts = raw_forecasts[raw_forecasts["gameweek"] >= args.start_gameweek]
    selected_gws = [int(value) for value in sorted(raw_forecasts["gameweek"].unique())[:args.horizon]]
    raw_forecasts = raw_forecasts[raw_forecasts["gameweek"].isin(selected_gws)]
    bank_override = None if args.bank is None else int(round(args.bank * 10))
    squad_path = Path(args.current_squad)
    current, selling_prices, bank, price_source = load_squad(
        squad_path, raw_forecasts, bank_override,
    )
    forecasts = prepare_forecasts(raw_forecasts, current, args.max_candidates_per_position)
    opponent_pairs = load_opponent_pairs(Path(args.fixtures), args.season, selected_gws)
    result, report = plan(
        forecasts, current, selling_prices, bank, args.free_transfers,
        args.discount, transfer_friction=args.transfer_friction,
        opponent_conflict_penalty=args.opponent_conflict_penalty,
        opponent_pairs=opponent_pairs,
        terminal_free_transfer_value=args.terminal_free_transfer_value,
        time_limit=args.time_limit,
    )
    reserve_values = {
        "wildcard": args.wildcard_reserve_value,
        "free_hit": args.free_hit_reserve_value,
        "triple_captain": args.triple_captain_reserve_value,
        "bench_boost": args.bench_boost_reserve_value,
    }
    chip_period = chip_period_for_gameweek(selected_gws[0])
    unavailable_chips = set(args.unavailable_chips) | snapshot_used_chips(
        squad_path, selected_gws[0]
    )
    report["chip_advice"] = advise_chips(
        forecasts,
        result,
        report,
        available_chips=set(CHIPS).difference(unavailable_chips),
        reserve_values=reserve_values,
        discount=args.discount,
        time_limit=args.chip_time_limit,
        period_start_gameweek=chip_period["start_gameweek"],
        period_end_gameweek=chip_period["end_gameweek"],
    )
    report.update({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "forecast_input": args.forecasts,
        "current_squad_input": args.current_squad,
        "selling_price_source": price_source,
        "selling_price_warning": "Current prices were used where true selling prices were unavailable.",
        "candidate_count": int(forecasts["element"].nunique()),
        "unavailable_chips": sorted(unavailable_chips),
        "forecast_note": (
            "Plans use the supplied point forecast. Price changes are not forecast; "
            "chips are evaluated as recommendations and are never activated automatically."
        ),
    })
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {args.output} and {args.report}")


if __name__ == "__main__":
    main()
