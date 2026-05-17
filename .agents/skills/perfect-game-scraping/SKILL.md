---
name: perfect-game-scraping
description: Specialized workflows for autonomously scraping baseball player schedules, team rosters, and tournament brackets from Perfect Game (perfectgame.org). Use when needing to update schedules, discover new games, or handle complex tournament date recursion and opponent normalization.
---

# Perfect Game Scraping

This skill provides a high-reliability workflow for extracting data from Perfect Game.

## Core Scraper
The primary engine is located at: `perfect_game/perfect_game_scraper.py`.

### Capabilities:
- **Player-to-Team Resolution:** Finds the correct team season page from a player profile.
- **Tournament Crawling:** Automatically follows links to multiple tournament dates and brackets.
- **Data Normalization:** Strips win/loss records from opponent names to prevent duplication.
- **Reliability:** Handles 429 Rate Limits and site-specific timeout issues.

## Workflows

### 1. Update Full Schedule
To refresh a player's complete schedule:
1. Run `python3 perfect_game/schedule_monitor.py --player_id <ID> --player "<Name>"`.
2. This uses the scraper, merges results into `team_schedule.json`, and sends notifications if changes occur.

### 2. Deep Tournament Discovery
If a game is suspected to be missing from the team page (common on Sunday mornings):
1. Use `fetch_team_schedule` with the `extra_urls` parameter.
2. Provide the tournament's Saturday schedule URL; the scraper will recursively find the Sunday bracket.

### 3. Debugging Scraper Issues
If the scraper fails to find games:
1. Check `perfect_game/SCRAPING.md` for current CSS selector logic.
2. Verify the player ID is correct by visiting the profile in a browser.
3. Check `monitor.log` for HTTP 403 or 429 errors indicating bot detection.

## Implementation Details
For detailed logic on how the scraper handles recursion and normalization, see [SCRAPING.md](../perfect_game/SCRAPING.md).
