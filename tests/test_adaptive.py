"""
tests/test_adaptive.py - Tests for adaptive_scheduler.calculate_interval()
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from adaptive_scheduler import calculate_interval
from config import (
    INTERVAL_GAME_NOW,
    INTERVAL_GAME_TODAY,
    INTERVAL_GAME_TOMORROW,
    INTERVAL_GAME_3_DAYS,
    INTERVAL_GAME_7_DAYS,
    INTERVAL_MAX,
    INTERVAL_WEEKDAY_MIN,
)


class TestCalculateInterval:
    """Tests for adaptive polling interval calculation."""

    def _make_game(self, date_str, time_str="TBD", game_type="Upcoming"):
        return {
            "Date": date_str,
            "Time": time_str,
            "Type": game_type,
            "Opponent": "Test Opponent",
            "Location": "Test Field",
        }

    def test_game_in_30_minutes(self):
        """Game starting in 30 minutes → fastest interval."""
        now = datetime(2026, 3, 1, 11, 0)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_NOW

    def test_game_in_1_hour(self):
        """Game starting in 1 hour → fastest interval."""
        now = datetime(2026, 3, 1, 10, 30)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_NOW

    def test_game_in_progress(self):
        """Game that started 1 hour ago (likely still playing) → fastest interval."""
        now = datetime(2026, 3, 1, 12, 30)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_NOW

    def test_game_in_8_hours(self):
        """Game today but >2 hours away → game-today interval."""
        now = datetime(2026, 3, 1, 3, 30)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_TODAY

    def test_game_tomorrow(self):
        """Game tomorrow → tomorrow interval."""
        now = datetime(2026, 2, 28, 6, 0)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_TOMORROW

    def test_game_in_3_days(self):
        """Game in ~3 days on a weekday → weekday floor takes precedence."""
        now = datetime(2026, 2, 26, 12, 0)  # Thursday
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        # Thursday is neither a game day nor eve of game day,
        # so weekday floor (60) overrides 3-day interval (30).
        assert result == INTERVAL_WEEKDAY_MIN

    def test_game_in_5_days(self):
        """Game in 5 days → 7-day interval."""
        now = datetime(2026, 2, 24, 12, 0)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_7_DAYS

    def test_no_upcoming_games(self):
        """Only past games → max interval."""
        games = [self._make_game("Feb 28", game_type="Past")]
        now = datetime(2026, 3, 1, 12, 0)
        result = calculate_interval(games, now=now)
        assert result == INTERVAL_MAX

    def test_empty_game_list(self):
        """No games at all → max interval."""
        result = calculate_interval([], now=datetime(2026, 3, 1, 12, 0))
        assert result == INTERVAL_MAX

    def test_game_with_tbd_time(self):
        """Game with TBD time defaults to midnight of game date."""
        now = datetime(2026, 2, 28, 12, 0)
        game = self._make_game("Mar 1", "TBD")
        result = calculate_interval([game], now=now)
        # Mar 1 midnight is 12 hours away → game today interval
        assert result == INTERVAL_GAME_TODAY

    def test_multiple_games_uses_closest(self):
        """With multiple upcoming games, the closest one determines the interval."""
        now = datetime(2026, 3, 1, 10, 0)
        games = [
            self._make_game("Mar 1", "11:30 AM"),   # 1.5 hours away
            self._make_game("Mar 8", "2:00 PM"),     # 7 days away
        ]
        result = calculate_interval(games, now=now)
        assert result == INTERVAL_GAME_NOW

    def test_game_far_away(self):
        """Game more than 7 days away → max interval."""
        now = datetime(2026, 2, 20, 12, 0)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_MAX

    def test_game_exactly_2_hours_away(self):
        """Game exactly 2 hours away → still game-now interval (<=2h)."""
        now = datetime(2026, 3, 1, 9, 30)
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        assert result == INTERVAL_GAME_NOW

    # ── Weekday / weekend awareness ─────────────────────────────

    def test_weekday_floor_on_tuesday(self):
        """On a Tuesday with game 5 days away, weekday floor keeps interval high."""
        now = datetime(2026, 2, 24, 12, 0)  # Tuesday
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        # Proximity gives 7-day interval (60), weekday floor is also 60
        assert result == max(INTERVAL_GAME_7_DAYS, INTERVAL_WEEKDAY_MIN)

    def test_friday_is_eve_of_game_day(self):
        """Friday (eve of Saturday game day) does NOT apply weekday floor."""
        now = datetime(2026, 2, 27, 6, 0)  # Friday
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        # ~53.5 hours away → within 72h = 3-day interval, but no weekday floor
        assert result == INTERVAL_GAME_3_DAYS

    def test_saturday_is_game_day(self):
        """Saturday is a game day — full adaptive speed, no floor."""
        now = datetime(2026, 2, 28, 6, 0)  # Saturday
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        # Game ~29.5h away → within 48h = tomorrow interval (no floor)
        assert result == INTERVAL_GAME_TOMORROW

    def test_sunday_is_game_day(self):
        """Sunday is a game day — no weekday floor applied."""
        now = datetime(2026, 3, 1, 3, 0)  # Sunday
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        # Game in ~8.5 hours → game-today interval
        assert result == INTERVAL_GAME_TODAY

    def test_weekday_floor_overrides_3day_interval(self):
        """On a non-eve weekday, 3-day interval gets clamped to weekday floor."""
        now = datetime(2026, 2, 26, 12, 0)  # Thursday, Mar 1 is ~2.5 days away
        game = self._make_game("Mar 1", "11:30 AM")
        result = calculate_interval([game], now=now)
        # Proximity gives 30 min, weekday floor clamps to 60 min
        assert result == INTERVAL_WEEKDAY_MIN

    def test_game_time_none_handled(self):
        """Game with Time=None (not just missing key) doesn't crash."""
        now = datetime(2026, 2, 28, 12, 0)
        game = {"Date": "Mar 1", "Time": None, "Type": "Upcoming",
                "Opponent": "Test", "Location": "Field"}
        result = calculate_interval([game], now=now)
        # Should parse fine (midnight default) — ~12h away → game-today
        assert result == INTERVAL_GAME_TODAY
