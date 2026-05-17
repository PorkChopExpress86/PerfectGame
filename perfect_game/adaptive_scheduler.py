"""Compatibility wrapper for the fixed-interval Perfect Game daemon.

The project previously used adaptive polling. Runtime behavior is now fixed
10-minute Thursday-Sunday polling.
"""

from perfect_game.polling_gate import (
    current_weekend_window,
    has_upcoming_game_in_current_window,
    should_poll_now,
)
from perfect_game.schedule_daemon import ScheduleDaemon, main
from shared.config import POLL_INTERVAL_MINUTES

__all__ = [
    "POLL_INTERVAL_MINUTES",
    "ScheduleDaemon",
    "current_weekend_window",
    "has_upcoming_game_in_current_window",
    "main",
    "should_poll_now",
]


if __name__ == "__main__":
    main()
