"""Shared, versioned configuration for reproducible FPL data acquisition."""

from __future__ import annotations

import csv
from pathlib import Path


CURRENT_SEASON = "2026-27"
HISTORICAL_SEASONS = (
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
)

# This immutable vaastav revision contains the completed 2025-26 season.
VAASTAV_REF = "9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88"


def historical_source_paths(data_root: Path, season: str) -> tuple[Path, Path] | None:
    """Return the compact historical inputs, supporting the legacy layout."""
    season_dir = data_root / season
    nested_players = season_dir / "vaastav" / "players_raw.csv"
    nested_merged = season_dir / "vaastav" / "merged_gw.csv"
    if nested_players.is_file() and nested_merged.is_file():
        return nested_players, nested_merged

    legacy_players = season_dir / "players_raw.csv"
    legacy_merged = season_dir / "merged_gw.csv"
    if not (legacy_players.is_file() and legacy_merged.is_file()):
        return None
    try:
        with legacy_merged.open(newline="", encoding="utf-8-sig") as handle:
            columns = next(csv.reader(handle))
    except (OSError, StopIteration):
        return None
    # vaastav's merged file includes the display position. Older official-API
    # snapshots used the same filename but do not, so do not mistake them for
    # a complete historical source.
    return (legacy_players, legacy_merged) if "position" in columns else None


def missing_historical_seasons(data_root: Path, seasons: list[str] | tuple[str, ...]) -> list[str]:
    return [season for season in seasons if historical_source_paths(data_root, season) is None]
