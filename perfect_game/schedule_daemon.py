"""Fixed-interval daemon for the Perfect Game schedule monitor."""

import argparse
import os
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from perfect_game.polling_gate import should_poll_now
from perfect_game.schedule_monitor import log, run_check
from shared.config import (
    DEFAULT_PLAYER_ID,
    DEFAULT_PLAYER_NAME,
    DEFAULT_TEAM,
    DEFAULT_TEAM_URL,
    ENV_FILE,
    LOG_RETENTION_HOURS,
    PID_FILE,
    POLL_INTERVAL_MINUTES,
)


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def check_existing_instance():
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        remove_pid()
        return False


class ScheduleDaemon:
    """Run Perfect Game checks on a fixed interval during active poll days."""

    def __init__(self, team, player_id, player_name, to_addr, dry_run=False,
                 log_hours=6, extra_urls=None, team_url=None):
        self.team = team
        self.player_id = player_id
        self.player_name = player_name
        self.to_addr = to_addr
        self.dry_run = dry_run
        self.log_hours = log_hours
        self.extra_urls = extra_urls or []
        self.team_url = team_url
        self.current_interval = POLL_INTERVAL_MINUTES
        self.scheduler = BlockingScheduler()

    def _log(self, msg):
        log(msg)

    def _run_check(self):
        try:
            self._log(f"Current interval: {self.current_interval} min")
            merged = run_check(
                team=self.team,
                player_id=self.player_id,
                player_name=self.player_name,
                to_addr=self.to_addr,
                force=False,
                log_hours=self.log_hours,
                extra_urls=self.extra_urls or None,
                team_url=self.team_url,
                dry_run=self.dry_run,
            )

            decision = should_poll_now(merged)
            new_interval = decision.interval_minutes
            if not decision.should_poll and decision.next_poll_at:
                seconds = max(0, (decision.next_poll_at - datetime.now()).total_seconds())
                new_interval = max(POLL_INTERVAL_MINUTES, int(seconds // 60) or 1)

            if new_interval != self.current_interval:
                self._log(f"Interval change: {self.current_interval} -> {new_interval} min")
                self.current_interval = new_interval
                try:
                    self.scheduler.reschedule_job(
                        "poll_job",
                        trigger=IntervalTrigger(minutes=new_interval),
                    )
                except Exception:
                    pass
        except Exception as e:
            self._log(f"ERROR in poll cycle: {e}")

    def start(self):
        if check_existing_instance():
            print("Another instance is already running. Exiting.")
            sys.exit(1)

        write_pid()

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


def main():
    parser = argparse.ArgumentParser(description="PerfectGame schedule monitor daemon.")
    parser.add_argument("--team", type=str, default=DEFAULT_TEAM, help="Team name filter.")
    parser.add_argument("--player-id", type=str, default=DEFAULT_PLAYER_ID,
                        help="Perfect Game Player ID.")
    parser.add_argument("--player", type=str, default=DEFAULT_PLAYER_NAME,
                        help="Player name for emails.")
    parser.add_argument("--to", type=str, default=None,
                        help="Recipient email(s), comma-separated.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log changes but do not send email.")
    parser.add_argument("--log-hours", type=float, default=LOG_RETENTION_HOURS,
                        help="Hours of log history to keep.")
    parser.add_argument("--extra-url", type=str, action="append", dest="extra_urls",
                        help="Additional tournament URL to scrape.")
    parser.add_argument("--team-url", type=str, default=DEFAULT_TEAM_URL,
                        help="Perfect Game team schedule URL.")
    args = parser.parse_args()

    to_addr = args.to or os.getenv("TO_EMAILS") or os.getenv("EMAIL_ADDRESS")
    if not to_addr:
        print("ERROR: No recipient email. Set TO_EMAILS or EMAIL_ADDRESS in .env or use --to.")
        sys.exit(1)

    ScheduleDaemon(
        team=args.team,
        player_id=args.player_id,
        player_name=args.player,
        to_addr=to_addr,
        dry_run=args.dry_run,
        log_hours=args.log_hours,
        extra_urls=list(args.extra_urls or []),
        team_url=args.team_url,
    ).start()


if __name__ == "__main__":
    main()
