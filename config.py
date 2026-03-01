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
PROJECT_DIR = Path(__file__).resolve().parent
SCHEDULE_FILE = PROJECT_DIR / "team_schedule.json"
LOG_FILE = PROJECT_DIR / "monitor.log"
PID_FILE = PROJECT_DIR / "monitor.pid"
ENV_FILE = PROJECT_DIR / ".env"

# ---------------------------------------------------------------------------
# Adaptive polling intervals (minutes)
# ---------------------------------------------------------------------------
# Game happening now (within ±2 hours of start)
INTERVAL_GAME_NOW = 5
# Game today but >2 hours away
INTERVAL_GAME_TODAY = 10
# Game tomorrow
INTERVAL_GAME_TOMORROW = 20
# Game within 3 days
INTERVAL_GAME_3_DAYS = 30
# Game within 7 days
INTERVAL_GAME_7_DAYS = 60
# No game within 7 days (maximum backoff)
INTERVAL_MAX = 120
# Minimum interval on non-game weekdays (Mon-Thu when not eve of game day)
INTERVAL_WEEKDAY_MIN = 60
# Default / starting interval
INTERVAL_DEFAULT = 10

# Days games are played (weekday() values: Mon=0 … Sun=6)
GAME_DAYS = [5, 6]  # Saturday and Sunday

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
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TEAM = "Your Team Name"
DEFAULT_PLAYER_ID = "YOUR_PLAYER_ID"
DEFAULT_PLAYER_NAME = "Your Player Name"
