"""
tests/test_scraper_integration.py - Integration tests for the scraper with mocked HTTP.

Uses the ``responses`` library to mock HTTP responses from Perfect Game.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import responses
from unittest.mock import patch
from perfect_game_scraper import fetch_team_schedule, parse_and_filter_schedule
from tests.conftest import SAMPLE_PROFILE_HTML, SAMPLE_FULL_PAGE


class TestScraperIntegration:
    """Integration tests with mocked HTTP responses."""

    @responses.activate
    @patch("perfect_game_scraper.random_delay", return_value=0)
    def test_full_fetch_chain(self, mock_delay):
        """Profile → Team Schedule → parsed games."""
        # Mock player profile page
        responses.add(
            responses.GET,
            "https://www.perfectgame.org/Players/Playerprofile.aspx?ID=0000000",
            body=SAMPLE_PROFILE_HTML,
            status=200,
        )
        # Mock team schedule page
        responses.add(
            responses.GET,
            url="https://www.perfectgame.org/PGBA/Team/default.aspx?orgid=90706&orgteamid=284257&team=1074261&Year=2026",
            body=SAMPLE_FULL_PAGE,
            status=200,
        )

        games = fetch_team_schedule("Example Team", "0000000")
        assert len(games) >= 1  # at least the upcoming game
        assert any(g["Opponent"] == "Expos Baseball 10U" for g in games)

    @responses.activate
    @patch("perfect_game_scraper.random_delay", return_value=0)
    def test_retry_on_429(self, mock_delay):
        """Should retry and eventually succeed on 429 rate-limiting."""
        # First request: 429
        responses.add(
            responses.GET,
            "https://www.perfectgame.org/Players/Playerprofile.aspx?ID=0000000",
            status=429,
        )
        # Second request: success
        responses.add(
            responses.GET,
            "https://www.perfectgame.org/Players/Playerprofile.aspx?ID=0000000",
            body=SAMPLE_PROFILE_HTML,
            status=200,
        )
        # Team page
        responses.add(
            responses.GET,
            url="https://www.perfectgame.org/PGBA/Team/default.aspx?orgid=90706&orgteamid=284257&team=1074261&Year=2026",
            body=SAMPLE_FULL_PAGE,
            status=200,
        )

        with patch("perfect_game_scraper.time.sleep"):  # skip real sleeps
            games = fetch_team_schedule("Example Team", "0000000")
        assert len(games) >= 1

    @responses.activate
    @patch("perfect_game_scraper.random_delay", return_value=0)
    def test_graceful_failure_on_timeout(self, mock_delay):
        """Should return empty list on persistent network failure."""
        import requests as req_lib
        responses.add(
            responses.GET,
            "https://www.perfectgame.org/Players/Playerprofile.aspx?ID=0000000",
            body=req_lib.exceptions.ConnectionError("Network unreachable"),
        )

        with patch("perfect_game_scraper.time.sleep"):
            games = fetch_team_schedule("Example Team", "0000000")
        assert games == []

    @responses.activate
    @patch("perfect_game_scraper.random_delay", return_value=0)
    def test_no_team_links_returns_empty(self, mock_delay):
        """Should return [] when profile page has no team links."""
        responses.add(
            responses.GET,
            "https://www.perfectgame.org/Players/Playerprofile.aspx?ID=0000000",
            body="<html><body>No teams here</body></html>",
            status=200,
        )

        games = fetch_team_schedule("Example Team", "0000000")
        assert games == []

    @responses.activate
    @patch("perfect_game_scraper.random_delay", return_value=0)
    def test_server_error_retry_exhaustion(self, mock_delay):
        """Should return [] after exhausting retries on 500 errors."""
        for _ in range(5):
            responses.add(
                responses.GET,
                "https://www.perfectgame.org/Players/Playerprofile.aspx?ID=0000000",
                status=500,
            )

        with patch("perfect_game_scraper.time.sleep"):
            games = fetch_team_schedule("Example Team", "0000000")
        assert games == []
