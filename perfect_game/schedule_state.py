"""Persistence helpers for Perfect Game schedule monitor state."""

import json
import os

from shared.config import BACKOFF_FILE, SCHEDULE_FILE


def load_schedule(filepath=SCHEDULE_FILE):
    """Load a schedule JSON file, returning [] when missing or corrupt."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_schedule(games, filepath=SCHEDULE_FILE):
    """Save the schedule list as pretty JSON."""
    with open(filepath, "w") as f:
        json.dump(games, f, indent=2)


def clear_backoff(filepath=BACKOFF_FILE):
    """Remove a stale backoff marker."""
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass
