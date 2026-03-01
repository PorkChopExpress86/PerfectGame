"""
tests/test_browser_profile.py - Tests for browser_profile module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from browser_profile import get_random_headers, random_delay


class TestGetRandomHeaders:
    """Tests for header generation."""

    def test_returns_required_keys(self):
        """All essential browser headers should be present."""
        headers = get_random_headers()
        required = {"User-Agent", "Accept", "Accept-Language", "Accept-Encoding",
                     "Connection", "Upgrade-Insecure-Requests", "DNT", "Referer",
                     "Cache-Control"}
        assert required.issubset(set(headers.keys()))

    def test_user_agent_varies(self):
        """Multiple calls should produce different User-Agent strings (randomness)."""
        agents = {get_random_headers()["User-Agent"] for _ in range(50)}
        assert len(agents) > 1, "UA should vary across calls"

    def test_custom_referer(self):
        """Passing a referer should override the default."""
        headers = get_random_headers(referer="https://example.com")
        assert headers["Referer"] == "https://example.com"

    def test_chrome_ua_has_sec_headers(self):
        """Chrome user-agents should include Sec-CH-UA headers."""
        # Force a Chrome UA by mocking random.choice
        chrome_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        with patch("browser_profile.random.choice", side_effect=[chrome_ua, "en-US,en;q=0.9", "https://www.perfectgame.org/"]):
            headers = get_random_headers()
        assert "Sec-CH-UA" in headers
        assert "Sec-CH-UA-Platform" in headers
        assert '"Windows"' in headers["Sec-CH-UA-Platform"]

    def test_firefox_ua_no_sec_headers(self):
        """Firefox user-agents should NOT include Sec-CH-UA headers."""
        firefox_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        with patch("browser_profile.random.choice", side_effect=[firefox_ua, "en-US,en;q=0.9", "https://www.perfectgame.org/"]):
            headers = get_random_headers()
        assert "Sec-CH-UA" not in headers

    def test_safari_ua_no_sec_headers(self):
        """Safari user-agents should NOT include Sec-CH-UA headers."""
        safari_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
        with patch("browser_profile.random.choice", side_effect=[safari_ua, "en-US,en;q=0.9", "https://www.google.com/"]):
            headers = get_random_headers()
        assert "Sec-CH-UA" not in headers


class TestRandomDelay:
    """Tests for the random delay function."""

    @patch("browser_profile.time.sleep")
    def test_sleeps_within_bounds(self, mock_sleep):
        """random_delay() should call sleep with a value within the specified range."""
        delay = random_delay(min_seconds=1.0, max_seconds=2.0)
        mock_sleep.assert_called_once()
        actual = mock_sleep.call_args[0][0]
        assert 1.0 <= actual <= 2.0

    @patch("browser_profile.time.sleep")
    def test_returns_delay_value(self, mock_sleep):
        """random_delay() should return the delay value."""
        delay = random_delay(min_seconds=0.5, max_seconds=0.5)
        assert delay == 0.5

    @patch("browser_profile.time.sleep")
    def test_uses_config_defaults(self, mock_sleep):
        """When no args given, should use config defaults."""
        delay = random_delay()
        mock_sleep.assert_called_once()
        actual = mock_sleep.call_args[0][0]
        # config defaults: 1.0 to 4.0
        assert 1.0 <= actual <= 4.0
