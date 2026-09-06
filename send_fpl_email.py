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


def render_email(status: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return a deterministic subject, plain text, and HTML body."""
    if status.get("read_only") is not True:
        raise ValueError("Refusing to email a status payload not marked read_only=true")

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
    parser.add_argument("--preview-dir", default="artifacts/email_preview")
    parser.add_argument("--send", action="store_true", help="Send through Gmail SMTP after rendering")
    args = parser.parse_args()

    status = json.loads(Path(args.status).read_text(encoding="utf-8"))
    subject, text_body, html_body = render_email(status)
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
