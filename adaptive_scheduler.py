"""
adaptive_scheduler.py - Long-running daemon that polls Perfect Game on an
adaptive interval, speeding up near game time and slowing down otherwise.

Uses APScheduler to manage the polling job.  After each scrape cycle the
interval is recalculated from the next-closest game time.

Usage:
    python adaptive_scheduler.py --team "Your Team Name" --player_id YOUR_PLAYER_ID --to user@example.com
    python adaptive_scheduler.py --dry-run   # log only, don't send email
"""

import argparse
import os
import signal
import sys
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Ensure project dir is on the path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from config import (
    GAME_DAYS,
    INTERVAL_DEFAULT,
    INTERVAL_GAME_3_DAYS,
    INTERVAL_GAME_7_DAYS,
    INTERVAL_GAME_NOW,
    INTERVAL_GAME_TODAY,
    INTERVAL_GAME_TOMORROW,
    INTERVAL_MAX,
    INTERVAL_WEEKDAY_MIN,
    PID_FILE,
)


# ---------------------------------------------------------------------------
# Adaptive interval calculation
# ---------------------------------------------------------------------------

def calculate_interval(games, now=None):
    """
    Determine the optimal polling interval (in minutes) based on how far
    away the nearest upcoming game is.

    Parameters
    ----------
    games : list[dict]
        Schedule entries, each having at least 'Date', 'Time', and 'Type'.
    now : datetime, optional
        Override current time (for testing).

    Returns
    -------
    int
        Polling interval in minutes.
    """
    if now is None:
        now = datetime.now()

    current_year = now.year
    closest_delta = None

    for game in games:
        if game.get("Type") != "Upcoming":
            continue

        date_str = (game.get("Date") or "").strip()
        time_str = (game.get("Time") or "").strip()

        if not date_str:
            continue

        try:
            # Parse date like "Mar 1"
            game_date = datetime.strptime(f"{date_str} {current_year}", "%b %d %Y")
        except ValueError:
            continue

        # Try to add time component
        if time_str and time_str != "N/A" and time_str != "TBD":
            try:
                # Parse time like "11:30 AM"
                game_time = datetime.strptime(time_str, "%I:%M %p")
                game_dt = game_date.replace(
                    hour=game_time.hour, minute=game_time.minute
                )
            except ValueError:
                game_dt = game_date  # midnight if time unparseable
        else:
            game_dt = game_date  # midnight if no time

        delta = game_dt - now
        if delta.total_seconds() < 0:
            # Game might be in progress — use absolute distance
            delta = abs(delta)
            # If within 2 hours of start, treat as "game now"
            if delta <= timedelta(hours=2):
                return INTERVAL_GAME_NOW

            continue  # past game with no score yet — skip

        if closest_delta is None or delta < closest_delta:
            closest_delta = delta

    if closest_delta is None:
        return INTERVAL_MAX

    hours_away = closest_delta.total_seconds() / 3600

    if hours_away <= 2:
        return INTERVAL_GAME_NOW
    elif hours_away <= 24:
        interval = INTERVAL_GAME_TODAY
    elif hours_away <= 48:
        interval = INTERVAL_GAME_TOMORROW
    elif hours_away <= 72:
        interval = INTERVAL_GAME_3_DAYS
    elif hours_away <= 168:  # 7 days
        interval = INTERVAL_GAME_7_DAYS
    else:
        interval = INTERVAL_MAX

    # Weekday back-off: if today is not a game day and not the evening
    # before a game day, enforce a minimum polling interval so we don't
    # waste requests on days when games never happen.
    today_wd = now.weekday()  # Mon=0 … Sun=6
    eve_of_game_day = any((gd - 1) % 7 == today_wd for gd in GAME_DAYS)
    is_game_day = today_wd in GAME_DAYS

    if not is_game_day and not eve_of_game_day:
        interval = max(interval, INTERVAL_WEEKDAY_MIN)

    return interval


# ---------------------------------------------------------------------------
# PID file management
# ---------------------------------------------------------------------------

def write_pid():
    """Write the current PID to the pid file."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    """Remove the pid file if it exists."""
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def check_existing_instance():
    """Return True if another instance is already running."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # signal 0 = just check if alive
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # Stale PID file
        remove_pid()
        return False


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

