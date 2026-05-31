"""
tests/test_schedule_daemon.py - Tests for the fixed-interval Perfect Game daemon.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from perfect_game.schedule_daemon import ScheduleDaemon
from shared.config import HOT_POLL_INTERVAL_MINUTES, POLL_INTERVAL_MINUTES


@patch("perfect_game.schedule_daemon.should_poll_now")
@patch("perfect_game.schedule_daemon.run_check")
def test_daemon_poll_uses_baseline_interval_when_polling(mock_run, mock_should_poll):
    mock_run.return_value = [{"Date": "Apr 26", "Type": "Upcoming"}]
    mock_should_poll.return_value = MagicMock(
        should_poll=True, next_poll_at=None, interval_minutes=POLL_INTERVAL_MINUTES
    )
    daemon = ScheduleDaemon(
        team="Texas Prospects",
        player_id="1646618",
        player_name="Parker",
        to_addr="to@test.com",
        team_url="https://example.test/team",
    )

    daemon._run_check()

    assert daemon.current_interval == POLL_INTERVAL_MINUTES
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["team_url"] == "https://example.test/team"


@patch("perfect_game.schedule_daemon.should_poll_now")
@patch("perfect_game.schedule_daemon.run_check")
def test_daemon_speeds_up_inside_hot_window(mock_run, mock_should_poll):
    mock_run.return_value = [{"Date": "Apr 26", "Type": "Upcoming"}]
    mock_should_poll.return_value = MagicMock(
        should_poll=True, next_poll_at=None, interval_minutes=HOT_POLL_INTERVAL_MINUTES
    )
    daemon = ScheduleDaemon(
        team="Texas Prospects",
        player_id="1646618",
        player_name="Parker",
        to_addr="to@test.com",
        team_url="https://example.test/team",
    )

    daemon._run_check()

    assert daemon.current_interval == HOT_POLL_INTERVAL_MINUTES


@patch("perfect_game.schedule_daemon.datetime")
@patch("perfect_game.schedule_daemon.should_poll_now")
@patch("perfect_game.schedule_daemon.run_check")
def test_daemon_extends_interval_until_next_poll(mock_run, mock_should_poll, mock_datetime):
    mock_datetime.now.return_value = datetime(2026, 4, 25, 9, 0)
    mock_run.return_value = []
    mock_should_poll.return_value = MagicMock(
        should_poll=False,
        next_poll_at=datetime(2026, 4, 30, 0, 0),
    )
    daemon = ScheduleDaemon(
        team="D1 Athletics",
        player_id="1646618",
        player_name="Parker",
        to_addr="to@test.com",
    )

    daemon._run_check()

    assert daemon.current_interval > POLL_INTERVAL_MINUTES
