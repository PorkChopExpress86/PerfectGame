#!/usr/bin/env python3
"""One-shot Perfect Game schedule check and notification CLI."""

import argparse
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, ".env"))

from perfect_game.notifications import (  # noqa: E402
    build_alert_email,
    is_recent_past_game,
    send_alert,
)
from perfect_game.perfect_game_scraper import fetch_team_schedule  # noqa: E402
from perfect_game.polling_gate import (  # noqa: E402
    has_upcoming_game_in_current_window,
    should_poll_now,
)
from perfect_game.schedule_merge import merge_into_schedule  # noqa: E402
from perfect_game.schedule_state import clear_backoff, load_schedule, save_schedule  # noqa: E402
from shared.config import (  # noqa: E402
    DEFAULT_PLAYER_ID,
    DEFAULT_PLAYER_NAME,
    DEFAULT_TEAM,
    DEFAULT_TEAM_URL,
    LOG_FILE as _LOG_FILE,
    LOG_RETENTION_HOURS,
    SCHEDULE_FILE as _SCHEDULE_FILE,
)
from shared.history_logger import log_notification  # noqa: E402
from shared.telegram_notifier import send_telegram  # noqa: E402

SCHEDULE_FILE = str(_SCHEDULE_FILE)
LOG_FILE = str(_LOG_FILE)


