"""
history_logger.py - Structured logging of sent notifications.

Appends notification metadata to notification_history.json to keep a
record of what was sent and when.
"""

import json
from datetime import datetime
from shared.config import NOTIFICATION_HISTORY_FILE

def log_notification(source: str, summary: str, details: dict | None = None):
    """
    Append a notification entry to the JSON history file.

    Args:
        source: The monitor that sent the notification (e.g., 'perfect_game', 'usssa_team').
        summary: A human-readable summary of the alert.
        details: Optional dictionary containing specific change details.
    """
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "summary": summary,
        "details": details or {}
    }

    history = []
    if NOTIFICATION_HISTORY_FILE.exists():
        try:
            history = json.loads(NOTIFICATION_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

    history.append(entry)

    # Keep the last 200 notifications to prevent the file from growing indefinitely
    history = history[-200:]

    try:
        NOTIFICATION_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"Warning: Could not write to notification history: {e}")
