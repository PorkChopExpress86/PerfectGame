"""
tests/test_email_alerts.py - Tests for all email alert functions.

Covers:
  email_schedule     : send_email()
  usssa_team_monitor : _build_email_html(), send_notification()

schedule_monitor.send_alert() and email_schedule.build_email_body() are
tested separately in test_email_integration.py.
"""

import email as _email
import email.header as _email_header
import smtplib
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import shared.email_schedule as email_schedule
import usssa.usssa_team_monitor as usssa_team_monitor


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _smtp_mock():
    """Return (mock_server, mock_context) for patching smtplib.SMTP_SSL."""
    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_server, mock_ctx


def _decode_subject(raw_message: str) -> str:
    """Parse a raw MIME message and return the decoded Subject header."""
    msg = _email.message_from_string(raw_message)
    parts = _email_header.decode_header(msg["Subject"])
    return "".join(
        p.decode(enc or "utf-8") if isinstance(p, bytes) else p
        for p, enc in parts
    )


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

_UPCOMING = {
    "GameID": 1,
    "Date": "Apr 26",
    "SortDate": "2026-04-26T00:00:00",
    "Time": "10:00 AM",
    "Opponent": "Astros Select",
    "Location": "Field 2",
    "Event": "Spring Invitational",
    "EventID": 408703,
    "Type": "Upcoming",
}

_CHANGED = {
    "old": {**_UPCOMING, "Time": "9:00 AM"},
    "new": {**_UPCOMING, "Time": "10:00 AM"},
    "fields": ["Time"],
}

# usssa_team_monitor new-style data (recentGames / bracket format)
_SCORED_GAME = {
    "gameId": 23641417,
    "date": "2026-06-13",
    "opponent": "Fasb 10U Aa",
    "result": "W",
    "wScore": 20,
    "lScore": 5,
}
_BRACKET_CHANGE = ("Pool Play", "Round 1 pool bracket content here")
_ACTIVE_EV = {
    "ID": "2687788",
    "eventId": "408743",
    "name": "Scrap Yard Summer Sizzle",
    "startDate": "2026-06-13T00:00:00",
    "endDate": "2026-06-14T23:59:59",
}
_FUTURE_EV = {
    "ID": "2679811",
    "eventId": "407750",
    "name": "Pensacola Beach World Series",
    "startDate": "2026-07-08T00:00:00",
    "endDate": "2026-07-12T23:59:59",
}

_BRACKET_GAME = {
    "team": "D1 - Athletics",
    "opponent": "Elite Baseball",
    "time_field": "Sat 4/26 10:00 AM Field 3",
    "score": "8-4",
}


# ===========================================================================
# email_schedule.send_email()
# ===========================================================================

class TestSendEmail:
    def setup_method(self):
        email_schedule.EMAIL_ADDRESS = "sender@test.com"
        email_schedule.EMAIL_APP_PASSWORD = "apppass"

    def teardown_method(self):
        email_schedule.EMAIL_ADDRESS = None
        email_schedule.EMAIL_APP_PASSWORD = None

    @patch("shared.email_schedule.smtplib.SMTP_SSL")
    def test_success_returns_true(self, mock_smtp):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        result = email_schedule.send_email("to@test.com", "Subj", "<p>body</p>")

        assert result is True

    @patch("shared.email_schedule.smtplib.SMTP_SSL")
    def test_calls_login_with_credentials(self, mock_smtp):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        email_schedule.send_email("to@test.com", "Subj", "<p>body</p>")

        mock_server.login.assert_called_once_with("sender@test.com", "apppass")

    @patch("shared.email_schedule.smtplib.SMTP_SSL")
    def test_calls_sendmail_with_correct_addresses(self, mock_smtp):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        email_schedule.send_email("to@test.com", "Subj", "<p>body</p>")

        args = mock_server.sendmail.call_args[0]
        assert args[0] == "sender@test.com"
        assert args[1] == "to@test.com"

    @patch("shared.email_schedule.smtplib.SMTP_SSL")
    def test_subject_and_body_in_raw_message(self, mock_smtp):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        email_schedule.send_email("to@test.com", "My Subject", "<p>Hello</p>")

        raw = mock_server.sendmail.call_args[0][2]
        assert "My Subject" in raw
        assert "Hello" in raw

    def test_returns_false_without_credentials(self):
        email_schedule.EMAIL_ADDRESS = None
        email_schedule.EMAIL_APP_PASSWORD = None

        result = email_schedule.send_email("to@test.com", "Subj", "<p>Hi</p>")

        assert result is False

    @patch("shared.email_schedule.smtplib.SMTP_SSL")
    def test_returns_false_on_auth_error(self, mock_smtp):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad creds")

        result = email_schedule.send_email("to@test.com", "Subj", "<p>Hi</p>")

        assert result is False

    @patch("shared.email_schedule.smtplib.SMTP_SSL")
    def test_returns_false_on_smtp_exception(self, mock_smtp):
        mock_smtp.side_effect = Exception("Connection refused")

        result = email_schedule.send_email("to@test.com", "Subj", "<p>Hi</p>")

        assert result is False


