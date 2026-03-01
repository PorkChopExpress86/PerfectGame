"""
tests/test_email_integration.py - Tests for email body generation and send logic.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from email_schedule import build_email_body, filter_upcoming
from schedule_monitor import build_alert_email, send_alert


class TestBuildEmailBody:
    """Tests for email_schedule.build_email_body()."""

    def test_upcoming_only_contains_games(self):
        """Should render a table with game data."""
        games = [
            {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Score/Result": "N/A", "Type": "Upcoming"},
        ]
        html = build_email_body(games)
        assert "Expos" in html
        assert "Mar 1" in html
        assert "11:30 AM" in html
        assert "<table" in html

    def test_full_schedule_with_past_games(self):
        """Should include past game results."""
        games = [
            {"Date": "Feb 28", "Time": "N/A", "Opponent": "Ducks",
             "Location": "Field 3", "Score/Result": "Played (L 19-7)",
             "Type": "Past"},
            {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Score/Result": "N/A", "Type": "Upcoming"},
        ]
        html = build_email_body(games)
        assert "Ducks" in html
        assert "19-7" in html

    def test_empty_games_shows_message(self):
        """Should show 'no upcoming games' for empty list."""
        html = build_email_body([])
        assert "No upcoming games" in html

    def test_custom_player_name(self):
        """Player name should appear in the email."""
        games = [{"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
                   "Location": "F1", "Score/Result": "N/A", "Type": "Upcoming"}]
        html = build_email_body(games, player_name="John Doe")
        assert "John Doe" in html


class TestFilterUpcoming:
    """Tests for email_schedule.filter_upcoming()."""

    def test_filters_only_upcoming(self):
        games = [
            {"Type": "Past", "Opponent": "A"},
            {"Type": "Upcoming", "Opponent": "B"},
            {"Type": "Upcoming", "Opponent": "C"},
        ]
        result = filter_upcoming(games)
        assert len(result) == 2
        assert all(g["Type"] == "Upcoming" for g in result)


class TestBuildAlertEmail:
    """Tests for schedule_monitor.build_alert_email()."""

    def test_new_games_section(self):
        """Alert email should have a 'New Game' section."""
        new = [{"Date": "Mar 5", "Time": "2:00 PM", "Opponent": "Hawks",
                "Location": "Field 1", "Type": "Upcoming"}]
        html = build_alert_email(new, [])
        assert "New Game" in html
        assert "Hawks" in html

    def test_changed_games_section(self):
        """Alert email should show changes with old → new values."""
        old = {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
               "Location": "Field 1", "Score/Result": "N/A"}
        new = {"Date": "Mar 1", "Time": "2:00 PM", "Opponent": "Expos",
               "Location": "Field 1", "Score/Result": "N/A"}
        changed = [{"old": old, "new": new, "fields": ["Time"]}]
        html = build_alert_email([], changed)
        assert "Change" in html
        assert "11:30 AM" in html
        assert "2:00 PM" in html

    def test_empty_changes_no_sections(self):
        """No changes should produce minimal HTML with no table sections."""
        html = build_alert_email([], [])
        assert "New Game" not in html
        assert "Change" not in html


class TestSendAlert:
    """Tests for schedule_monitor.send_alert()."""

    @patch.dict(os.environ, {"EMAIL_ADDRESS": "test@test.com", "EMAIL_APP_PASSWORD": "pass123"})
    @patch("schedule_monitor.smtplib.SMTP_SSL")
    def test_send_calls_smtp(self, mock_smtp_class):
        """Should connect to SMTP and call sendmail."""
        # Reload env vars
        import schedule_monitor
        schedule_monitor.EMAIL_ADDRESS = "test@test.com"
        schedule_monitor.EMAIL_APP_PASSWORD = "pass123"

        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = send_alert("recipient@test.com", "Test Subject", "<p>Hi</p>")
        assert result is True
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    def test_send_fails_without_credentials(self):
        """Should return False if credentials are not set."""
        import schedule_monitor
        schedule_monitor.EMAIL_ADDRESS = None
        schedule_monitor.EMAIL_APP_PASSWORD = None
        result = send_alert("x@test.com", "Subj", "<p>Hi</p>")
        assert result is False