class ScheduleDaemon:
    """
    Long-running process that periodically checks Perfect Game for schedule
    changes.  The polling interval adapts automatically based on how close
    the next game is.
    """

    def __init__(self, team, player_id, player_name, to_addr, dry_run=False,
                 log_hours=6):
        self.team = team
        self.player_id = player_id
        self.player_name = player_name
        self.to_addr = to_addr
        self.dry_run = dry_run
        self.log_hours = log_hours
        self.current_interval = INTERVAL_DEFAULT
        self.scheduler = BlockingScheduler()

    # ------ helpers ------

    def _log(self, msg):
        from schedule_monitor import log
        log(msg)

    def _run_check(self):
        """Execute a single scrape + merge + notify cycle (delegates to schedule_monitor)."""
        from schedule_monitor import (
            fetch_team_schedule,
            load_schedule,
            log_section,
            merge_into_schedule,
            save_schedule,
            send_alert,
            build_alert_email,
            trim_old_logs,
        )
        from config import SCHEDULE_FILE

        try:
            trim_old_logs(hours=self.log_hours)
            log_section(f"DAEMON POLL — {datetime.now().strftime('%a %b %d %Y %I:%M %p')}")
            self._log(f"Current interval: {self.current_interval} min")

            # Fetch
            scraped = fetch_team_schedule(self.team, self.player_id)
            if not scraped:
                self._log("No games returned — skipping merge.")
                return

            # Merge
            existing = load_schedule(str(SCHEDULE_FILE))
            merged, new_entries, changed_entries = merge_into_schedule(existing, scraped)
            save_schedule(merged, str(SCHEDULE_FILE))

            # Notify
            if not self.dry_run and (new_entries or changed_entries):
                change_parts = []
                if new_entries:
                    change_parts.append(f"{len(new_entries)} new game(s)")
                if changed_entries:
                    change_parts.append(f"{len(changed_entries)} change(s)")
                summary = ", ".join(change_parts)
                subject = f"⚾ {self.player_name} - Schedule Update: {summary}"
                html = build_alert_email(new_entries, changed_entries,
                                         player_name=self.player_name)
                send_alert(self.to_addr, subject, html)
            elif new_entries or changed_entries:
                self._log("[dry-run] Changes detected but email suppressed.")
            else:
                self._log("No changes detected.")

            # Adapt interval
            new_interval = calculate_interval(merged)
            if new_interval != self.current_interval:
                self._log(
                    f"Interval change: {self.current_interval} → {new_interval} min"
                )
                self.current_interval = new_interval
                self.scheduler.reschedule_job(
                    "poll_job",
                    trigger=IntervalTrigger(minutes=new_interval),
                )

        except Exception as e:
            self._log(f"ERROR in poll cycle: {e}")

    # ------ main loop ------

    def start(self):
        """Start the adaptive polling daemon."""
        if check_existing_instance():
            print("Another instance is already running. Exiting.")
            sys.exit(1)

        write_pid()

        # Graceful shutdown
        def _shutdown(signum, frame):
            self._log(f"Received signal {signum} — shutting down.")
            self.scheduler.shutdown(wait=False)
            remove_pid()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        self._log(f"Daemon started (PID {os.getpid()}).")
        self._log(f"Team: {self.team} | Player: {self.player_name} (ID: {self.player_id})")
        self._log(f"Recipient: {self.to_addr} | Dry-run: {self.dry_run}")
        self._log(f"Starting interval: {self.current_interval} min")

        # Run once immediately on startup
        self._run_check()

        self.scheduler.add_job(
            self._run_check,
            trigger=IntervalTrigger(minutes=self.current_interval),
            id="poll_job",
            name="PerfectGame schedule poll",
            max_instances=1,
        )

        try:
            self.scheduler.start()
        finally:
            remove_pid()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    from dotenv import load_dotenv
    from config import ENV_FILE, DEFAULT_TEAM, DEFAULT_PLAYER_ID, DEFAULT_PLAYER_NAME, LOG_RETENTION_HOURS

    load_dotenv(str(ENV_FILE))

    parser = argparse.ArgumentParser(
        description="Adaptive PerfectGame schedule monitor daemon."
    )
    parser.add_argument("--team", type=str, default=DEFAULT_TEAM,
                        help="Team name filter.")
    parser.add_argument("--player-id", type=str, default=DEFAULT_PLAYER_ID,
                        help="Perfect Game Player ID.")
    parser.add_argument("--player", type=str, default=DEFAULT_PLAYER_NAME,
                        help="Player name for emails.")
    parser.add_argument("--to", type=str, default=None,
                        help="Recipient email(s), comma-separated (defaults to TO_EMAILS or EMAIL_ADDRESS from .env).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log changes but do not send email.")
    parser.add_argument("--log-hours", type=float, default=LOG_RETENTION_HOURS,
                        help="Hours of log history to keep.")
    args = parser.parse_args()

    to_addr = args.to or os.getenv("TO_EMAILS") or os.getenv("EMAIL_ADDRESS")
    if not to_addr:
        print("ERROR: No recipient email. Set TO_EMAILS or EMAIL_ADDRESS in .env or use --to.")
        sys.exit(1)

    daemon = ScheduleDaemon(
        team=args.team,
        player_id=args.player_id,
        player_name=args.player,
        to_addr=to_addr,
        dry_run=args.dry_run,
        log_hours=args.log_hours,
    )
    daemon.start()


if __name__ == "__main__":
    main()
