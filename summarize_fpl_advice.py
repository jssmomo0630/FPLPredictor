#!/usr/bin/env python3
"""Optionally summarize deterministic FPL advice with Gemini, with safe fallback."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gemini-3.5-flash-lite"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _facts(advice: dict[str, Any]) -> dict[str, Any]:
    recommendation = advice["recommendation"]
    return {
        "target_gameweek": advice["target_gameweek"],
        "deadline_time_local": advice.get("deadline_time_local"),
        "headline": recommendation["headline"],
        "transfers_out": recommendation["transfers_out"],
        "transfers_in": recommendation["transfers_in"],
        "hit_cost_points": recommendation["hit_cost_points"],
        "points_comparison": recommendation.get("points_comparison"),
        "captain": recommendation["captain"]["player_name"],
        "vice_captain": recommendation["vice_captain"]["player_name"],
        "bench_order": [row["player_name"] for row in recommendation["bench"]],
        "chip_advice": recommendation["chip_advice"].get("recommendation"),
        "assumptions": advice["assumptions"],
    }


def gemini_summary(advice: dict[str, Any], api_key: str, model: str) -> str:
    prompt = (
        "Write a concise FPL manager briefing of at most 140 words from the JSON facts below. "
        "Do not introduce players, prices, points, injuries, fixtures, or claims absent from the JSON. "
        "Explain projected net gains when provided, distinguishing next week from the whole plan. "
        "Do not attribute the whole horizon gain to today's transfers or invent causal explanations. "
        "Clearly label the public-squad and free-transfer limitations. Use plain text, not markdown.\n\n"
        + json.dumps(_facts(advice), ensure_ascii=False)
    )
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": prompt}]}]}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/{model}:generateContent",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "FPLPredictor-advice-summary/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise ValueError("Gemini returned no summary text")
    return text


def build_summary(advice: dict[str, Any], api_key: str | None, model: str) -> dict[str, Any]:
    if advice.get("read_only") is not True or advice.get("advisory_only") is not True:
        raise ValueError("Advice must be marked read_only and advisory_only")
    provider = "deterministic"
    summary = advice["deterministic_summary"]
    error = None
    if api_key:
        try:
            summary = gemini_summary(advice, api_key, model)
            provider = "gemini"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
            error = f"{type(exc).__name__}: {exc}"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model if provider == "gemini" else None,
        "used_ai": provider == "gemini",
        "summary": summary,
        "fallback_reason": error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Optionally summarize FPL advice with Gemini")
    parser.add_argument("--advice", default="artifacts/fpl_advice.json")
    parser.add_argument("--output", default="artifacts/fpl_summary.json")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()
    advice = json.loads(Path(args.advice).read_text(encoding="utf-8"))
    result = build_summary(advice, os.environ.get("GEMINI_API_KEY"), args.model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "provider": result["provider"],
        "used_ai": result["used_ai"],
        "fallback": result["fallback_reason"] is not None,
    }, indent=2))


if __name__ == "__main__":
    main()
