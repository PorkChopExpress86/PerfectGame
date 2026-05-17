#!/usr/bin/env python3
"""
usssa_team_monitor.py - Monitors USSSA team schedule for new/changed upcoming games.

Polls the USSSA teamInfoV11 API for team 3313953 (D1 Athletics, 10u AA).
When new upcoming games are detected or game details change, sends an email alert.

No Playwright required — the USSSA API is accessible via plain HTTP POST.

Usage:
    .venv/bin/python usssa_team_monitor.py
    .venv/bin/python usssa_team_monitor.py --once       # single check, no loop
    .venv/bin/python usssa_team_monitor.py --force      # send email even if no changes
    .venv/bin/python usssa_team_monitor.py --interval 15

Environment variables (from .env):
    EMAIL_ADDRESS       - Gmail sender address
    EMAIL_APP_PASSWORD  - Gmail app password
    TO_EMAILS           - Comma-separated recipient list
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

from shared.telegram_notifier import send_telegram
from shared.history_logger import log_notification
from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

EMAIL_ADDRESS: str | None = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD: str | None = os.getenv("EMAIL_APP_PASSWORD")
TO_EMAILS: str = os.getenv("TO_EMAILS", EMAIL_ADDRESS or "")

TEAM_ID = "3313953"
TEAM_NAME = "D1 Athletics"

SNAPSHOT_FILE = ROOT_DIR / ".usssa_team_schedule.json"
LOG_FILE = ROOT_DIR / "usssa_team_monitor.log"

USSSA_API_URL = "https://www.usssa.com/api/?action=teamInfoV11"
TEAM_PAGE_URL = f"https://www.usssa.com/default/teamHome/?gdSport=&teamID={TEAM_ID}"

DEFAULT_INTERVAL_MINUTES = 30

_shutdown_requested = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [usssa-team] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------
def fetch_team_info() -> dict[str, Any] | None:
    """
    POST to the USSSA teamInfoV11 API and return the parsed JSON response.
    Returns None on failure.
    """
    try:
        resp = requests.post(
            USSSA_API_URL,
            data={"teamID": TEAM_ID, "page": "home", "divID": "undefined"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        _log(f"  ERROR fetching team info: {exc}")
        return None


# ---------------------------------------------------------------------------
# Game normalization
# ---------------------------------------------------------------------------
def _parse_date(iso_str: str) -> str:
    """Convert '2026-03-29T00:00:00' → 'Mar 29'."""
    try:
        return datetime.fromisoformat(iso_str).strftime("%b %d")
    except (ValueError, TypeError):
        return iso_str or "TBD"


def normalize_upcoming(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw upcomingGames entry into the project's standard format."""
    return {
        "GameID": int(raw.get("gameId") or 0),
        "Date": _parse_date(raw.get("the_date", "")),
        "SortDate": raw.get("sortDate", ""),
        "Time": raw.get("the_time", "TBD"),
        "Opponent": (raw.get("opponent") or "TBD").title(),
        "Location": raw.get("fieldName", "TBD"),
        "Event": (raw.get("event") or "").title(),
        "EventID": raw.get("eventID"),
        "Type": "Upcoming",
    }


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------
def _load_snapshot() -> dict[str, Any]:
    if SNAPSHOT_FILE.exists():
        try:
            return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_snapshot(data: dict[str, Any]) -> None:
    SNAPSHOT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------
_TRACKED_FIELDS = ("Date", "Time", "Opponent", "Location", "Event")


