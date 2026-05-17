# Perfect Game Scraper Documentation

This document describes the architecture, logic, and usage of the Perfect Game scraper located in `perfect_game/perfect_game_scraper.py`.

## Overview

The scraper is designed to extract baseball team schedules from a configured Perfect Game team URL, with player-profile discovery kept as a fallback. It handles the dynamic nature of tournament scheduling, where games are often added late or moved to different dates and brackets.

## Key Features

### 1. Autonomous Discovery
The scraper starts from a player's profile page and follows a discovery chain:
- **Team URL:** Starts from `TEAM_URL` / `PLAYER_TEAM_URL` when configured.
- **Player Profile Fallback:** Finds the link to the team's current season page only when no team URL is configured.
- **Team Page:** Scrapes the primary schedule and identifies tournament event IDs.
- **Tournament Crawling:** Recursively visits "Tournament Schedule" and "Brackets" pages for discovered events.
- **Recursive Depth:** It follows links to other tournament dates (e.g., Saturday to Sunday) to ensure all games are captured even if not linked from the main team page.

### 2. Opponent Normalization
Tournament games often have changing opponent strings as records are updated (e.g., "Team X (3-0-0)" vs "Team X (4-0-0)").
- The scraper strips record strings (e.g., `(W 1-0)`, `(3-0-0)`) to maintain a consistent identity for games.
- This prevents duplicate entries in the schedule and redundant notifications.

### 3. Smart Deduplication
Games are deduplicated based on a composite key: `(Date, Time, Normalized Opponent)`.
- If a game exists in both the team schedule and a tournament bracket, it is merged.
- "Past" games (with scores) are prioritized over "Upcoming" placeholders.

### 4. Anti-Detection & Reliability
- **Rotating Headers:** Uses `shared/browser_profile.py` to rotate User-Agent strings and headers.
- **Adaptive Delays:** Randomizes sleep intervals between requests to simulate human browsing behavior.
- **Retries:** Implements an exponential backoff retry logic for 429 (Rate Limit) and 5xx (Server Error) responses.

## Usage

### Command Line
```bash
# Basic usage
python3 perfect_game/perfect_game_scraper.py --player_id 1646618 --team "D1 Athletics"

# Integration with monitor
python3 perfect_game/schedule_monitor.py --team "D1 Athletics" --team-url "https://www.perfectgame.org/PGBA/Team/default.aspx?..."
```

### Integration
The `fetch_team_schedule` function is the primary entry point:
```python
from perfect_game.perfect_game_scraper import fetch_team_schedule

games = fetch_team_schedule(
    team_name_filter="D1 Athletics",
    player_id="1646618",
    team_url="https://www.perfectgame.org/PGBA/Team/default.aspx?...",
    extra_urls=["https://..."]
)
```

## Maintenance
If Perfect Game changes its website layout:
1. Update CSS selectors in `parse_and_filter_schedule`.
2. Verify regex patterns for `eventID`, `orgteamid`, and `TournamentSchedule.aspx`.
3. Check the `_year_aware_parse` function if date formats change.
