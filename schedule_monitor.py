#!/usr/bin/env python3
"""
schedule_monitor.py - Monitors Perfect Game for schedule changes.

Fetches the latest schedule from Perfect Game, merges it into team_schedule.json
using these rules:
  - Past games are LOCKED forever (never modified or removed)
  - Upcoming games can be updated if Time, Location, or Opponent changes
  - Upcoming games are promoted to Past if the scraper now shows a score
  - New games that don't exist locally are appended

Sends an email alert when new games are added or upcoming games change.
Designed to be run via cron every 30 minutes.

Requires the .venv virtual environment.

Usage:
    python3 schedule_monitor.py
    python3 schedule_monitor.py --team "Your Team Name" --player "Your Player Name"
    python3 schedule_monitor.py --force
"""

import argparse
import json
import os
import sys
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Add project dir to path so imports work from cron
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

from config import (
    SCHEDULE_FILE as _SCHEDULE_FILE,
    LOG_FILE as _LOG_FILE,
    LOG_RETENTION_HOURS as _LOG_RETENTION_HOURS,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_TIMEOUT,
)
from perfect_game_scraper import fetch_team_schedule

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")

SCHEDULE_FILE = str(_SCHEDULE_FILE)
LOG_FILE = str(_LOG_FILE)
LOG_RETENTION_HOURS = _LOG_RETENTION_HOURS


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(message):
    """Write a timestamped message to the log file and stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log_section(title):
    """Write a visual section divider to the log."""
    bar = "-" * 60
    log(bar)
    log(f"  {title}")
    log(bar)


def trim_old_logs(hours=LOG_RETENTION_HOURS):
    """
    Remove log lines older than `hours` hours from monitor.log.
    Each line must start with a [YYYY-MM-DD HH:MM:SS] timestamp.
    Lines without a recognisable timestamp are kept.
    """
    if not os.path.exists(LOG_FILE):
        return
    cutoff = datetime.now() - timedelta(hours=hours)
    kept = []
    removed = 0
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                # Parse timestamp from [YYYY-MM-DD HH:MM:SS]
                if line.startswith("["):
                    try:
                        ts_str = line[1:20]  # "2026-02-28 21:00:00"
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        if ts < cutoff:
                            removed += 1
                            continue
                    except ValueError:
                        pass  # keep unparseable lines
                kept.append(line)
        with open(LOG_FILE, "w") as f:
            f.writelines(kept)
        if removed:
            log(f"Log trimmed: removed {removed} entr{'y' if removed == 1 else 'ies'} older than {hours}h.")
    except Exception as e:
        log(f"WARNING: Could not trim log file: {e}")


# ---------------------------------------------------------------------------
# Schedule I/O
# ---------------------------------------------------------------------------

def load_schedule(filepath=SCHEDULE_FILE):
    """Load team_schedule.json, returning an empty list if missing or corrupt."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        log(f"WARNING: Could not read {filepath}. Starting with empty schedule.")
        return []


def save_schedule(games, filepath=SCHEDULE_FILE):
    """Save the schedule list to disk as pretty JSON."""
    with open(filepath, "w") as f:
        json.dump(games, f, indent=2)


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _game_key(game):
    """
    Unique identity key for matching games across fetches.
    We match on Date + Opponent since Location/Time may legitimately change.
    """
    return (
        (game.get("Date") or "").strip(),
        (game.get("Opponent") or "").strip(),
    )


