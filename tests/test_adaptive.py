"""
tests/test_adaptive.py - Compatibility tests for fixed polling gate exports.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from perfect_game.adaptive_scheduler import (
    POLL_INTERVAL_MINUTES,
    current_weekend_window,
    has_upcoming_game_in_current_window,
    should_poll_now,
)


class TestWeekendPollingGate:
    """Tests for fixed Thu-Sun polling."""

    def _make_game(self, date_str, time_str="TBD", game_type="Upcoming"):
        return {
            "Date": date_str,
            "Time": time_str,
            "Type": game_type,
            "Opponent": "Test Opponent",
            "Location": "Test Field",
        }

    def test_thursday_uses_fixed_20_minute_polling(self):
        now = datetime(2026, 4, 23, 8, 0)  # Thursday
        decision = should_poll_now([], now=now)
        assert decision.should_poll is True
        assert decision.interval_minutes == POLL_INTERVAL_MINUTES

    def test_monday_skips_until_next_thursday(self):
        now = datetime(2026, 4, 27, 8, 0)  # Monday
        decision = should_poll_now([], now=now)
        assert decision.should_poll is False
        assert decision.next_poll_at == datetime(2026, 4, 30, 0, 0)

    def test_saturday_before_9_continues_when_no_games_detected(self):
        now = datetime(2026, 4, 25, 8, 59)  # Saturday
        decision = should_poll_now([], now=now)
        assert decision.should_poll is True

    def test_saturday_9_without_upcoming_games_continues_polling(self):
        now = datetime(2026, 4, 25, 9, 0)  # Saturday
        decision = should_poll_now([], now=now)
        assert decision.should_poll is True
        assert decision.next_poll_at is None

    def test_saturday_9_with_current_window_game_continues(self):
        now = datetime(2026, 4, 25, 9, 0)  # Saturday
        decision = should_poll_now([self._make_game("Apr 26", "3:00 PM")], now=now)
        assert decision.should_poll is True

    def test_sunday_without_upcoming_games_continues_polling(self):
        now = datetime(2026, 4, 26, 9, 0)  # Sunday
        decision = should_poll_now([], now=now)
        assert decision.should_poll is True
        assert decision.next_poll_at is None

    def test_current_window_excludes_next_week_games(self):
        now = datetime(2026, 4, 25, 9, 0)  # Saturday
        assert has_upcoming_game_in_current_window(
            [self._make_game("May 2", "3:00 PM")],
            now=now,
        ) is False

    def test_current_window_bounds_are_thursday_to_sunday(self):
        now = datetime(2026, 4, 25, 12, 0)  # Saturday
        start, end = current_weekend_window(now)
        assert start == datetime(2026, 4, 23, 0, 0)
        assert end == datetime(2026, 4, 26, 23, 59, 59, 999999)
