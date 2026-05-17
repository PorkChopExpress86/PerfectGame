#!/usr/bin/env python3
"""
review_notifications.py
A skill script to review game reports and determine if an email notification is required.
It also formats the data context required for rendering an HTML email template.
"""

import json
import logging
import sys
from typing import Dict, Any, List, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class NotificationReviewer:
    """Class to review reports and prep notification data."""

    def __init__(self, report_path: str):
        self.report_path = Path(report_path)
        self.report_data: Dict[str, Any] = {}

    def load_report(self) -> bool:
        """Load the JSON report containing the game schedule and changes."""
        if not self.report_path.exists():
            logging.error(f"Report file '{self.report_path}' not found.")
            return False

        try:
            with open(self.report_path, "r", encoding="utf-8") as f:
                self.report_data = json.load(f)
            return True
        except json.JSONDecodeError:
            logging.error(f"Failed to parse '{self.report_path}' as JSON.")
            return False

    def should_send_notification(self) -> bool:
        """
        Determine if an email notification should be sent based on the report contents.

        Rules for sending:
        1. There are notable changes (e.g. time, location changes).
        2. There are new past game results that haven't been emailed yet.
        3. There are upcoming games in the next 7 days, and no email has been sent recently.
        """
        if not self.report_data:
            return False

        changes = self.report_data.get("notable_changes", [])
        if changes:
            logging.info(f"Found {len(changes)} schedule change(s). Notification required.")
            return True

        past_games = self.report_data.get("past_games", [])
        if past_games:
            logging.info(f"Found {len(past_games)} recent past game(s). Notification required.")
            return True

        upcoming_games = self.report_data.get("upcoming_games", [])
        if upcoming_games:
            # Note: A real system might track when the last standard "upcoming" email was sent.
            logging.info(f"Found {len(upcoming_games)} upcoming game(s). Notification required.")
            return True

        logging.info("No changes, past games, or upcoming games. No notification needed.")
        return False

    def format_email_context(self) -> Dict[str, Any]:
        """
        Prepare the context dictionary required by the notification template.
        """
        return {
            "player_name": self.report_data.get("player_name", "Player"),
            "report_date": self.report_data.get("report_generated_at", "Unknown Date"),
            "changes": self.report_data.get("notable_changes", []),
            "upcoming": self.report_data.get("upcoming_games", []),
            "past": self.report_data.get("past_games", [])
        }


def main():
    # Typically this would accept an argparse argument for the file path
    default_report_path = Path(__file__).parent.parent / "examples" / "report.json"

    reviewer = NotificationReviewer(str(default_report_path))

    logging.info(f"Reviewing notifications based on report: {default_report_path}")

    if not reviewer.load_report():
        sys.exit(1)

    if reviewer.should_send_notification():
        logging.info("Programming notification delivery... Compiling template context.")
        context = reviewer.format_email_context()
        logging.info("Email Template Context Prepared:")
        print(json.dumps(context, indent=2))

        # Following this, an email orchestration script (like email_schedule.py)
        # would inject this `context` into `notification_template.html` and dispatch it.
    else:
        logging.info("Skipping notification delivery.")

if __name__ == "__main__":
    main()
