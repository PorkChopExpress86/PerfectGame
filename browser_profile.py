"""
browser_profile.py - Anti-detection module for realistic browser-like requests.

Provides rotating User-Agent strings, complete header sets, and random delays
to make HTTP requests appear organic and avoid bot-detection on Perfect Game.
"""

import random
import time

# ---------------------------------------------------------------------------
# User-Agent pool — realistic, modern browser strings across platforms
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

# Languages with quality weights — looks realistic
_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.8",
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,fr;q=0.7",
]

# Referer URLs — pages a real user might come from
_REFERERS = [
    "https://www.perfectgame.org/",
    "https://www.perfectgame.org/Players/Playerprofile.aspx",
    "https://www.perfectgame.org/PGBA/",
    "https://www.google.com/",
    "https://www.google.com/search?q=perfect+game+baseball",
]


def get_random_headers(referer=None):
    """
    Build a complete, randomized header set that mimics a real browser visit.

    Parameters
    ----------
    referer : str, optional
        Override the Referer header.  If None, a random one is chosen.

    Returns
    -------
    dict
        Headers suitable for ``requests.Session.headers.update()``.
    """
    ua = random.choice(_USER_AGENTS)

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Referer": referer or random.choice(_REFERERS),
        "Cache-Control": "max-age=0",
    }

    # Add Sec-CH-UA hints for Chrome/Edge user-agents
    if "Chrome" in ua and "Firefox" not in ua:
        # Extract major version from the UA string
        import re
        chrome_match = re.search(r"Chrome/(\d+)", ua)
        if chrome_match:
            major = chrome_match.group(1)
            if "Edg/" in ua:
                headers["Sec-CH-UA"] = f'"Microsoft Edge";v="{major}", "Chromium";v="{major}", "Not-A.Brand";v="99"'
            else:
                headers["Sec-CH-UA"] = f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not-A.Brand";v="99"'
            headers["Sec-CH-UA-Mobile"] = "?0"
            # Derive platform from UA
            if "Windows" in ua:
                headers["Sec-CH-UA-Platform"] = '"Windows"'
            elif "Macintosh" in ua:
                headers["Sec-CH-UA-Platform"] = '"macOS"'
            elif "Linux" in ua:
                headers["Sec-CH-UA-Platform"] = '"Linux"'
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-Site"] = "same-origin"
            headers["Sec-Fetch-User"] = "?1"

    return headers


def random_delay(min_seconds=None, max_seconds=None):
    """
    Sleep for a random duration to simulate human browsing pace.

    Parameters
    ----------
    min_seconds : float, optional
        Minimum delay (default from config.RANDOM_DELAY_MIN).
    max_seconds : float, optional
        Maximum delay (default from config.RANDOM_DELAY_MAX).
    """
    from config import RANDOM_DELAY_MIN, RANDOM_DELAY_MAX
    lo = min_seconds if min_seconds is not None else RANDOM_DELAY_MIN
    hi = max_seconds if max_seconds is not None else RANDOM_DELAY_MAX
    delay = random.uniform(lo, hi)
    time.sleep(delay)
    return delay