def merge_into_schedule(existing, scraped):
    """
    Merge freshly-scraped games into the existing schedule.

    Rules
    -----
    1. Past games in `existing` are NEVER modified or removed.
    2. Upcoming games in `existing` are updated if Time or Location changed.
    3. An Upcoming game is promoted to Past if the scraped version now has
       a Score/Result (i.e. the game has been played).
    4. Games in `scraped` that are not in `existing` at all are appended.
    5. Games in `existing` that are missing from `scraped` are kept as-is.

    Returns
    -------
    (merged_list, new_entries, changed_entries)
      merged_list    – the full updated schedule (list of dicts)
      new_entries    – games added that were not in existing (list of dicts)
      changed_entries – existing upcoming games that had a field change
                        list of {"old": ..., "new": ...}
    """
    existing_by_key = {_game_key(g): g for g in existing}
    scraped_by_key  = {_game_key(g): g for g in scraped}

    new_entries     = []
    changed_entries = []

    # Build the merged result, starting from existing.
    merged = []
    for key, old in existing_by_key.items():
        if old.get("Type") == "Past":
            # --- LOCKED: never touch past games ---
            merged.append(old)
        else:
            # Upcoming game — see if scraper has an update.
            if key in scraped_by_key:
                fresh = scraped_by_key[key]
                updated = dict(old)  # copy

                # Detect field-level changes
                changed_fields = []

                if fresh.get("Time") != old.get("Time"):
                    updated["Time"] = fresh.get("Time")
                    changed_fields.append("Time")

                if fresh.get("Location") != old.get("Location"):
                    updated["Location"] = fresh.get("Location")
                    changed_fields.append("Location")

                if fresh.get("Opponent", "").strip() != old.get("Opponent", "").strip():
                    updated["Opponent"] = fresh.get("Opponent")
                    changed_fields.append("Opponent")

                # Promote to Past if the scraped game now has a result
                if fresh.get("Type") == "Past":
                    updated["Type"] = "Past"
                    updated["Score/Result"] = fresh.get("Score/Result", "N/A")
                    updated["Time"] = "N/A"
                    changed_fields.append("Result")

                if changed_fields:
                    changed_entries.append({"old": old, "new": updated,
                                            "fields": changed_fields})
                merged.append(updated)
            else:
                # Scraper didn't return this game — keep it unchanged.
                merged.append(old)

    # Append scraped games that don't exist in existing at all.
    for key, fresh in scraped_by_key.items():
        if key not in existing_by_key:
            merged.append(fresh)
            new_entries.append(fresh)

    # Sort: Past games first (by original insertion order preserved implicitly)
    # then Upcoming, then by Date string for readability.
    def sort_key(g):
        type_order = 0 if g.get("Type") == "Past" else 1
        return (type_order, g.get("Date", ""))

    merged.sort(key=sort_key)

    return merged, new_entries, changed_entries


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def build_alert_email(new_games, changed_games, player_name="Your Player Name"):
    """Build an HTML email summarising schedule changes."""
    sections = []

    if new_games:
        rows = ""
        for g in new_games:
            rows += f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">{g.get('Date', 'TBD')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{g.get('Time', 'TBD')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{g.get('Opponent', '?')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{g.get('Location', 'TBD')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{g.get('Type', '')}</td>
            </tr>"""

        sections.append(f"""
        <h3 style="color:#2e7d32;">🆕 New Game(s) Added</h3>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead>
                <tr style="background-color:#2e7d32;color:white;">
                    <th style="padding:10px;border:1px solid #ddd;">Date</th>
                    <th style="padding:10px;border:1px solid #ddd;">Time</th>
                    <th style="padding:10px;border:1px solid #ddd;">Opponent</th>
                    <th style="padding:10px;border:1px solid #ddd;">Location</th>
                    <th style="padding:10px;border:1px solid #ddd;">Type</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>""")

    if changed_games:
        rows = ""
        for c in changed_games:
            old, new, fields = c["old"], c["new"], c["fields"]

            def diff_cell(field, old_val, new_val):
                if field in fields:
                    return f"{old_val or 'N/A'} → {new_val or 'N/A'}"
                return new_val or "N/A"

            time_str   = diff_cell("Time",     old.get("Time"),     new.get("Time"))
            loc_str    = diff_cell("Location",  old.get("Location"), new.get("Location"))
            result_str = diff_cell("Result",    old.get("Score/Result"), new.get("Score/Result"))
            opp_str    = diff_cell("Opponent",  old.get("Opponent"), new.get("Opponent"))

            rows += f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">{new.get('Date', 'TBD')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{opp_str}</td>
                <td style="padding:8px;border:1px solid #ddd;color:#d84315;"><b>{time_str}</b></td>
                <td style="padding:8px;border:1px solid #ddd;color:#d84315;"><b>{loc_str}</b></td>
                <td style="padding:8px;border:1px solid #ddd;color:#d84315;"><b>{result_str}</b></td>
            </tr>"""

        sections.append(f"""
        <h3 style="color:#d84315;">🔄 Schedule Change(s)</h3>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead>
                <tr style="background-color:#d84315;color:white;">
                    <th style="padding:10px;border:1px solid #ddd;">Date</th>
                    <th style="padding:10px;border:1px solid #ddd;">Opponent</th>
                    <th style="padding:10px;border:1px solid #ddd;">Time</th>
                    <th style="padding:10px;border:1px solid #ddd;">Location</th>
                    <th style="padding:10px;border:1px solid #ddd;">Score/Status</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>""")

    body = "\n".join(sections)
    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">⚾ Schedule Alert for {player_name}</h2>
        {body}
        <br>
        <p style="font-size:12px;color:#888;">
            Checked at {datetime.now().strftime('%b %d, %Y %I:%M %p')} — Perfect Game Monitor
        </p>
    </body>
    </html>
    """
    return html


def send_alert(to_addr, subject, html_body):
    """Send an alert email via Gmail SMTP."""
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        log("ERROR: Email credentials not configured in .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, [to_addr], msg.as_string())
        log(f"✅ Alert email sent to {to_addr}")
        return True
    except smtplib.SMTPResponseException as e:
        # Code 235 = auth OK; treat 2xx as success
        if 200 <= e.smtp_code < 300:
            log(f"✅ Alert email sent to {to_addr}")
            return True
        log(f"❌ Failed to send alert: SMTP {e.smtp_code} - {e.smtp_error}")
        return False
    except Exception as e:
        log(f"❌ Failed to send alert: {e}")
        return False


# ---------------------------------------------------------------------------
# Core check cycle (used by both CLI and daemon)
# ---------------------------------------------------------------------------

def run_check(team, player_id, player_name, to_addr, force=False, log_hours=LOG_RETENTION_HOURS):
    """
    Execute one full scrape → merge → notify cycle.

    Returns
    -------
    list
        The merged game list (for interval calculation by the daemon).
    """
    trim_old_logs(hours=log_hours)

    run_start = datetime.now()
    log_section(f"RUN START — {run_start.strftime('%a %b %d %Y %I:%M %p')}")
    log(f"Team:    {team}")
    log(f"Player:  {player_name} (ID: {player_id})")
    log(f"Log retention: {log_hours}h")

    # --- Fetch latest from Perfect Game ---
    log_section("Fetching schedule from Perfect Game")
    log(f"Searching for player {player_id}'s team: '{team}'...")
    fetch_start = datetime.now()
    scraped_games = fetch_team_schedule(team, player_id)
    fetch_elapsed = (datetime.now() - fetch_start).total_seconds()
    log(f"Fetch complete in {fetch_elapsed:.1f}s.")

    if not scraped_games:
        log("No games returned from Perfect Game. Site may be blocking or no games are scheduled.")
        log("Existing team_schedule.json is left unchanged.")
        log_section("RUN END — no data")
        return load_schedule()

    log(f"Scraped {len(scraped_games)} game(s):")
    for g in scraped_games:
        log(f"  [{g.get('Type','?'):8s}] {g.get('Date','?'):6s} vs {g.get('Opponent','?')} @ {g.get('Location','?')}")

    # --- Load existing schedule (source of truth) ---
    log_section("Loading existing schedule")
    existing_games = load_schedule()
    past_count     = sum(1 for g in existing_games if g.get("Type") == "Past")
    upcoming_count = len(existing_games) - past_count
    log(f"Loaded {len(existing_games)} game(s): {past_count} past (locked), {upcoming_count} upcoming.")

    # --- Merge scraped into existing ---
    log_section("Merging into team_schedule.json")
    merged, new_entries, changed_entries = merge_into_schedule(existing_games, scraped_games)
    log(f"Merge result: {len(merged)} total game(s).")

    if new_entries:
        log(f"  New game(s) added: {len(new_entries)}")
        for g in new_entries:
            log(f"    [NEW]     {g.get('Date')} vs {g.get('Opponent')} @ {g.get('Location')}")
    if changed_entries:
        log(f"  Changed game(s): {len(changed_entries)}")
        for c in changed_entries:
            log(f"    [CHANGED] {c['new'].get('Date')} vs {c['new'].get('Opponent')} — {c['fields']}")
    if not new_entries and not changed_entries:
        log("  No changes detected.")

    save_schedule(merged)
    log(f"Saved {len(merged)} game(s) to {SCHEDULE_FILE}.")

    # --- Email ---
    log_section("Email")
    if not new_entries and not changed_entries:
        if force:
            log("--force flag set — sending full schedule email.")
            from email_schedule import build_email_body
            html    = build_email_body(merged, player_name=player_name)
            subject = f"⚾ {player_name} - Game Schedule"
            send_alert(to_addr, subject, html)
        else:
            log("No changes — no email sent.")
    else:
        change_parts = []
        if new_entries:
            change_parts.append(f"{len(new_entries)} new game(s)")
        if changed_entries:
            change_parts.append(f"{len(changed_entries)} change(s)")
        summary = ", ".join(change_parts)
        subject = f"⚾ {player_name} - Schedule Update: {summary}"
        html    = build_alert_email(new_entries, changed_entries, player_name=player_name)
        send_alert(to_addr, subject, html)

    elapsed = (datetime.now() - run_start).total_seconds()
    log_section(f"RUN END — completed in {elapsed:.1f}s")
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Monitor PG schedule for changes.")
    parser.add_argument(
        "--team", type=str, default="Your Team Name",
        help="Team name to search for on Perfect Game."
    )
    parser.add_argument(
        "--player", type=str, default="Your Player Name",
        help="Player name for the email subject."
    )
    parser.add_argument(
        "--player-id", type=str, default="YOUR_PLAYER_ID",
        help="Perfect Game Player ID to monitor."
    )
    parser.add_argument(
        "--to", type=str, default=None,
        help="Recipient email (defaults to EMAIL_ADDRESS from .env)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Send email even if no changes detected."
    )
    parser.add_argument(
        "--log-hours", type=float, default=LOG_RETENTION_HOURS,
        help=f"Hours of log history to keep (default: {LOG_RETENTION_HOURS})."
    )
    args = parser.parse_args()

    to_addr = args.to or EMAIL_ADDRESS
    if not to_addr:
        log("ERROR: No recipient email configured.")
        return

    run_check(
        team=args.team,
        player_id=args.player_id,
        player_name=args.player,
        to_addr=to_addr,
        force=args.force,
        log_hours=args.log_hours,
    )


if __name__ == "__main__":
    main()
