#!/usr/bin/env python3
"""Render and optionally send a read-only FPL status email through Gmail SMTP."""

from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, getaddresses
from pathlib import Path
from typing import Any, Mapping


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _recipient_addresses(value: str) -> list[str]:
    addresses = [address for _, address in getaddresses([value]) if address]
    if not addresses:
        raise ValueError("EMAIL_TO must contain at least one valid address")
    return addresses


def _deadline_label(status: Mapping[str, Any]) -> str:
    gameweek = status.get("gameweek", {})
    return gameweek.get("deadline_time_local") or gameweek.get("deadline_time_utc") or "not published"


def _render_advice_email(
    status: Mapping[str, Any],
    advice: Mapping[str, Any],
    summary_payload: Mapping[str, Any] | None,
) -> tuple[str, str, str]:
    if advice.get("read_only") is not True or advice.get("advisory_only") is not True:
        raise ValueError("Refusing to email advice not marked read_only and advisory_only")
    recommendation = advice.get("recommendation", {})
    assumptions = advice.get("assumptions", {})
    gameweek = advice.get("target_gameweek")
    hours = advice.get("hours_to_deadline")
    timing = f" — {hours:.0f}h to deadline" if isinstance(hours, (int, float)) else ""
    subject = f"[FPL] GW{gameweek} recommendations{timing}"
    summary = (summary_payload or {}).get("summary") or advice.get("deterministic_summary", "")
    summary_label = "AI commentary" if (summary_payload or {}).get("used_ai") else "Summary"
    transfers_out = recommendation.get("transfers_out", [])
    transfers_in = recommendation.get("transfers_in", [])
    transfer_lines = [
        f"- {outgoing.get('player_name')} → {incoming.get('player_name')}"
        for outgoing, incoming in zip(transfers_out, transfers_in)
    ] or ["- No transfer; roll if the stated assumptions match your team."]
    starters = recommendation.get("starting_xi", [])
    captain = recommendation.get("captain", {}).get("player_name")
    vice = recommendation.get("vice_captain", {}).get("player_name")
    bench = recommendation.get("bench", [])
    chip_advice = recommendation.get("chip_advice", {})
    chip_period = chip_advice.get("chip_period") or {}
    chip_period_text = (
        f"Active chip set: GW{chip_period.get('start_gameweek')}-"
        f"GW{chip_period.get('end_gameweek')} (expires at the GW"
        f"{chip_period.get('end_gameweek')} deadline)"
        if chip_period.get("start_gameweek") is not None
        and chip_period.get("end_gameweek") is not None
        else "Active chip-set period unavailable"
    )
    chip_schedule = chip_advice.get("tentative_schedule", [])
    chip_schedule_text = "; ".join(
        f"{str(row.get('chip')).replace('_', ' ').title()} GW{row.get('gameweek')}"
        for row in chip_schedule
    ) or "No future chip slot currently clears the planning threshold"
    conflicts = recommendation.get("opponent_conflicts", [])
    flags = [
        player for player in status.get("squad", {}).get("players", [])
        if player.get("availability") != "available"
    ]
    flag_lines = [
        f"- {player.get('player_name')}: {player.get('availability')}"
        + (f" — {player.get('news')}" if player.get("news") else "")
        for player in flags
    ] or ["- None"]
    conflict_lines = [
        f"- {row.get('attacking_player')} vs {row.get('defensive_player')} "
        f"({float(row.get('penalty_points', 0)):.2f}-point soft penalty)"
        for row in conflicts
    ] or ["- None in the recommended starting XI"]
    text_body = "\n".join([
        f"FPL GW{gameweek} recommendations",
        "",
        str(summary),
        "",
        f"Deadline: {advice.get('deadline_time_local')}",
        f"Primary advice: {recommendation.get('headline')}",
        f"Transfer hit: {recommendation.get('hit_cost_points', 0):g} points",
        f"Projected bank after moves: £{recommendation.get('bank_after_millions', 0):.1f}m",
        "",
        "Transfers:",
        *transfer_lines,
        "",
        f"Starting XI: {', '.join(str(row.get('player_name')) for row in starters)}",
        f"Captain: {captain}",
        f"Vice-captain: {vice}",
        f"Bench order: {', '.join(str(row.get('player_name')) for row in bench)}",
        f"Chip advice: {chip_advice.get('recommendation') or 'No chip recommendation available'}",
        chip_period_text,
        f"Tentative chip schedule: {chip_schedule_text}",
        "",
        "Opposing-player overlaps:",
        *conflict_lines,
        "",
        "Availability flags:",
        *flag_lines,
        "",
        f"Assumed free transfers: {assumptions.get('free_transfers_assumed')}",
        str(assumptions.get("public_squad_warning") or ""),
        str(assumptions.get("free_transfer_warning") or ""),
        str(assumptions.get("selling_price_warning") or ""),
        "",
        "Advisory only: review and apply any changes manually in FPL.",
    ]) + "\n"

    def escaped(value: Any) -> str:
        return html.escape(str(value))

    transfers_html = "".join(
        f"<li>{escaped(outgoing.get('player_name'))} → {escaped(incoming.get('player_name'))}</li>"
        for outgoing, incoming in zip(transfers_out, transfers_in)
    ) or "<li>No transfer; roll if the stated assumptions match your team.</li>"
    flags_html = "".join(
        f"<li><strong>{escaped(player.get('player_name'))}</strong>: {escaped(player.get('availability'))}"
        f"{' — ' + escaped(player.get('news')) if player.get('news') else ''}</li>"
        for player in flags
    ) or "<li>None</li>"
    starters_html = "".join(f"<li>{escaped(row.get('player_name'))} ({escaped(row.get('position'))})</li>" for row in starters)
    bench_html = "".join(
        f"<li>{escaped(row.get('player_name'))} ({escaped(row.get('position'))})</li>" for row in bench
    )
    conflicts_html = "".join(
        f"<li>{escaped(row.get('attacking_player'))} vs {escaped(row.get('defensive_player'))} "
        f"({escaped(format(float(row.get('penalty_points', 0)), '.2f'))}-point soft penalty)</li>"
        for row in conflicts
    ) or "<li>None in the recommended starting XI</li>"
    html_body = f"""<!doctype html>
<html lang="en">
  <body style="font-family:Arial,sans-serif;line-height:1.5;color:#17202a">
    <h1 style="font-size:22px">FPL GW{escaped(gameweek)} recommendations</h1>
    <p style="padding:12px;background:#e8f4fd"><strong>{escaped(summary_label)}:</strong> {escaped(summary)}</p>
    <p><strong>Deadline:</strong> {escaped(advice.get('deadline_time_local'))}<br>
       <strong>Primary advice:</strong> {escaped(recommendation.get('headline'))}<br>
       <strong>Transfer hit:</strong> {escaped(recommendation.get('hit_cost_points', 0))} points<br>
       <strong>Projected bank:</strong> £{escaped(f"{recommendation.get('bank_after_millions', 0):.1f}")}m</p>
    <h2 style="font-size:18px">Transfers</h2><ul>{transfers_html}</ul>
    <h2 style="font-size:18px">Starting XI</h2><ul>{starters_html}</ul>
    <p><strong>Captain:</strong> {escaped(captain)}<br><strong>Vice-captain:</strong> {escaped(vice)}</p>
    <h2 style="font-size:18px">Bench order</h2><ol>{bench_html}</ol>
    <p><strong>Chip advice:</strong> {escaped(chip_advice.get('recommendation') or 'No chip recommendation available')}<br>
       <strong>{escaped(chip_period_text)}</strong><br>
       Tentative schedule: {escaped(chip_schedule_text)}</p>
    <h2 style="font-size:18px">Opposing-player overlaps</h2><ul>{conflicts_html}</ul>
    <h2 style="font-size:18px">Availability flags</h2><ul>{flags_html}</ul>
    <div style="padding:12px;background:#fff4ce">
      <strong>Important assumptions</strong>
      <ul>
        <li>Free transfers assumed: {escaped(assumptions.get('free_transfers_assumed'))}</li>
        <li>{escaped(assumptions.get('public_squad_warning'))}</li>
        <li>{escaped(assumptions.get('free_transfer_warning'))}</li>
        <li>{escaped(assumptions.get('selling_price_warning'))}</li>
      </ul>
    </div>
    <p><strong>Advisory only:</strong> review and apply changes manually in FPL.</p>
  </body>
</html>
"""
    return subject, text_body, html_body


