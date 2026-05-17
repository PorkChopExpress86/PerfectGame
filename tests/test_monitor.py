"""
tests/test_monitor.py - End-to-end tests for schedule_monitor.run_check()
"""

import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
import perfect_game.schedule_monitor as schedule_monitor


class TestRunCheck:
    """End-to-end tests for the run_check() cycle."""

    def _setup_env(self):
        """Set up test email credentials."""
        schedule_monitor.EMAIL_ADDRESS = "test@test.com"
        schedule_monitor.EMAIL_APP_PASSWORD = "pass123"

    @patch("perfect_game.schedule_monitor.send_alert", return_value=True)
    @patch("perfect_game.schedule_monitor.fetch_team_schedule")
    @patch("perfect_game.schedule_monitor.save_schedule")
    @patch("perfect_game.schedule_monitor.load_schedule")
    @patch("perfect_game.schedule_monitor.trim_old_logs")
    def test_new_games_trigger_email(self, mock_trim, mock_load, mock_save,
                                      mock_fetch, mock_send):
        """New games should trigger an email alert."""
        self._setup_env()
        mock_load.return_value = []
        mock_fetch.return_value = [
            {"Date": "Mar 5", "Time": "2:00 PM", "Opponent": "Hawks",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]

        result = schedule_monitor.run_check(
            team="Test Team", player_id="123",
            player_name="Test Player", to_addr="test@test.com",
        )

        mock_send.assert_called_once()
        assert len(result) == 1
        assert result[0]["Opponent"] == "Hawks"

    @patch("perfect_game.schedule_monitor.send_alert", return_value=True)
    @patch("perfect_game.schedule_monitor.fetch_team_schedule")
    @patch("perfect_game.schedule_monitor.save_schedule")
    @patch("perfect_game.schedule_monitor.load_schedule")
    @patch("perfect_game.schedule_monitor.trim_old_logs")
    def test_no_changes_no_email(self, mock_trim, mock_load, mock_save,
                                  mock_fetch, mock_send):
        """No changes should result in no email sent."""
        self._setup_env()
        existing = [
            {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]
        mock_load.return_value = existing
        mock_fetch.return_value = existing.copy()

        schedule_monitor.run_check(
            team="Test Team", player_id="123",
            player_name="Test Player", to_addr="test@test.com",
        )

        mock_send.assert_not_called()

    @patch("perfect_game.schedule_monitor.send_alert", return_value=True)
    @patch("perfect_game.schedule_monitor.fetch_team_schedule")
    @patch("perfect_game.schedule_monitor.save_schedule")
    @patch("perfect_game.schedule_monitor.load_schedule")
    @patch("perfect_game.schedule_monitor.trim_old_logs")
    def test_force_sends_email_regardless(self, mock_trim, mock_load, mock_save,
                                           mock_fetch, mock_send):
        """--force should send email even with no changes."""
        self._setup_env()
        existing = [
            {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]
        mock_load.return_value = existing
        mock_fetch.return_value = existing.copy()

        with patch("shared.email_schedule.build_email_body", return_value="<p>Full</p>"):
            schedule_monitor.run_check(
                team="Test Team", player_id="123",
                player_name="Test Player", to_addr="test@test.com",
                force=True,
            )

        mock_send.assert_called_once()

    @patch("perfect_game.schedule_monitor.send_alert", return_value=True)
    @patch("perfect_game.schedule_monitor.fetch_team_schedule")
    @patch("perfect_game.schedule_monitor.save_schedule")
    @patch("perfect_game.schedule_monitor.load_schedule")
    @patch("perfect_game.schedule_monitor.trim_old_logs")
    def test_empty_scrape_keeps_existing(self, mock_trim, mock_load, mock_save,
                                          mock_fetch, mock_send):
        """Empty scrape result should not wipe existing schedule."""
        self._setup_env()
        existing = [
            {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]
        mock_load.return_value = existing
        mock_fetch.return_value = []

        result = schedule_monitor.run_check(
            team="Test Team", player_id="123",
            player_name="Test Player", to_addr="test@test.com",
        )

        # Should return existing schedule unchanged
        mock_save.assert_not_called()  # No merge happens when scrape is empty
        mock_send.assert_not_called()

    @patch("perfect_game.schedule_monitor.clear_backoff")
    @patch("perfect_game.schedule_monitor.should_poll_now")
    def test_poll_window_ignores_stale_persisted_backoff(self, mock_should_poll, mock_clear):
        """Persisted backoff from the old Saturday gate should not skip a poll."""
        mock_should_poll.return_value = MagicMock(should_poll=True)

        decision = schedule_monitor._should_skip_before_fetch([], enforce_poll_window=True)

        assert decision is None
        mock_clear.assert_called_once()
        mock_should_poll.assert_called_once_with([])

    @patch("perfect_game.schedule_monitor.send_alert", return_value=True)
    @patch("perfect_game.schedule_monitor.fetch_team_schedule")
    @patch("perfect_game.schedule_monitor.save_schedule")
    @patch("perfect_game.schedule_monitor.load_schedule")
    @patch("perfect_game.schedule_monitor.trim_old_logs")
    def test_changed_game_triggers_email(self, mock_trim, mock_load, mock_save,
                                          mock_fetch, mock_send):
        """A schedule change should trigger an alert email."""
        self._setup_env()
        existing = [
            {"Date": "Mar 1", "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]
        scraped = [
            {"Date": "Mar 1", "Time": "3:00 PM", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]
        mock_load.return_value = existing
        mock_fetch.return_value = scraped

        schedule_monitor.run_check(
            team="Test Team", player_id="123",
            player_name="Test Player", to_addr="test@test.com",
        )

        mock_send.assert_called_once()
        # Check the subject mentions "change"
        call_args = mock_send.call_args
        assert "change" in call_args[0][1].lower() or "update" in call_args[0][1].lower()

    @patch("perfect_game.schedule_monitor.send_alert", return_value=True)
    @patch("perfect_game.schedule_monitor.fetch_team_schedule")
    @patch("perfect_game.schedule_monitor.save_schedule")
    @patch("perfect_game.schedule_monitor.load_schedule")
    @patch("perfect_game.schedule_monitor.trim_old_logs")
    def test_score_promotion_triggers_email(self, mock_trim, mock_load, mock_save,
                                            mock_fetch, mock_send):
        """A newly posted score should promote the game and notify."""
        self._setup_env()
        date_str = datetime.now().strftime("%b %-d")
        existing = [
            {"Date": date_str, "Time": "11:30 AM", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Upcoming", "Score/Result": "N/A"},
        ]
        scraped = [
            {"Date": date_str, "Time": "N/A", "Opponent": "Expos",
             "Location": "Field 1", "Type": "Past",
             "Score/Result": "Played (W 8-3)"},
        ]
        mock_load.return_value = existing
        mock_fetch.return_value = scraped

        result = schedule_monitor.run_check(
            team="Test Team", player_id="123",
            player_name="Test Player", to_addr="test@test.com",
            enforce_poll_window=False,
        )

        mock_send.assert_called_once()
        assert result[0]["Type"] == "Past"
        assert result[0]["Score/Result"] == "Played (W 8-3)"
