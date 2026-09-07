#!/usr/bin/env python3
"""Build historical training rows and current candidates for an FPL GW1 prior."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from fpl_pipeline_config import CURRENT_SEASON


PLAYER_TOTALS = [
    "minutes", "starts", "goals_scored", "assists", "clean_sheets", "saves",
    "bonus", "expected_goals", "expected_assists", "expected_goal_involvements",
    "defensive_contribution", "total_points",
]


def _players_path(data_root: Path, season: str) -> Path:
    nested = data_root / season / "vaastav" / "players_raw.csv"
    return nested if nested.exists() else data_root / season / "players_raw.csv"


def _merged_path(data_root: Path, season: str) -> Path:
    nested = data_root / season / "vaastav" / "merged_gw.csv"
    if nested.exists():
        return nested
    return data_root / season / "merged_gw.csv"


def _player_lookup(data_root: Path, season: str) -> pd.DataFrame:
    fields = ["id", "code", "web_name", "element_type", "team_code"]
    players = pd.read_csv(_players_path(data_root, season), low_memory=False)
    return players.reindex(columns=fields)


def _fixture_sides(raw: pd.DataFrame) -> pd.DataFrame:
    gameweek = "GW" if "GW" in raw else "round"
    fields = ["fixture", gameweek, "team", "was_home", "kickoff_time"]
    for column in ["team_h_score", "team_a_score"]:
        if column in raw:
            fields.append(column)
    sides = raw[fields].drop_duplicates(["fixture", "team"])
    if sides["was_home"].dtype == "object":
        sides["was_home"] = sides["was_home"].replace(
            {"True": True, "False": False, "true": True, "false": False}
        ).astype(bool)
    home = sides[sides["was_home"]].rename(columns={gameweek: "gameweek", "team": "team"})
    away = sides[~sides["was_home"]].rename(columns={gameweek: "gameweek", "team": "opponent_name"})
    matches = home.merge(
        away[["fixture", "opponent_name"]], on="fixture", how="inner", validate="one_to_one"
    )
    home_rows = matches.assign(was_home=True)
    away_rows = matches.rename(columns={"team": "opponent_name", "opponent_name": "team"}).assign(was_home=False)
    result = pd.concat([home_rows, away_rows], ignore_index=True)
    if {"team_h_score", "team_a_score"}.issubset(result.columns):
        result["goals_for"] = np.where(result["was_home"], result["team_h_score"], result["team_a_score"])
        result["goals_against"] = np.where(result["was_home"], result["team_a_score"], result["team_h_score"])
    return result


def _team_prior(data_root: Path, season: str) -> pd.DataFrame:
    raw = pd.read_csv(_merged_path(data_root, season), low_memory=False)
    if "position" in raw:
        raw = raw[raw["position"].isin(["GK", "GKP", "DEF", "MID", "FWD"])]
    if "expected_goals" not in raw:
        raw["expected_goals"] = 0.0
    sides = _fixture_sides(raw)
    per_fixture = raw.groupby(["fixture", "team"], as_index=False).agg(
        team_xg=("expected_goals", "sum"),
        team_fpl_points=("total_points", "sum"),
    )
    sides = sides.merge(per_fixture, on=["fixture", "team"], how="left", validate="one_to_one")
    return sides.groupby("team", as_index=False).agg(
        prior_team_games=("fixture", "nunique"),
        prior_team_goals_for=("goals_for", "mean"),
        prior_team_goals_against=("goals_against", "mean"),
        prior_team_xg=("team_xg", "mean"),
        prior_team_fpl_points=("team_fpl_points", "mean"),
    )


def _player_prior(canonical: pd.DataFrame, data_root: Path, season: str) -> pd.DataFrame:
    rows = canonical[canonical["season"] == season].copy()
    lookup = _player_lookup(data_root, season)
    rows = rows.merge(lookup[["id", "code"]], left_on="element", right_on="id", validate="many_to_one")
    for column in PLAYER_TOTALS:
        rows[column] = pd.to_numeric(rows[column], errors="coerce").fillna(0)
    rows["appearance"] = rows["minutes"].gt(0).astype(int)
    prior = rows.groupby("code", as_index=False).agg(
        **{f"prior_{column}": (column, "sum") for column in PLAYER_TOTALS},
        prior_appearances=("appearance", "sum"),
        prior_gameweeks=("gameweek", "nunique"),
    )
    minutes = prior["prior_minutes"].replace(0, np.nan)
    appearances = prior["prior_appearances"].replace(0, np.nan)
    prior["prior_minutes_per_team_game"] = prior["prior_minutes"] / prior["prior_gameweeks"].replace(0, np.nan)
    prior["prior_points_per_team_game"] = prior["prior_total_points"] / prior["prior_gameweeks"].replace(0, np.nan)
    prior["prior_start_rate"] = prior["prior_starts"] / prior["prior_gameweeks"].replace(0, np.nan)
    prior["prior_appearance_rate"] = prior["prior_appearances"] / prior["prior_gameweeks"].replace(0, np.nan)
    prior["prior_minutes_per_appearance"] = prior["prior_minutes"] / appearances
    prior["prior_points_per_appearance"] = prior["prior_total_points"] / appearances
    for column in [
        "total_points", "goals_scored", "assists", "expected_goals", "expected_assists",
        "expected_goal_involvements", "clean_sheets", "saves", "bonus",
        "defensive_contribution",
    ]:
        prior[f"prior_{column}_per90"] = prior[f"prior_{column}"] / minutes * 90
    prior["has_prior_player_history"] = 1
    return prior


def _fixture_horizon(sides: pd.DataFrame, team_prior: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    upcoming = sides[sides["gameweek"].between(1, horizon)].copy()
    opponent = team_prior.add_prefix("opponent_").rename(columns={"opponent_team": "opponent_name"})
    upcoming = upcoming.merge(opponent, on="opponent_name", how="left", validate="many_to_one")
    upcoming["home"] = upcoming["was_home"].astype(int)
    opponent_columns = [
        "opponent_prior_team_goals_for", "opponent_prior_team_goals_against",
        "opponent_prior_team_xg", "opponent_prior_team_fpl_points",
    ]
    return upcoming.groupby("team", as_index=False).agg(
        fixtures_next5=("fixture", "count"),
        home_fixtures_next5=("home", "sum"),
        first_fixture_home=("home", "first"),
        **{f"mean_{column}_next5": (column, "mean") for column in opponent_columns},
    )


def _historical_target(
    canonical: pd.DataFrame, data_root: Path, prior_season: str, target_season: str
) -> pd.DataFrame:
    prior_players = _player_prior(canonical, data_root, prior_season)
    prior_teams = _team_prior(data_root, prior_season)
    raw = pd.read_csv(_merged_path(data_root, target_season), low_memory=False)
    gameweek = "GW" if "GW" in raw else "round"
    lookup = _player_lookup(data_root, target_season)
    previous_lookup = _player_lookup(data_root, prior_season)[["code", "team_code"]].rename(
        columns={"team_code": "prior_team_code"}
    )
    target = raw[raw[gameweek] == 1].merge(
        lookup, left_on="element", right_on="id", how="left", validate="many_to_one"
    )
    target = target[target["element_type"].isin([1, 2, 3, 4])].copy()
    target["target_appearance"] = target["minutes"].gt(0).astype(int)
    target["target_started"] = (
        pd.to_numeric(target["starts"], errors="coerce").fillna(0).gt(0)
        if "starts" in target else target["minutes"].ge(60)
    ).astype(int)
    target["target_played_60"] = target["minutes"].ge(60).astype(int)
    target = target.groupby("element", as_index=False).agg(
        code=("code", "first"), player_name=("web_name", "first"),
        element_type=("element_type", "first"), team=("team", "first"),
        team_code=("team_code", "first"), price=("value", "first"),
        target_points_1gw=("total_points", "sum"), target_minutes_gw1=("minutes", "sum"),
        target_appearance=("target_appearance", "max"), target_started=("target_started", "max"),
        target_played_60=("target_played_60", "max"),
    )
    sides = _fixture_sides(raw)
    horizon = _fixture_horizon(sides, prior_teams)
    target = target.merge(prior_players, on="code", how="left", validate="many_to_one")
    target = target.merge(previous_lookup, on="code", how="left", validate="many_to_one")
    target = target.merge(prior_teams, on="team", how="left", validate="many_to_one")
    target = target.merge(horizon, on="team", how="left", validate="many_to_one")
    target["season"] = target_season
    target["promoted_team"] = target["prior_team_games"].isna().astype(int)
    target["has_prior_player_history"] = target["has_prior_player_history"].fillna(0).astype(int)
    target["changed_team"] = (
        target["prior_team_code"].notna() & target["team_code"].ne(target["prior_team_code"])
    ).astype(int)
    target["position_changed"] = 0  # historical preseason position snapshots are unavailable
    target["defensive_contribution_rules"] = int(target_season >= "2025-26")
    target["availability_factor"] = 1.0
    return target


def _current_target(
    canonical: pd.DataFrame, data_root: Path, prior_season: str, target_season: str
) -> pd.DataFrame:
    prior_players = _player_prior(canonical, data_root, prior_season)
    previous_lookup = _player_lookup(data_root, prior_season)[
        ["code", "element_type", "team_code"]
    ].rename(
        columns={"element_type": "prior_element_type", "team_code": "prior_team_code"}
    )
    prior_teams = _team_prior(data_root, prior_season)

    season_dir = data_root / target_season
    players = pd.read_csv(season_dir / "players_raw.csv", low_memory=False)
    teams = pd.read_csv(season_dir / "teams.csv", usecols=["id", "name"])
    target = players[players["element_type"].isin([1, 2, 3, 4])].copy()
    if "can_select" in target:
        target = target[target["can_select"].fillna(False)]
    target = target.merge(teams.rename(columns={"id": "team", "name": "team_name"}), on="team", validate="many_to_one")
    target = target.rename(columns={
        "id": "element", "web_name": "player_name", "team": "team_id",
        "team_name": "team", "now_cost": "price",
    })

    fixtures = pd.read_csv(season_dir / "fixtures_canonical.csv", low_memory=False)
    name_map = teams.rename(columns={"id": "team", "name": "team_name"})
    fixtures = fixtures.merge(name_map, on="team", validate="many_to_one").rename(
        columns={"team": "team_id", "team_name": "team"}
    )
    fixtures = fixtures.merge(
        name_map.rename(columns={"team": "opponent_team", "team_name": "opponent_name"}),
        on="opponent_team", validate="many_to_one",
    )
    horizon = _fixture_horizon(fixtures, prior_teams)
    official = fixtures[fixtures["gameweek"].between(1, 5)].groupby("team", as_index=False).agg(
        mean_official_fdr_next5=("fixture_difficulty", "mean"),
        first_fixture_fdr=("fixture_difficulty", "first"),
    )

    target = target.merge(prior_players, on="code", how="left", validate="many_to_one")
    target = target.merge(previous_lookup, on="code", how="left", validate="many_to_one")
    target = target.merge(prior_teams, on="team", how="left", validate="many_to_one")
    target = target.merge(horizon, on="team", how="left", validate="many_to_one")
    target = target.merge(official, on="team", how="left", validate="many_to_one")
    target["season"] = target_season
    target["target_points_1gw"] = pd.NA
    target["target_minutes_gw1"] = pd.NA
    target["target_appearance"] = pd.NA
    target["target_started"] = pd.NA
    target["target_played_60"] = pd.NA
    target["promoted_team"] = target["prior_team_games"].isna().astype(int)
    target["has_prior_player_history"] = target["has_prior_player_history"].fillna(0).astype(int)
    target["changed_team"] = (
        target["prior_team_code"].notna() & target["team_code"].ne(target["prior_team_code"])
    ).astype(int)
    target["position_changed"] = (
        target["prior_element_type"].notna() & target["prior_element_type"].ne(target["element_type"])
    ).astype(int)
    target["defensive_contribution_rules"] = 1
    chance = pd.to_numeric(target.get("chance_of_playing_next_round"), errors="coerce") / 100
    status_factor = target.get("status", "a").map({"a": 1.0, "d": 0.75, "i": 0.0, "s": 0.0, "u": 0.0})
    target["availability_factor"] = chance.fillna(status_factor).fillna(1.0)
    target["penalty_order"] = pd.to_numeric(target.get("penalties_order"), errors="coerce")
    target["set_piece_order"] = pd.concat([
        pd.to_numeric(target.get("corners_and_indirect_freekicks_order"), errors="coerce"),
        pd.to_numeric(target.get("direct_freekicks_order"), errors="coerce"),
    ], axis=1).min(axis=1)
    return target


def build(data_root: Path, canonical_path: Path, current_season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    canonical = pd.read_csv(canonical_path, low_memory=False)
    seasons = sorted(canonical["season"].unique().tolist())
    historical = [
        _historical_target(canonical, data_root, seasons[index - 1], seasons[index])
        for index in range(1, len(seasons))
    ]
    training = pd.concat(historical, ignore_index=True, sort=False)
    current = _current_target(canonical, data_root, seasons[-1], current_season)
    return training, current


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GW1 prior training and candidate datasets")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--canonical", default="data/canonical_gameweeks.csv")
    parser.add_argument("--current-season", default=CURRENT_SEASON)
    parser.add_argument("--training-output", default="data/gw1_training.csv")
    parser.add_argument("--current-output")
    args = parser.parse_args()

    current_output = args.current_output or f"data/gw1_{args.current_season}_candidates.csv"
    training, current = build(Path(args.data_root), Path(args.canonical), args.current_season)
    training.to_csv(args.training_output, index=False)
    current.to_csv(current_output, index=False)
    print(f"Training: {len(training):,} rows across {training['season'].nunique()} target seasons")
    print(training.groupby("season").agg(
        players=("element", "size"), history_rate=("has_prior_player_history", "mean"),
        promoted=("promoted_team", "sum"), changed_team=("changed_team", "sum"),
    ).to_string())
    print(
        f"Current candidates: {len(current):,}; prior history: "
        f"{current['has_prior_player_history'].mean():.1%}; promoted-team players: "
        f"{current['promoted_team'].sum()}; transferred players: {current['changed_team'].sum()}"
    )


if __name__ == "__main__":
    main()