def render_email(
    status: Mapping[str, Any],
    advice: Mapping[str, Any] | None = None,
    summary_payload: Mapping[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Return a deterministic subject, plain text, and HTML body."""
    if status.get("read_only") is not True:
        raise ValueError("Refusing to email a status payload not marked read_only=true")
    if advice is not None:
        return _render_advice_email(status, advice, summary_payload)

    gameweek = status.get("gameweek", {})
    next_event = gameweek.get("next") or {}
    squad = status.get("squad", {})
    decision = status.get("decision", {})
    next_id = next_event.get("id")
    next_label = f"GW{next_id}" if next_id is not None else "season status"
    deadline = _deadline_label(status)
    source_event = squad.get("source_event_id")
    players = squad.get("players", [])
    flagged = [player for player in players if player.get("availability") != "available"]

    subject = f"[FPL] Email delivery test — {next_label}"
    source_note = (
        f"The squad is the public lineup locked at the GW{source_event} deadline. "
        "Transfers made since that deadline are not visible through the public API."
        if source_event is not None
        else "No public post-deadline squad was available."
    )
    flagged_lines = [
        f"- {player.get('player_name')}: {player.get('availability')}"
        + (f" — {player.get('news')}" if player.get("news") else "")
        for player in flagged
    ] or ["- None"]
    player_lines = [
        f"- {player.get('position')}: {player.get('player_name')} ({player.get('team')})"
        for player in players
    ]
    text_body = "\n".join([
        "FPL email delivery test",
        "",
        "This message verifies GitHub Actions → Gmail delivery. It is not a transfer recommendation.",
        f"Next deadline: {deadline}",
        f"Decision: {decision.get('action', 'unknown')} — {decision.get('reason', '')}",
        f"Published squad players: {squad.get('player_count', len(players))}",
        "",
        "Availability flags:",
        *flagged_lines,
        "",
        "Published squad:",
        *player_lines,
        "",
        source_note,
        "No transfers, chips, captaincy changes, or lineup changes were submitted.",
    ]) + "\n"

    def escaped(value: Any) -> str:
        return html.escape(str(value))

    flagged_html = "".join(
        f"<li><strong>{escaped(player.get('player_name'))}</strong>: "
        f"{escaped(player.get('availability'))}"
        f"{' — ' + escaped(player.get('news')) if player.get('news') else ''}</li>"
        for player in flagged
    ) or "<li>None</li>"
    players_html = "".join(
        f"<li>{escaped(player.get('position'))}: {escaped(player.get('player_name'))} "
        f"({escaped(player.get('team'))})</li>"
        for player in players
    )
    html_body = f"""<!doctype html>
<html lang="en">
  <body style="font-family:Arial,sans-serif;line-height:1.5;color:#17202a">
    <h1 style="font-size:22px">FPL email delivery test</h1>
    <p>This verifies GitHub Actions → Gmail delivery. It is <strong>not</strong> a transfer recommendation.</p>
    <p><strong>Next deadline:</strong> {escaped(deadline)}<br>
       <strong>Decision:</strong> {escaped(decision.get('action', 'unknown'))} — {escaped(decision.get('reason', ''))}<br>
       <strong>Published squad players:</strong> {escaped(squad.get('player_count', len(players)))}</p>
    <h2 style="font-size:18px">Availability flags</h2>
    <ul>{flagged_html}</ul>
    <h2 style="font-size:18px">Published squad</h2>
    <ul>{players_html}</ul>
    <p style="padding:12px;background:#fff4ce"><strong>Data limitation:</strong> {escaped(source_note)}</p>
    <p>No transfers, chips, captaincy changes, or lineup changes were submitted.</p>
  </body>
</html>
"""
    return subject, text_body, html_body


def build_message(
    subject: str,
    text_body: str,
    html_body: str,
    sender: str,
    recipients: list[str],
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("FPL Advisor", sender))
    message["To"] = ", ".join(recipients)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_message(message: EmailMessage, username: str, app_password: str) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
        smtp.login(username, app_password)
        smtp.send_message(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render or send the FPL status email")
    parser.add_argument("--status", default="artifacts/fpl_status.json")
    parser.add_argument("--advice", help="Optional recommendation JSON")
    parser.add_argument("--summary", help="Optional deterministic/Gemini summary JSON")
    parser.add_argument("--preview-dir", default="artifacts/email_preview")
    parser.add_argument("--send", action="store_true", help="Send through Gmail SMTP after rendering")
    args = parser.parse_args()

    status = json.loads(Path(args.status).read_text(encoding="utf-8"))
    advice = json.loads(Path(args.advice).read_text(encoding="utf-8")) if args.advice else None
    summary_payload = json.loads(Path(args.summary).read_text(encoding="utf-8")) if args.summary else None
    subject, text_body, html_body = render_email(status, advice, summary_payload)
    preview = Path(args.preview_dir)
    preview.mkdir(parents=True, exist_ok=True)
    (preview / "subject.txt").write_text(subject + "\n", encoding="utf-8")
    (preview / "body.txt").write_text(text_body, encoding="utf-8")
    (preview / "body.html").write_text(html_body, encoding="utf-8")

    sent = False
    recipient_count = 0
    if args.send:
        required = ("SMTP_USERNAME", "SMTP_APP_PASSWORD", "EMAIL_TO")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise SystemExit(f"Missing required email secret(s): {', '.join(missing)}")
        username = os.environ["SMTP_USERNAME"].strip()
        app_password = os.environ["SMTP_APP_PASSWORD"].replace(" ", "")
        recipients = _recipient_addresses(os.environ["EMAIL_TO"])
        message = build_message(subject, text_body, html_body, username, recipients)
        send_message(message, username, app_password)
        sent = True
        recipient_count = len(recipients)

    print(json.dumps({
        "preview_dir": str(preview),
        "subject": subject,
        "sent": sent,
        "recipient_count": recipient_count,
    }, indent=2))


if __name__ == "__main__":
    main()
