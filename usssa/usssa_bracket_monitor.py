#!/usr/bin/env python3
"""
usssa_bracket_monitor.py - USSSA Tournament Bracket Change Monitor.

Polls the USSSA Game Center bracket page every 5 minutes for the
10u AA division (divisionID=2687372). When the bracket or pool play
content changes, sends an email notification with details about the
D1 Athletics (teamID=3313953).

Uses Playwright (headless Chromium) to render the AngularJS SPA and
intercept the API JSON responses, since the USSSA site does not expose
a clean public API reachable with plain HTTP requests.

Usage:
    .venv/bin/python usssa_bracket_monitor.py
    .venv/bin/python usssa_bracket_monitor.py --interval 3   # check every 3 min
    .venv/bin/python usssa_bracket_monitor.py --once          # single check, no loop

Environment variables (from .env):
    EMAIL_ADDRESS       - Gmail sender address
    EMAIL_APP_PASSWORD  - Gmail app password
    TO_EMAILS           - Comma-separated recipient list
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import signal
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

import requests
from shared.telegram_notifier import send_telegram
from shared.history_logger import log_notification
from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

EMAIL_ADDRESS: str | None = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD: str | None = os.getenv("EMAIL_APP_PASSWORD")
TO_EMAILS: str = os.getenv("TO_EMAILS", EMAIL_ADDRESS or "")

# USSSA event parameters
EVENT_ID = 408703
DIVISION_ID = 2687372  # 10u AA
TEAM_ID = "3313953"
TEAM_NAME = "D1 - Athletics"
AGE = 10
AGE_CLASS = "AA"

# Snapshot persistence — one file per view type
SNAPSHOT_DIR = ROOT_DIR / ".usssa_snapshots"
LOG_FILE = ROOT_DIR / "usssa_monitor.log"

# URLs to monitor: pool play (option=101) and bracket (option=111)
_BASE = (
    "https://usssa.com/baseball/event_gameCenter/"
    f"?eventID={EVENT_ID}&age={AGE}&ageClass={AGE_CLASS}"
    f"&divisionID={DIVISION_ID}&bnp=1&bf=1&isWinner=1"
)
MONITOR_VIEWS: dict[str, str] = {
    "pool_play": _BASE + "&option=101",
    "bracket": _BASE + "&option=111",
}

# Default polling interval in minutes
DEFAULT_INTERVAL_MINUTES = 5

# Graceful shutdown flag
_shutdown_requested = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    """Write a timestamped log line to stdout and the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [usssa-monitor] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Snapshot (hash) helpers
# ---------------------------------------------------------------------------
def _snapshot_path(view_name: str) -> Path:
    """Return the path to the snapshot file for a given view."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    return SNAPSHOT_DIR / f"{view_name}.json"


def _load_snapshot(view_name: str) -> dict[str, Any]:
    """Load the last-known snapshot for a view, or return empty dict."""
    path = _snapshot_path(view_name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_snapshot(view_name: str, data: dict[str, Any]) -> None:
    """Persist the current snapshot data for a view."""
    path = _snapshot_path(view_name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _content_hash(content: str) -> str:
    """Return a SHA-256 hex digest of the content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Bracket HTML parsing