def log(message):
    """Write a timestamped message to stdout and monitor.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_section(title):
    bar = "-" * 60
    log(bar)
    log(f"  {title}")
    log(bar)


def trim_old_logs(hours=LOG_RETENTION_HOURS):
    """Keep only recent timestamped log entries."""
    if not os.path.exists(LOG_FILE):
        return
    cutoff = datetime.now() - timedelta(hours=hours)
    kept = []
    removed = 0
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                if line.startswith("["):
                    try:
                        ts = datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S")
                        if ts < cutoff:
                            removed += 1
                            continue
                    except ValueError:
                        pass
                kept.append(line)
        with open(LOG_FILE, "w") as f:
            f.writelines(kept)
        if removed:
            log(f"Log trimmed: removed {removed} entr{'y' if removed == 1 else 'ies'} older than {hours}h.")
    except OSError as e:
        log(f"WARNING: Could not trim log file: {e}")


def _should_skip_before_fetch(existing_games, enforce_poll_window):
    if not enforce_poll_window:
        return None

    clear_backoff()
    decision = should_poll_now(existing_games)
    if decision.should_poll:
        return None
    return decision


def _record_post_merge_backoff(merged, enforce_poll_window):
    if not enforce_poll_window:
        return

    decision = should_poll_now(merged)
    if not decision.should_poll and decision.next_poll_at:
        return
    if has_upcoming_game_in_current_window(merged):
        clear_backoff()


def _changed_games(changed_entries):
    return [change["new"] for change in changed_entries]


def _alertable_games(new_entries, changed_entries):
    candidates = list(new_entries) + _changed_games(changed_entries)
    return [
        game for game in candidates
        if game.get("Type") != "Past" or is_recent_past_game(game)
    ]


def _send_force_schedule(merged, player_name, to_addr, dry_run):
    from shared.email_schedule import build_email_body

    upcoming_only = [game for game in merged if game.get("Type") == "Upcoming"]
    if not upcoming_only:
        log("No upcoming games to send even with --force.")
        return

    subject = f"⚾ {player_name} - Upcoming Schedule"
    html = build_email_body(upcoming_only, player_name=player_name)
    if dry_run:
        log("[dry-run] Upcoming schedule email suppressed.")
        return

    send_alert(to_addr, subject, html)
    tg_body = "\n".join(
        f"⚾ {game.get('Date')} {game.get('Time', 'TBD')} "
        f"vs {game.get('Opponent', '?')} @ {game.get('Location', 'TBD')}"
        for game in upcoming_only
    )
    send_telegram(subject, tg_body)
    log_notification("perfect_game", f"Upcoming Schedule sent via --force for {player_name}")


def _send_change_alert(alert_games, player_name, to_addr, dry_run, new_entries, changed_entries):
    subject = f"⚾ {player_name} - Schedule Update"
    html = build_alert_email(alert_games, player_name=player_name)
    if dry_run:
        log("[dry-run] Schedule update notifications suppressed.")
        return

    send_alert(to_addr, subject, html)
    tg_body = "\n".join(
        f"⚾ {game.get('Date')} "
        f"{game.get('Score/Result') if game.get('Type') == 'Past' else game.get('Time', 'TBD')} "
        f"vs {game.get('Opponent', '?')} @ {game.get('Location', 'TBD')}"
        for game in alert_games
    )
    send_telegram(subject, tg_body)
    log_notification(
        "perfect_game",
        f"Schedule Update: {len(new_entries)} new, {len(changed_entries)} changed for {player_name}",
    )


def _notify(merged, new_entries, changed_entries, player_name, to_addr, force, dry_run):
    log_section("Email")
    alert_games = _alertable_games(new_entries, changed_entries)

    if alert_games:
        _send_change_alert(alert_games, player_name, to_addr, dry_run, new_entries, changed_entries)
    elif force:
        log("--force flag set — sending upcoming schedule email.")
        _send_force_schedule(merged, player_name, to_addr, dry_run)
    elif new_entries or changed_entries:
        log("Changes were only to past games — no email sent.")
    else:
        log("No changes — no email sent.")


def _log_scraped_games(scraped_games):
    log(f"Scraped {len(scraped_games)} game(s):")
    for game in scraped_games:
        log(
            f"  [{game.get('Type','?'):8s}] {game.get('Date','?'):6s} "
            f"{game.get('Time','?'):8s} vs {game.get('Opponent','?')} "
            f"@ {game.get('Location','?')}"
        )


def run_check(team, player_id, player_name, to_addr, force=False,
              log_hours=LOG_RETENTION_HOURS, extra_urls=None, team_url=None,
              enforce_poll_window=True, dry_run=False):
    """Run one scrape, merge, and notification cycle."""
    trim_old_logs(hours=log_hours)

    run_start = datetime.now()
    log_section(f"RUN START — {run_start.strftime('%a %b %d %Y %I:%M %p')}")
    log(f"Team:    {team}")
    log(f"Player:  {player_name} (ID: {player_id})")
    log(f"Log retention: {log_hours}h")
    if team_url:
        log(f"Team URL: {team_url}")
    if extra_urls:
        log(f"Extra URLs: {extra_urls}")

    existing_games = load_schedule()
    skip_decision = _should_skip_before_fetch(existing_games, enforce_poll_window)
    if skip_decision:
        next_poll = (
            skip_decision.next_poll_at.strftime("%a %b %d %Y %I:%M %p")
            if skip_decision.next_poll_at else "unknown"
        )
        log(f"Skipping Perfect Game poll: {skip_decision.reason}. Next poll: {next_poll}.")
        log_section("RUN END — skipped")
        return existing_games

    log_section("Fetching schedule from Perfect Game")
    log(
        f"Fetching configured team schedule: '{team}'..."
        if team_url else f"Searching for player {player_id}'s team: '{team}'..."
    )
    fetch_start = datetime.now()
    scraped_games = fetch_team_schedule(
        team, player_id, extra_urls=extra_urls, team_url=team_url
    )
    log(f"Fetch complete in {(datetime.now() - fetch_start).total_seconds():.1f}s.")

    if not scraped_games:
        log("No games returned from Perfect Game. Site may be blocking or no games are scheduled.")
        log("Existing team_schedule.json is left unchanged.")
        _record_post_merge_backoff(existing_games, enforce_poll_window)
        log_section("RUN END — no data")
        return existing_games

    _log_scraped_games(scraped_games)

    log_section("Loading existing schedule")
    past_count = sum(1 for game in existing_games if game.get("Type") == "Past")
    log(f"Loaded {len(existing_games)} game(s): {past_count} past (locked), {len(existing_games) - past_count} upcoming.")

    log_section("Merging into team_schedule.json")
    merged, new_entries, changed_entries = merge_into_schedule(existing_games, scraped_games)
    log(f"Merge result: {len(merged)} total game(s).")
    for game in new_entries:
        log(f"    [NEW]     {game.get('Date')} {game.get('Time')} vs {game.get('Opponent')} @ {game.get('Location')}")
    for change in changed_entries:
        log(f"    [CHANGED] {change['new'].get('Date')} vs {change['new'].get('Opponent')} — {change['fields']}")
    if not new_entries and not changed_entries:
        log("  No changes detected.")

    save_schedule(merged)
    log(f"Saved {len(merged)} game(s) to {SCHEDULE_FILE}.")
    _record_post_merge_backoff(merged, enforce_poll_window)
    _notify(merged, new_entries, changed_entries, player_name, to_addr, force, dry_run)

    elapsed = (datetime.now() - run_start).total_seconds()
    log_section(f"RUN END — completed in {elapsed:.1f}s")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Monitor PG schedule for changes.")
    parser.add_argument("--team", type=str, default=DEFAULT_TEAM,
                        help="Team name to search for on Perfect Game.")
    parser.add_argument("--player", type=str, default=DEFAULT_PLAYER_NAME,
                        help="Player name for the email subject.")
    parser.add_argument("--player-id", type=str, default=DEFAULT_PLAYER_ID,
                        help="Perfect Game Player ID to monitor.")
    parser.add_argument("--team-url", type=str, default=DEFAULT_TEAM_URL,
                        help="Perfect Game team schedule URL to monitor directly.")
    parser.add_argument("--to", type=str, default=None,
                        help="Recipient email(s), comma-separated.")
    parser.add_argument("--force", action="store_true",
                        help="Send email even if no changes detected.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run fetch/merge without sending email or Telegram.")
    parser.add_argument("--log-hours", type=float, default=LOG_RETENTION_HOURS,
                        help=f"Hours of log history to keep (default: {LOG_RETENTION_HOURS}).")
    args = parser.parse_args()

    to_addr = args.to or os.getenv("TO_EMAILS") or os.getenv("EMAIL_ADDRESS")
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
        team_url=args.team_url,
        enforce_poll_window=not args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
