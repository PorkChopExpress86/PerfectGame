---
name: Review Notifications
description: A skill to review and program email notifications based on game schedule changes and upcoming game reports.
---

# Review Notifications

This skill provides the logical components and templates required to review game schedule reports, identify meaningful changes (e.g., schedule updates, new game scores, or upcoming games), and construct professional email notifications.

## Skill Components

1. **Scripts (`scripts/review_notifications.py`)**
   - Contains the core Python implementation.
   - Parses the JSON report out of a datastore or file.
   - Evaluates defined rules to determine whether an email notification should be sent.
   - Extracts relevant data for the email template.

2. **Examples/Resources (`examples/`)**
   - `report.json`: Example payload illustrating the information structure (player details, newly detected changes, upcoming schedule, and recent past results).
   - `notification_template.html`: A rich, responsive HTML email template demonstrating how to render the notification cleanly across diverse email clients.

## Recommended Workflow

1. A monitoring script (like `schedule_monitor.py`) produces a `report.json` payload outlining what has changed.
2. The `review_notifications.py` skill script consumes the payload, decides if a threshold for notification is met, and prepares the template mapping.
3. An email utility (like `email_schedule.py`) renders `notification_template.html` with the prepared data and dispatches the email.