def detect_changes(
    old_games: list[dict],
    new_games: list[dict],
) -> tuple[list[dict], list[dict[str, Any]]]:
    """
    Compare old and new upcoming game lists by GameID.

    Returns:
        added   - games in new_games not present in old_games
        changed - list of {"old": ..., "new": ..., "fields": [...]}
    """
    old_by_id = {g["GameID"]: g for g in old_games}
    new_by_id = {g["GameID"]: g for g in new_games}

    added = [g for gid, g in new_by_id.items() if gid not in old_by_id]

    changed = []
    for gid, new_g in new_by_id.items():
        if gid not in old_by_id:
            continue
        old_g = old_by_id[gid]
        diff = [f for f in _TRACKED_FIELDS if new_g.get(f) != old_g.get(f)]
        if diff:
            changed.append({"old": old_g, "new": new_g, "fields": diff})

    return added, changed


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def _build_email_html(
    added: list[dict],
    changed: list[dict[str, Any]],
    all_upcoming: list[dict],
) -> str:
    now_str = datetime.now().strftime("%I:%M %p on %B %d, %Y")

    def _game_row(g: dict, highlight: str = "") -> str:
        bg = f'style="background:{highlight};"' if highlight else ""
        return (
            f'<tr {bg}>'
            f'<td style="padding:8px;border:1px solid #ddd;">{g.get("Date","TBD")}</td>'
            f'<td style="padding:8px;border:1px solid #ddd;">{g.get("Time","TBD")}</td>'
            f'<td style="padding:8px;border:1px solid #ddd;">{g.get("Opponent","TBD")}</td>'
            f'<td style="padding:8px;border:1px solid #ddd;">{g.get("Location","TBD")}</td>'
            f'<td style="padding:8px;border:1px solid #ddd;">{g.get("Event","")}</td>'
            f"</tr>"
        )

    header_row = (
        '<tr style="background-color:#1a3a5c;color:white;">'
        '<th style="padding:10px;border:1px solid #ddd;">Date</th>'
        '<th style="padding:10px;border:1px solid #ddd;">Time</th>'
        '<th style="padding:10px;border:1px solid #ddd;">Opponent</th>'
        '<th style="padding:10px;border:1px solid #ddd;">Location</th>'
        '<th style="padding:10px;border:1px solid #ddd;">Event</th>'
        "</tr>"
    )

    sections = ""

    if added:
        rows = "".join(_game_row(g, "#e8f5e9") for g in added)
        sections += f"""
        <h3 style="color:#2d6a4f;">New Game(s) Added</h3>
        <table style="border-collapse:collapse;width:100%;max-width:900px;">
            <thead>{header_row}</thead>
            <tbody>{rows}</tbody>
        </table>"""

    if changed:
        change_rows = ""
        for c in changed:
            change_rows += _game_row(c["new"], "#fff8e1")
            change_rows += (
                f'<tr><td colspan="5" style="padding:4px 8px;font-size:11px;'
                f'color:#888;border:1px solid #eee;">Changed: {", ".join(c["fields"])}</td></tr>'
            )
        sections += f"""
        <h3 style="color:#b45309;">Game Detail Change(s)</h3>
        <table style="border-collapse:collapse;width:100%;max-width:900px;">
            <thead>{header_row}</thead>
            <tbody>{change_rows}</tbody>
        </table>"""

    if all_upcoming:
        rows = "".join(_game_row(g) for g in sorted(all_upcoming, key=lambda g: g.get("SortDate", "")))
        sections += f"""
        <h3 style="color:#555;">All Upcoming Games</h3>
        <table style="border-collapse:collapse;width:100%;max-width:900px;">
            <thead>{header_row}</thead>
            <tbody>{rows}</tbody>
        </table>"""

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">⚾ USSSA Schedule Update — {TEAM_NAME}</h2>
        <p>Schedule updated as of <strong>{now_str}</strong>.</p>
        {sections}
        <p>
            <a href="{TEAM_PAGE_URL}"
               style="display:inline-block;padding:10px 20px;background-color:#1a3a5c;
                      color:white;text-decoration:none;border-radius:5px;">
                View Team Page
            </a>
        </p>
        <br>
        <p style="font-size:12px;color:#888;">Powered by USSSA Team Monitor</p>
    </body>
    </html>
    """


def send_notification(
    added: list[dict],
    changed: list[dict[str, Any]],
    all_upcoming: list[dict],
) -> bool:
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        _log("ERROR: EMAIL_ADDRESS / EMAIL_APP_PASSWORD not set in .env")
        return False

    recipients = [e.strip() for e in TO_EMAILS.split(",") if e.strip()]
    if not recipients:
        _log("ERROR: No recipients configured (TO_EMAILS in .env)")
        return False

    parts = []
    if added:
        parts.append(f"{len(added)} new game(s)")
    if changed:
        parts.append(f"{len(changed)} change(s)")
    subject = f"⚾ {TEAM_NAME} USSSA Schedule — {', '.join(parts)}"

    html = _build_email_html(added, changed, all_upcoming)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))

    try:
        _log(f"  Sending email to {recipients}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, recipients, msg.as_string())
        _log("  ✅ Email sent.")
        # Send Telegram notification
        tg_body = "\n".join([f"🆕 {g.get("Date")} {g.get("Time")} vs {g.get("Opponent")}" for g in added])
        if changed:
            tg_body += "\n" + "\n".join([f"🔄 {c["new"].get("Date")} {c["new"].get("Time")} vs {c["new"].get("Opponent")}" for c in changed])
        send_telegram(subject, tg_body)
        log_notification("usssa_team", subject)
        return True
    except smtplib.SMTPAuthenticationError:
        _log("  ❌ SMTP auth failed — check EMAIL_APP_PASSWORD")
        return False
    except Exception as exc:
        _log(f"  ❌ Email failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------
def check_for_changes(force: bool = False) -> bool:
    """
    Fetch current upcoming games, compare to snapshot, notify on changes.
    Returns True if an email was sent.
    """
    _log("Fetching team info from USSSA API...")
    data = fetch_team_info()
    if data is None:
        _log("  ⚠ Failed to fetch — will retry next cycle.")
        return False

    raw_upcoming: list[dict] = data.get("upcomingGames") or []
    current_games = [normalize_upcoming(g) for g in raw_upcoming]

    _log(f"  Found {len(current_games)} upcoming game(s).")

    snapshot = _load_snapshot()
    is_first_run = "games" not in snapshot
    previous_games: list[dict] = snapshot.get("games", [])

    added, changed = detect_changes(previous_games, current_games)

    _log(f"  Change summary: added={len(added)}, changed={len(changed)}, is_first_run={is_first_run}, force={force}")

    # Save snapshot
    _save_snapshot({
        "last_checked": datetime.now().isoformat(),
        "games": current_games,
    })

    if added:
        _log(f"  🆕 {len(added)} new game(s):")
        for g in added:
            _log(f"    → {g['Date']} {g['Time']} vs {g['Opponent']} @ {g['Location']}")

    if changed:
        _log(f"  🔔 {len(changed)} game(s) changed:")
        for c in changed:
            _log(f"    → {c['new']['Date']} vs {c['new']['Opponent']} — {c['fields']}")

    if not added and not changed:
        _log("  ✓ No changes.")

    should_send = (len(added) > 0 or len(changed) > 0) and not is_first_run
    if force:
        _log("  Force flag is set — will send notification.")
        should_send = True

    if is_first_run and not force:
        _log("  First run — snapshot captured. No notification sent.")
        return False

    if should_send:
        _log("  Sending notification...")
        send_notification(added, changed, current_games)
        return True

    _log("  No notification needed.")
    return False


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------
def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown_requested
    _log(f"Received {signal.Signals(signum).name} — shutting down.")
    _shutdown_requested = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor USSSA team schedule for changes."
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL_MINUTES,
        help=f"Polling interval in minutes (default: {DEFAULT_INTERVAL_MINUTES}).",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single check and exit.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Send email even if no changes detected.",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _log("=" * 60)
    _log("USSSA Team Monitor starting")
    _log(f"  Team:      {TEAM_NAME} (teamID={TEAM_ID})")
    _log(f"  Interval:  {args.interval} minutes")
    _log(f"  Recipients: {TO_EMAILS}")
    _log("=" * 60)

    if args.once:
        check_for_changes(force=args.force)
        _log("Single check complete. Exiting.")
        return

    while not _shutdown_requested:
        try:
            check_for_changes(force=args.force)
        except Exception as exc:
            _log(f"Unhandled error: {exc}")

        if _shutdown_requested:
            break

        _log(f"Sleeping {args.interval} min...")
        for _ in range(args.interval * 60):
            if _shutdown_requested:
                break
            time.sleep(1)

    _log("Monitor stopped.")


if __name__ == "__main__":
    main()
