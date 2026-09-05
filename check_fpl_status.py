#!/usr/bin/env python3
"""Read-only FPL deadline, gameweek, and published-squad availability monitor."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


BASE_URL = "https://fantasy.premierleague.com/api"
REQUEST_HEADERS = {
    "User-Agent": "FPLPredictor-status-monitor/1.0",
    "Accept": "application/json",
}
POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def fetch_json(path: str) -> Any:
    """Perform an unauthenticated GET against the official FPL API."""
    request = urllib.request.Request(f"{BASE_URL}/{path.lstrip('/')}", headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_deadline(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _event_summary(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "id": event.get("id"),
        "name": event.get("name"),
        "deadline_time": event.get("deadline_time"),
        "finished": bool(event.get("finished")),
        "data_checked": bool(event.get("data_checked")),
        "is_current": bool(event.get("is_current")),
        "is_next": bool(event.get("is_next")),
        "average_entry_score": event.get("average_entry_score"),
        "highest_score": event.get("highest_score"),
    }


def resolve_gameweeks(events: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    dated = [event for event in events if event.get("deadline_time")]
    passed = [event for event in dated if parse_deadline(event["deadline_time"]) <= now]
    upcoming = sorted(
        (event for event in dated if parse_deadline(event["deadline_time"]) > now),
        key=lambda event: parse_deadline(event["deadline_time"]),
    )
    current = next((event for event in events if event.get("is_current")), None)
    if current is None and passed:
        current = max(passed, key=lambda event: parse_deadline(event["deadline_time"]))
    latest_finished = max(
        (event for event in events if event.get("finished")),
        key=lambda event: int(event.get("id", 0)),
        default=None,
    )
    latest_published = max(
        passed, key=lambda event: int(event.get("id", 0)), default=None
    )
    return {
        "current": current,
        "next": upcoming[0] if upcoming else None,
        "latest_finished": latest_finished,
        "latest_published": latest_published,
    }


def availability_state(player: dict[str, Any]) -> str:
    status = player.get("status") or "a"
    chance = player.get("chance_of_playing_next_round")
    if status in {"i", "s", "u", "n"} or chance == 0:
        return "unavailable"
    if status == "d" or (isinstance(chance, (int, float)) and chance < 100):
        return "doubtful"
    return "available"


def _decision(hours_to_deadline: float | None, flagged_count: int, next_event_id: int | None) -> dict[str, Any]:
    if hours_to_deadline is None or next_event_id is None:
        return {
            "action": "season_complete",
            "window": None,
            "trigger_key": None,
            "reason": "No future gameweek deadline is published.",
        }
    if hours_to_deadline <= 6:
        window = "deadline_6h"
        return {
            "action": "run_recommendation",
            "window": window,
            "trigger_key": f"gw{next_event_id}:{window}",
            "reason": "The next deadline is within 6 hours.",
        }
    if hours_to_deadline <= 24:
        window = "deadline_24h"
        return {
            "action": "run_recommendation",
            "window": window,
            "trigger_key": f"gw{next_event_id}:{window}",
            "reason": "The next deadline is within 24 hours.",
        }
    if flagged_count:
        return {
            "action": "send_status_update",
            "window": "availability",
            "trigger_key": f"gw{next_event_id}:availability",
            "reason": f"{flagged_count} published-squad player(s) have an availability flag.",
        }
    return {
        "action": "no_action",
        "window": "monitoring",
        "trigger_key": None,
        "reason": "The deadline is more than 24 hours away and no squad player is flagged.",
    }


def build_status(
    bootstrap: dict[str, Any],
    picks_payload: dict[str, Any] | None,
    entry_id: int,
    squad_event_id: int | None,
    now: datetime,
    timezone_name: str,
) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    local_zone = ZoneInfo(timezone_name)
    resolved = resolve_gameweeks(bootstrap.get("events", []), now)
    next_event = resolved["next"]
    deadline = parse_deadline(next_event["deadline_time"]) if next_event else None
    hours_to_deadline = (deadline - now).total_seconds() / 3600 if deadline else None

    teams = {team["id"]: team.get("name") for team in bootstrap.get("teams", [])}
    elements = {element["id"]: element for element in bootstrap.get("elements", [])}
    squad_players = []
    for pick in (picks_payload or {}).get("picks", []):
        element = elements.get(pick.get("element"), {})
        state = availability_state(element)
        squad_players.append({
            "element": pick.get("element"),
            "player_name": element.get("web_name"),
            "team": teams.get(element.get("team")),
            "position": POSITION_NAMES.get(element.get("element_type")),
            "squad_position": pick.get("position"),
            "is_captain": bool(pick.get("is_captain")),
            "is_vice_captain": bool(pick.get("is_vice_captain")),
            "availability": state,
            "status": element.get("status"),
            "chance_of_playing_next_round": element.get("chance_of_playing_next_round"),
            "news": element.get("news") or "",
            "news_added": element.get("news_added"),
        })
    counts = {
        state: sum(player["availability"] == state for player in squad_players)
        for state in ("available", "doubtful", "unavailable")
    }
    flagged = counts["doubtful"] + counts["unavailable"]

    return {
        "schema_version": 1,
        "read_only": True,
        "checked_at_utc": now.isoformat(),
        "timezone": timezone_name,
        "entry_id": entry_id,
        "gameweek": {
            "current": _event_summary(resolved["current"]),
            "next": _event_summary(next_event),
            "latest_finished": _event_summary(resolved["latest_finished"]),
            "latest_finished_is_finalized": bool(
                resolved["latest_finished"] and resolved["latest_finished"].get("data_checked")
            ),
            "deadline_time_utc": deadline.isoformat() if deadline else None,
            "deadline_time_local": deadline.astimezone(local_zone).isoformat() if deadline else None,
            "hours_to_deadline": round(hours_to_deadline, 2) if hours_to_deadline is not None else None,
        },
        "squad": {
            "source": "public_post_deadline_picks" if picks_payload else "unavailable",
            "source_event_id": squad_event_id,
            "player_count": len(squad_players),
            "availability_counts": counts,
            "flagged_count": flagged,
            "players": squad_players,
        },
        "decision": _decision(
            hours_to_deadline,
            flagged,
            int(next_event["id"]) if next_event else None,
        ),
    }


def main() -> None:
    env_entry_id = os.environ.get("FPL_ENTRY_ID")
    parser = argparse.ArgumentParser(description="Check FPL status without changing an FPL team")
    parser.add_argument("--entry-id", type=int, default=int(env_entry_id) if env_entry_id else None)
    parser.add_argument("--timezone", default=os.environ.get("FPL_TIMEZONE", "America/Los_Angeles"))
    parser.add_argument("--output", default="artifacts/fpl_status.json")
    args = parser.parse_args()
    if args.entry_id is None:
        parser.error("--entry-id or FPL_ENTRY_ID is required")

    try:
        bootstrap = fetch_json("bootstrap-static/")
        resolved = resolve_gameweeks(bootstrap.get("events", []), datetime.now(timezone.utc))
        squad_event = resolved["latest_published"]
        picks_payload = (
            fetch_json(f"entry/{args.entry_id}/event/{squad_event['id']}/picks/")
            if squad_event else None
        )
    except urllib.error.HTTPError as error:
        raise SystemExit(f"FPL API request failed with HTTP {error.code}") from error
    except Exception as error:
        raise SystemExit(f"FPL status check failed: {error}") from error

    report = build_status(
        bootstrap,
        picks_payload,
        args.entry_id,
        int(squad_event["id"]) if squad_event else None,
        datetime.now(timezone.utc),
        args.timezone,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "output": str(output),
        "next_gameweek": (report["gameweek"]["next"] or {}).get("id"),
        "hours_to_deadline": report["gameweek"]["hours_to_deadline"],
        "flagged_players": report["squad"]["flagged_count"],
        "decision": report["decision"],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
