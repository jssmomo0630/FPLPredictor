#!/usr/bin/env python3
"""
Fetch and save the latest available (post‑deadline) FPL squad for a given entry ID.

Usage:
  python fetch_entry_squad.py --entry-id 2536556

Notes:
- Determines the latest gameweek whose deadline has passed (so picks are public).
- Uses public endpoint: /api/entry/{entry_id}/event/{event_id}/picks/
- Also fetches /api/bootstrap-static/ to map element IDs -> names/teams and to
  resolve the most recent post‑deadline event id.
- Saves a JSON under squads/ with a timestamped filename including entry and GW.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error


BASE_URL = "https://fantasy.premierleague.com/api"


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_deadline(dt_str: str) -> datetime:
    # FPL returns ISO8601 with 'Z' suffix, e.g. '2025-08-09T10:30:00Z'
    # Convert to aware datetime in UTC.
    if dt_str.endswith("Z"):
        dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)


def resolve_latest_post_deadline_event_id(bootstrap: Dict[str, Any]) -> Optional[int]:
    events = bootstrap.get("events", [])
    if not events:
        return None

    now = datetime.now(timezone.utc)
    # Choose the event whose deadline_time <= now, with the max id
    eligible: List[Dict[str, Any]] = []
    for ev in events:
        dl = ev.get("deadline_time")
        if not dl:
            continue
        try:
            dl_dt = parse_deadline(dl)
        except Exception:
            continue
        if dl_dt <= now:
            eligible.append(ev)

    if not eligible:
        return None

    # Some seasons include explicit 'id' on events; otherwise use index position
    # Prefer explicit 'id', fallback to sequence number if missing.
    def event_id(ev: Dict[str, Any]) -> int:
        if isinstance(ev.get("id"), int):
            return ev["id"]
        # Fallback: try 'event' or position-like fields
        for key in ("event", "gw", "round"):
            if isinstance(ev.get(key), int):
                return ev[key]
        # Last resort: derive from 'name' like 'Gameweek 5'
        name = str(ev.get("name", ""))
        tokens = [int(t) for t in name.split() if t.isdigit()]
        return tokens[-1] if tokens else -1

    latest = max(eligible, key=event_id)
    eid = event_id(latest)
    return eid if isinstance(eid, int) and eid > 0 else None


def build_element_maps(bootstrap: Dict[str, Any]):
    elements = bootstrap.get("elements", [])
    teams = bootstrap.get("teams", [])
    element_to_name = {e["id"]: f"{e.get('first_name','')} {e.get('second_name','')}".strip() for e in elements}
    element_to_team_id = {e["id"]: e.get("team") for e in elements}
    team_id_to_name = {t["id"]: t.get("name") for t in teams}
    element_to_team_name = {eid: team_id_to_name.get(tid) for eid, tid in element_to_team_id.items()}
    element_to_pos = {e["id"]: e.get("element_type") for e in elements}
    return element_to_name, element_to_team_name, element_to_pos


def fetch_entry_picks(entry_id: int, event_id: int) -> Dict[str, Any]:
    url = f"{BASE_URL}/entry/{entry_id}/event/{event_id}/picks/"
    return fetch_json(url)


def normalize_output(
    entry_id: int,
    event_id: int,
    picks_payload: Dict[str, Any],
    bootstrap: Dict[str, Any],
) -> Dict[str, Any]:
    element_to_name, element_to_team, element_to_pos = build_element_maps(bootstrap)

    picks = picks_payload.get("picks", [])
    auto_subs = picks_payload.get("automatic_subs", [])
    entry_history = picks_payload.get("entry_history", {})
    active_chip = picks_payload.get("active_chip")

    # Decorate picks with names/teams
    decorated_picks = []
    for p in picks:
        el = p.get("element")
        decorated_picks.append(
            {
                "element": el,
                "player_name": element_to_name.get(el),
                "team_name": element_to_team.get(el),
                "position_type": element_to_pos.get(el),  # 1:GK,2:DEF,3:MID,4:FWD
                "position": p.get("position"),
                "multiplier": p.get("multiplier"),
                "is_captain": p.get("is_captain"),
                "is_vice_captain": p.get("is_vice_captain"),
            }
        )

    out: Dict[str, Any] = {
        "metadata": {
            "entry_id": entry_id,
            "event_id": event_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "active_chip": active_chip,
        },
        "entry_history": entry_history,
        "picks": decorated_picks,
        "automatic_subs": auto_subs,
        "raw": picks_payload,
    }
    return out


def save_json(data: Dict[str, Any], entry_id: int, event_id: int) -> str:
    os.makedirs("squads", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(
        "squads", f"current_squad_{entry_id}_gw{event_id}_{ts}.json"
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def main():
    parser = argparse.ArgumentParser(description="Fetch latest available FPL squad for an entry")
    parser.add_argument("--entry-id", type=int, default=2536556, help="FPL entry (team) ID")
    parser.add_argument("--event-id", type=int, default=None, help="Override event id (gameweek)")
    args = parser.parse_args()

    try:
        bootstrap = fetch_json(f"{BASE_URL}/bootstrap-static/")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Failed to fetch bootstrap-static: HTTP {e.code}")
    except Exception as e:
        raise SystemExit(f"Failed to fetch bootstrap-static: {e}")

    event_id = args.event_id
    if event_id is None:
        event_id = resolve_latest_post_deadline_event_id(bootstrap)
        if event_id is None:
            raise SystemExit("Could not determine a post-deadline event id. Is the season started?")

    try:
        picks_payload = fetch_entry_picks(args.entry_id, event_id)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(
                f"Entry {args.entry_id} or event {event_id} not found (HTTP 404)."
            )
        raise SystemExit(f"Failed to fetch picks: HTTP {e.code}")
    except Exception as e:
        raise SystemExit(f"Failed to fetch picks: {e}")

    output = normalize_output(args.entry_id, event_id, picks_payload, bootstrap)
    try:
        history = fetch_json(f"{BASE_URL}/entry/{args.entry_id}/history/")
        output["metadata"]["chips_used"] = history.get("chips", [])
    except Exception:
        output["metadata"]["chips_used"] = []
    out_path = save_json(output, args.entry_id, event_id)

    # Print concise summary
    names = [p.get("player_name") for p in output["picks"]]
    print(
        f"Saved squad for entry {args.entry_id}, GW {event_id} to {out_path}. Players: {', '.join([n for n in names if n])}"
    )


if __name__ == "__main__":
    main()