# ---------------------------------------------------------------------------
def _clean_html(raw_html: str) -> str:
    """Strip HTML tags and collapse whitespace for readable text."""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = unescape(text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_team_games(html_content: str) -> list[dict[str, str]]:
    """
    Parse the bracket/pool HTML for games involving the Athletics (teamID=3313953).

    Returns a list of dicts with keys: opponent, time, field, score, result.
    """
    games: list[dict[str, str]] = []
    if TEAM_ID not in html_content:
        return games

    # The bracket HTML is a <table> with rows.  Team links look like:
    #   <a href=http://www.usssa.com/default/teamHome/?teamID=3313953>Team Name</a>
    # Find rows / cells containing our team ID and extract context.
    team_pattern = re.compile(
        r'teamID=' + re.escape(TEAM_ID) + r'[^>]*>([^<]*)</a>',
        re.IGNORECASE,
    )
    team_matches = list(team_pattern.finditer(html_content))

    for match in team_matches:
        team_display_name = match.group(1).strip()
        # Get surrounding context (the table row area)
        start = max(0, match.start() - 500)
        end = min(len(html_content), match.end() + 500)
        context = html_content[start:end]

        game: dict[str, str] = {"team": team_display_name}

        # Extract game time / field info from the context
        time_match = re.search(
            r'(\w{3}\s+\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\s+[AP]M\s+\w+\s*\d*)',
            _clean_html(context),
            re.IGNORECASE,
        )
        if time_match:
            game["time_field"] = time_match.group(1).strip()

        # Extract opponent — any other team link in the same context
        other_teams = re.findall(
            r'teamID=(\d+)[^>]*>([^<]*)</a>',
            context,
            re.IGNORECASE,
        )
        for tid, tname in other_teams:
            if tid != TEAM_ID:
                game["opponent"] = tname.strip()
                break

        # Extract score if present
        score_match = re.search(
            r'<font\s+color=red>([^<]+)</font>',
            context,
            re.IGNORECASE,
        )
        if score_match:
            game["score"] = score_match.group(1).strip()

        games.append(game)

    return games


def _extract_all_games(html_content: str) -> str:
    """Return a human-readable summary of the full bracket content."""
    clean = _clean_html(html_content)
    # Extract meaningful game entries (date/time patterns)
    entries = re.findall(
        r'(\w{3}\s+\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}\s+[AP]M\s+[^\(]+\([A-Z0-9]+)',
        clean,
        re.IGNORECASE,
    )
    return "\n".join(f"  • {e.strip()}" for e in entries) if entries else clean[:500]


# ---------------------------------------------------------------------------
# Playwright fetcher
# ---------------------------------------------------------------------------
def fetch_bracket_content(url: str) -> dict[str, Any] | None:
    """
    Use Playwright headless Chromium to load the USSSA Game Center page
    and intercept the ``getGameCenterContent`` API response.

    Returns the parsed JSON dict, or None on failure.
    """
    # Import here to keep Playwright optional for testing
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log("ERROR: playwright is not installed. Run: pip install playwright")
        return None

    captured: dict[str, Any] = {}

    def _on_response(response: Any) -> None:
        """Intercept the game center API response."""
        try:
            if "getGameCenterContent" in response.url and response.status == 200:
                captured["data"] = response.json()
        except Exception:
            pass

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("response", _on_response)
            _log(f"  Loading {url[:80]}...")
            page.goto(url, timeout=45_000)
            # Wait for the API call to complete
            page.wait_for_timeout(5_000)
            browser.close()
    except Exception as exc:
        _log(f"  Playwright error: {exc}")
        return None

    return captured.get("data")


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def _build_notification_html(
    view_name: str,
    team_games: list[dict[str, str]],
    bracket_summary: str,
    bracket_url: str,
) -> str:
    """Build a rich HTML email for a bracket change notification."""
    team_rows = ""
    if team_games:
        for g in team_games:
            opp = g.get("opponent", "TBD")
            tf = g.get("time_field", "TBD")
            score = g.get("score", "—")
            team_rows += f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">{g.get('team', TEAM_NAME)}</td>
                <td style="padding:8px;border:1px solid #ddd;">{opp}</td>
                <td style="padding:8px;border:1px solid #ddd;">{tf}</td>
                <td style="padding:8px;border:1px solid #ddd;">{score}</td>
            </tr>"""
        team_section = f"""
        <h3 style="color:#2d6a4f;">🏟️ {TEAM_NAME} Games Found</h3>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead>
                <tr style="background-color:#2d6a4f;color:white;">
                    <th style="padding:10px;border:1px solid #ddd;">Team</th>
                    <th style="padding:10px;border:1px solid #ddd;">Opponent</th>
                    <th style="padding:10px;border:1px solid #ddd;">Time / Field</th>
                    <th style="padding:10px;border:1px solid #ddd;">Score</th>
                </tr>
            </thead>
            <tbody>{team_rows}</tbody>
        </table>"""
    else:
        team_section = f"""
        <p style="color:#666;"><em>{TEAM_NAME} (teamID={TEAM_ID}) has not yet
        been placed in the {view_name.replace('_', ' ')} view. This will update
        once seedings are finalized.</em></p>"""

    view_label = view_name.replace("_", " ").title()
    now_str = datetime.now().strftime("%I:%M %p on %B %d, %Y")

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">⚾ USSSA Bracket Update — 10u AA {view_label}</h2>
        <p>The <strong>{view_label}</strong> was updated as of <strong>{now_str}</strong>.</p>

        {team_section}

        <h3 style="color:#555;">📋 Full {view_label} Summary</h3>
        <pre style="background:#f4f4f4;padding:12px;border-radius:6px;font-size:12px;
                    max-height:400px;overflow:auto;white-space:pre-wrap;">
{bracket_summary}
        </pre>

        <p>
            <a href="{bracket_url}"
               style="display:inline-block;padding:10px 20px;background-color:#1a3a5c;
                      color:white;text-decoration:none;border-radius:5px;">
                View Live Bracket
            </a>
        </p>

        <br>
        <p style="font-size:12px;color:#888;">
            Scrap Yard Spring Invitational — Conroe, TX — Mar 28-29<br>
            Powered by USSSA Bracket Monitor
        </p>
    </body>
    </html>
    """


def send_notification(
    view_name: str,
    team_games: list[dict[str, str]],
    bracket_summary: str,
    bracket_url: str,
) -> bool:
    """Send the bracket-change email to all recipients."""
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        _log("ERROR: EMAIL_ADDRESS / EMAIL_APP_PASSWORD not set in .env")
        return False

    recipients = [e.strip() for e in TO_EMAILS.split(",") if e.strip()]
    if not recipients:
        _log("ERROR: No recipients configured (TO_EMAILS in .env)")
        return False

    view_label = view_name.replace("_", " ").title()
    subject = f"⚾ USSSA 10u AA {view_label} Updated — {TEAM_NAME}"
    html_body = _build_notification_html(
        view_name, team_games, bracket_summary, bracket_url
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        _log(f"  Sending email to {recipients}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, recipients, msg.as_string())
        _log("  ✅ Email sent successfully.")
        # Send Telegram notification
        tg_body = f"Bracket updated: {bracket_url}\n" + "\n".join([
            f"⚾ {g.get('time_field', 'TBD')} vs {g.get('opponent', '?')}"
            for g in team_games
        ])
        send_telegram(subject, tg_body)
        log_notification("usssa_bracket", subject)
        return True
    except smtplib.SMTPAuthenticationError:
        _log("  ❌ SMTP authentication failed — check EMAIL_APP_PASSWORD")
        return False
    except Exception as exc:
        _log(f"  ❌ Email send failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Core monitor logic
# ---------------------------------------------------------------------------
def check_for_changes() -> int:
    """
    Check all monitored views for content changes.

    Returns the number of views that changed.
    """
    changes_detected = 0

    for view_name, url in MONITOR_VIEWS.items():
        _log(f"Checking {view_name}...")
        data = fetch_bracket_content(url)
        if data is None:
            _log(f"  ⚠ Failed to fetch {view_name} — will retry next cycle.")
            continue

        html_content: str = data.get("html", "")
        current_hash = _content_hash(html_content)

        snapshot = _load_snapshot(view_name)
        previous_hash = snapshot.get("hash", "")

        if current_hash == previous_hash:
            _log(f"  ✓ No changes in {view_name}.")
            continue

        # --- Change detected! ---
        changes_detected += 1
        is_first_run = previous_hash == ""
        _log(
            f"  {'🆕 First snapshot' if is_first_run else '🔔 CHANGE DETECTED'} "
            f"for {view_name} (hash {current_hash[:12]})"
        )

        # Extract team-specific info
        team_games = _extract_team_games(html_content)
        bracket_summary = _extract_all_games(html_content)

        previous_team_games = snapshot.get("team_games", [])
        previous_summary = snapshot.get("bracket_summary", "")

        team_changed = (team_games != previous_team_games)
        summary_changed = (bracket_summary != previous_summary)

        if team_games:
            _log(f"  Found {len(team_games)} game(s) for {TEAM_NAME}")
            for g in team_games:
                _log(f"    → vs {g.get('opponent', '?')} @ {g.get('time_field', '?')}")

        # Save updated snapshot
        _save_snapshot(view_name, {
            "hash": current_hash,
            "last_checked": datetime.now().isoformat(),
            "html_length": len(html_content),
            "team_games": team_games,
            "bracket_summary": bracket_summary,
            "division_name": data.get("divisionName", ""),
        })

        # Send notification ONLY if something meaningful changed
        # Skip on first run if no team games were found.
        if is_first_run:
            if team_games:
                _log("  First run with team games — sending notification.")
                send_notification(view_name, team_games, bracket_summary, url)
            else:
                _log("  First run, no team games — snapshot captured.")
        elif team_changed or summary_changed:
            _log(f"  Meaningful change detected (team: {team_changed}, summary: {summary_changed}) — sending notification.")
            send_notification(view_name, team_games, bracket_summary, url)
        else:
            _log("  No meaningful change for our team/summary — skipping notification.")

    return changes_detected


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------
def _handle_signal(signum: int, _frame: Any) -> None:
    """Set shutdown flag on SIGINT/SIGTERM for graceful exit."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    _log(f"Received {sig_name} — shutting down after current cycle.")
    _shutdown_requested = True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point: parse args and run the polling loop."""
    parser = argparse.ArgumentParser(
        description="Monitor USSSA tournament bracket for changes."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_MINUTES,
        help=f"Polling interval in minutes (default: {DEFAULT_INTERVAL_MINUTES}).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit (no polling loop).",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _log("=" * 60)
    _log("USSSA Bracket Monitor starting")
    _log(f"  Event:     Scrap Yard Spring Invitational (ID={EVENT_ID})")
    _log(f"  Division:  10u AA (divisionID={DIVISION_ID})")
    _log(f"  Team:      {TEAM_NAME} (teamID={TEAM_ID})")
    _log(f"  Interval:  {args.interval} minutes")
    _log(f"  Recipients: {TO_EMAILS}")
    _log("=" * 60)

    if args.once:
        check_for_changes()
        _log("Single check complete. Exiting.")
        return

    while not _shutdown_requested:
        try:
            check_for_changes()
        except Exception as exc:
            _log(f"Unhandled error: {exc}")

        if _shutdown_requested:
            break

        next_check = datetime.now().strftime("%H:%M:%S")
        _log(f"Sleeping {args.interval} min (next check ~{next_check})...")
        # Sleep in small increments so we can respond to signals quickly
        for _ in range(args.interval * 60):
            if _shutdown_requested:
                break
            time.sleep(1)

    _log("Monitor stopped.")


if __name__ == "__main__":
    main()
