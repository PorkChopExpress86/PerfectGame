"""
tests/test_adaptive.py - Compatibility tests for fixed polling gate exports.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from perfect_game.adaptive_scheduler import (
    HOT_POLL_INTERVAL_MINUTES,
    POLL_INTERVAL_MINUTES,
    current_weekend_window,
    has_upcoming_game_in_current_window,
    in_hot_window,
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


class TestHotPostingWindows:
    """Fast 3-minute polling around the two weekly posting events."""

    # Week anchor: Apr 23 2026 = Thursday .. Apr 27 2026 = Monday.

    def test_thursday_before_noon_is_baseline(self):
        decision = should_poll_now([], now=datetime(2026, 4, 23, 11, 59))
        assert in_hot_window(datetime(2026, 4, 23, 11, 59)) is False
        assert decision.interval_minutes == POLL_INTERVAL_MINUTES

    def test_thursday_noon_starts_hot_window(self):
        now = datetime(2026, 4, 23, 12, 0)  # Thursday noon
        decision = should_poll_now([], now=now)
        assert in_hot_window(now) is True
        assert decision.should_poll is True
        assert decision.interval_minutes == HOT_POLL_INTERVAL_MINUTES

    def test_friday_is_hot_buffer_for_saturday_games(self):
        now = datetime(2026, 4, 24, 15, 0)  # Friday afternoon
        assert in_hot_window(now) is True
        assert should_poll_now([], now=now).interval_minutes == HOT_POLL_INTERVAL_MINUTES

    def test_saturday_midnight_drops_back_to_baseline(self):
        now = datetime(2026, 4, 25, 0, 0)  # Saturday 00:00 (W1 ended)
        assert in_hot_window(now) is False
        assert should_poll_now([], now=now).interval_minutes == POLL_INTERVAL_MINUTES

    def test_saturday_afternoon_is_baseline(self):
        now = datetime(2026, 4, 25, 14, 0)  # Saturday 2 PM, games being played
        assert in_hot_window(now) is False
        assert should_poll_now([], now=now).interval_minutes == POLL_INTERVAL_MINUTES

    def test_saturday_7pm_starts_bracket_window(self):
        now = datetime(2026, 4, 25, 19, 0)  # Saturday 7 PM
        assert in_hot_window(now) is True
        assert should_poll_now([], now=now).interval_minutes == HOT_POLL_INTERVAL_MINUTES

    def test_sunday_daytime_stays_hot_for_next_round_games(self):
        now = datetime(2026, 4, 26, 12, 0)  # Sunday noon
        assert in_hot_window(now) is True
        assert should_poll_now([], now=now).interval_minutes == HOT_POLL_INTERVAL_MINUTES

    def test_sunday_9pm_drops_back_to_baseline(self):
        now = datetime(2026, 4, 26, 21, 0)  # Sunday 9 PM (W2 ended)
        assert in_hot_window(now) is False
        assert should_poll_now([], now=now).interval_minutes == POLL_INTERVAL_MINUTES

    def test_monday_is_outside_polling_entirely(self):
        now = datetime(2026, 4, 27, 13, 0)  # Monday
        decision = should_poll_now([], now=now)
        assert in_hot_window(now) is False
        assert decision.should_poll is False
