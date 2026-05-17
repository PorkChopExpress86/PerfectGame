"""
tests/test_notifications.py - Tests for Perfect Game notification helpers.
"""

from unittest.mock import MagicMock, patch

import perfect_game.notifications as notifications


def test_build_alert_email_renders_current_game_values():
    html = notifications.build_alert_email(
        [
            {
                "Date": "Apr 26",
                "Time": "3:00 PM",
                "Opponent": "RBC-RED",
                "Location": "Field 4",
                "Type": "Upcoming",
            }
        ],
        player_name="D1 Athletics",
    )

    assert "D1 Athletics" in html
    assert "RBC-RED" in html
    assert "3:00 PM" in html
    assert "Field 4" in html


def test_send_alert_returns_false_without_credentials():
    notifications.EMAIL_ADDRESS = None
    notifications.EMAIL_APP_PASSWORD = None

    assert notifications.send_alert("to@test.com", "Subject", "<p>body</p>") is False


@patch("perfect_game.notifications.smtplib.SMTP_SSL")
def test_send_alert_sends_to_multiple_recipients(mock_smtp):
    notifications.EMAIL_ADDRESS = "sender@test.com"
    notifications.EMAIL_APP_PASSWORD = "password"
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

    result = notifications.send_alert(
        "one@test.com, two@test.com",
        "Subject",
        "<p>body</p>",
    )

    assert result is True
    mock_server.login.assert_called_once_with("sender@test.com", "password")
    assert mock_server.sendmail.call_args[0][1] == ["one@test.com", "two@test.com"]