# ===========================================================================
# usssa_team_monitor._build_email_html()
# ===========================================================================

class TestUsssaTeamBuildEmailHtml:
    def test_added_games_section_shown(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[_SCORED_GAME], bracket_changes=[], active_event=None, future_events=[]
        )
        assert "New Game Result" in html
        assert "Fasb 10U Aa" in html

    def test_bracket_change_section_shown(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[], bracket_changes=[_BRACKET_CHANGE], active_event=None, future_events=[]
        )
        assert "Pool Play Updated" in html

    def test_all_upcoming_section_shown(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[], bracket_changes=[], active_event=None, future_events=[_FUTURE_EV]
        )
        assert "Upcoming Registered Events" in html
        assert "Pensacola Beach World Series" in html

    def test_team_page_link_present(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[], bracket_changes=[], active_event=None, future_events=[]
        )
        assert "View Team Page" in html
        assert "href" in html

    def test_no_extra_sections_for_empty_input(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[], bracket_changes=[], active_event=None, future_events=[]
        )
        assert "New Game Result" not in html
        assert "Updated" not in html
        assert "Upcoming Registered Events" not in html

    def test_game_details_in_added_section(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[_SCORED_GAME], bracket_changes=[], active_event=None, future_events=[]
        )
        assert "2026-06-13" in html
        assert "20" in html
        assert "5" in html

    def test_changed_fields_label_shown(self):
        html = usssa_team_monitor._build_email_html(
            new_games=[], bracket_changes=[_BRACKET_CHANGE], active_event=_ACTIVE_EV, future_events=[]
        )
        assert "Scrap Yard Summer Sizzle" in html


# ===========================================================================
# usssa_team_monitor.send_notification()
# ===========================================================================

class TestUsssaTeamSendNotification:
    def setup_method(self):
        usssa_team_monitor.EMAIL_ADDRESS = "sender@test.com"
        usssa_team_monitor.EMAIL_APP_PASSWORD = "apppass"
        usssa_team_monitor.TO_EMAILS = "rcpt@test.com"

    def teardown_method(self):
        usssa_team_monitor.EMAIL_ADDRESS = None
        usssa_team_monitor.EMAIL_APP_PASSWORD = None
        usssa_team_monitor.TO_EMAILS = ""

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_success_for_added_games(self, mock_smtp, mock_tg):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        result = usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        assert result is True
        mock_server.sendmail.assert_called_once()

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_success_for_changed_games(self, mock_smtp, mock_tg):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        result = usssa_team_monitor.send_notification(
            new_games=[], bracket_changes=[_BRACKET_CHANGE]
        )

        assert result is True
        mock_server.sendmail.assert_called_once()

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_subject_reports_added_count(self, mock_smtp, mock_tg):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME, _SCORED_GAME], bracket_changes=[]
        )

        subject = _decode_subject(mock_server.sendmail.call_args[0][2])
        assert "2 new result" in subject

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_subject_reports_changed_count(self, mock_smtp, mock_tg):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        usssa_team_monitor.send_notification(
            new_games=[], bracket_changes=[_BRACKET_CHANGE]
        )

        subject = _decode_subject(mock_server.sendmail.call_args[0][2])
        assert "1 bracket update" in subject

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_sends_to_multiple_recipients(self, mock_smtp, mock_tg):
        usssa_team_monitor.TO_EMAILS = "a@test.com, b@test.com"
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        recipients = mock_server.sendmail.call_args[0][1]
        assert "a@test.com" in recipients
        assert "b@test.com" in recipients

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_sends_telegram_on_success(self, mock_smtp, mock_tg):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx

        usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        mock_tg.assert_called_once()

    def test_returns_false_without_credentials(self):
        usssa_team_monitor.EMAIL_ADDRESS = None
        usssa_team_monitor.EMAIL_APP_PASSWORD = None

        result = usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        assert result is False

    def test_returns_false_with_empty_recipients(self):
        usssa_team_monitor.TO_EMAILS = ""

        result = usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        assert result is False

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_returns_false_on_auth_error(self, mock_smtp, mock_tg):
        mock_server, mock_ctx = _smtp_mock()
        mock_smtp.return_value = mock_ctx
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad")

        result = usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        assert result is False

    @patch("usssa.usssa_team_monitor.send_telegram")
    @patch("usssa.usssa_team_monitor.smtplib.SMTP_SSL")
    def test_returns_false_on_smtp_exception(self, mock_smtp, mock_tg):
        mock_smtp.side_effect = Exception("Connection refused")

        result = usssa_team_monitor.send_notification(
            new_games=[_SCORED_GAME], bracket_changes=[]
        )

        assert result is False
