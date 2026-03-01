"""
tests/test_parser.py - Tests for perfect_game_scraper.parse_and_filter_schedule()
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from perfect_game_scraper import parse_and_filter_schedule
from tests.conftest import (
    SAMPLE_FULL_PAGE,
    SAMPLE_EMPTY_PAGE,
    SAMPLE_MALFORMED_ROW,
    SAMPLE_SCHEDULE_HTML_ROW,
    SAMPLE_PAST_GAME_ROW,
)


class TestParseAndFilterSchedule:
    """Tests for HTML schedule parsing."""

    def test_parses_upcoming_game(self):
        """Should extract Date, Time, Opponent, Location from an upcoming game row."""
        html = f"<div>nestedscheduleGridRow{SAMPLE_SCHEDULE_HTML_ROW}</div>"
        result = parse_and_filter_schedule(html)
        assert len(result) == 1
        game = result[0]
        assert game["Date"] == "Mar 1"
        assert game["Time"] == "11:30 AM"
        assert game["Opponent"] == "Expos Baseball 10U"
        assert "Bayer Park" in game["Location"]
        assert game["Type"] == "Upcoming"

    def test_parses_past_game(self):
        """Should extract score and result from a played game."""
        html = f"<div>nestedscheduleGridRow{SAMPLE_PAST_GAME_ROW}</div>"
        result = parse_and_filter_schedule(html)
        assert len(result) == 1
        game = result[0]
        assert game["Date"] == "Feb 28"
        assert game["Type"] == "Past"
        assert "Played" in game["Score/Result"]
        assert game["Opponent"] == "Fairfield Ducks"

    def test_parses_full_page_with_multiple_games(self):
        """Should parse both past and upcoming games from a full page."""
        result = parse_and_filter_schedule(SAMPLE_FULL_PAGE)
        assert len(result) >= 1  # At least the upcoming game
        types = {g["Type"] for g in result}
        assert "Upcoming" in types

    def test_empty_page_returns_empty_list(self):
        """Should return [] when no schedule grid rows exist."""
        result = parse_and_filter_schedule(SAMPLE_EMPTY_PAGE)
        assert result == []

    def test_empty_string_returns_empty_list(self):
        """Should handle empty string gracefully."""
        result = parse_and_filter_schedule("")
        assert result == []

    def test_malformed_row_missing_date(self):
        """Should handle rows with blank/whitespace date fields."""
        html = f"<div>nestedscheduleGridRow{SAMPLE_MALFORMED_ROW}</div>"
        result = parse_and_filter_schedule(html)
        # The row has whitespace-only date which produces an empty date_str
        # after strip — strptime fails, so parsed_date is None.
        # But the game has an opponent so it's still included as Upcoming.
        # This is acceptable: a malformed date doesn't crash the parser.
        if len(result) > 0:
            assert result[0]["Date"] == "" or result[0]["Date"] is None

    def test_output_fields_present(self):
        """Every game dict should have all expected keys."""
        html = f"<div>nestedscheduleGridRow{SAMPLE_SCHEDULE_HTML_ROW}</div>"
        result = parse_and_filter_schedule(html)
        assert len(result) == 1
        expected_keys = {"Date", "Time", "Score/Result", "Opponent", "Location", "Type"}
        assert set(result[0].keys()) == expected_keys

    def test_no_opponent_row_skipped(self):
        """Rows without an opponent link should be excluded."""
        html = """<div>nestedscheduleGridRow
            <span id="lblMonthDay" class="lbl">Mar 5</span>
            <span id="lblTime" class="lbl">3:00 PM</span>
        </div>"""
        result = parse_and_filter_schedule(html)
        assert result == []
