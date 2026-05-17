"""
config.py - Centralized configuration for the PerfectGame schedule monitor.

All tuneable constants live here so they can be imported by any module and
overridden easily in tests.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = PROJECT_DIR / "team_schedule.json"
NOTIFICATION_HISTORY_FILE = PROJECT_DIR / "notification_history.json"
LOG_FILE = PROJECT_DIR / "monitor.log"
PID_FILE = PROJECT_DIR / "monitor.pid"
ENV_FILE = PROJECT_DIR / ".env"
BACKOFF_FILE = PROJECT_DIR / ".perfectgame_backoff.json"

# ---------------------------------------------------------------------------
# Perfect Game polling
# ---------------------------------------------------------------------------
# Fixed poll interval during the active Perfect Game weekend window.
POLL_INTERVAL_MINUTES = 10

# Days the Perfect Game monitor should actively look for schedules/scores.
POLL_DAYS = [3, 4, 5, 6]  # Thursday through Sunday

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 20  # seconds per HTTP request
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # seconds; doubles each retry
RANDOM_DELAY_MIN = 1.0  # seconds between sequential requests
RANDOM_DELAY_MAX = 4.0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_RETENTION_HOURS = 6

# ---------------------------------------------------------------------------
# Email (read from environment / .env at import time)
# ---------------------------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Defaults (set via .env — never hard-code personal data here)
# ---------------------------------------------------------------------------
DEFAULT_TEAM        = os.getenv("PLAYER_TEAM", "")
DEFAULT_PLAYER_ID   = os.getenv("PLAYER_ID", "")
DEFAULT_PLAYER_NAME = os.getenv("PLAYER_NAME", "")
DEFAULT_TEAM_URL    = os.getenv("TEAM_URL") or os.getenv("PLAYER_TEAM_URL", "")
