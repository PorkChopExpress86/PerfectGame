# Perfect Game Schedule Monitor

An automated tool to monitor any player's Perfect Game schedule and send email alerts when games are added, changed, or scores are posted.

## Features

- **Adaptive Polling**: Automatically adjusts check frequency based on game proximity — polls every 5 minutes near game time, slows to every 2 hours when no games are upcoming.
- **Multi-Page Scraping**: Monitors both the tournament team page (discovered via the player profile) and an optional PGBA club page configured via `PLAYER_TEAM_URL`, so games posted on either URL are never missed.
- **Anti-Detection**: Rotating User-Agent strings, realistic browser headers (Sec-CH-UA, DNT, etc.), random delays between requests, and exponential backoff on rate-limiting.
- **Smart Merging**: Past games are locked and never modified. Upcoming games are updated when time, location, or opponent changes. New games are appended.
- **Email Alerts**: Sends HTML notifications when schedule changes are detected. Alert and schedule emails include only games within the next 7 days.
- **Clean Logs**: Maintains a retention-limited log file (default 6 hours) for troubleshooting.

## Setup

### 1. Prerequisites
- Python 3.8+
- A Gmail account with an **App Password** (for sending alerts).

### 2. Installation
Clone the repository and set up the virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_APP_PASSWORD=your-app-password
TO_EMAILS=you@example.com,other@example.com   # optional comma-separated recipients

PLAYER_NAME="Your Player Name"
PLAYER_ID="YOUR_PLAYER_ID"
PLAYER_TEAM_URL="https://www.perfectgame.org/PGBA/Team/default.aspx?orgid=...&orgteamid=..."  # optional extra team URL
```

`PLAYER_TEAM_URL` is optional but recommended when the player is registered under a **PGBA club page** that is not linked from the player profile. Both the profile-discovered tournament page and this URL are scraped each poll cycle; games are deduplicated before the merge step.

## Usage

### Automated Setup (Recommended)
The interactive setup script handles everything — installs dependencies, configures the systemd service or cron:
```bash
bash setup.sh
```

### Adaptive Daemon (systemd)
The daemon automatically adjusts its polling interval:

| Game proximity      | Polling interval |
|---------------------|------------------|
| Within 2 hours      | Every 5 minutes  |
| Today (>2h away)    | Every 10 minutes |
| Tomorrow            | Every 20 minutes |
| Within 3 days       | Every 30 minutes |
| Within 7 days       | Every 60 minutes |
| No games within 7d  | Every 120 minutes|

```bash
# Start manually:
python3 adaptive_scheduler.py --team "Your Team Name" --player-id "YOUR_PLAYER_ID"

# With an additional team page (e.g. PGBA club) to monitor:
python3 adaptive_scheduler.py --team "Your Team Name" --player-id "YOUR_PLAYER_ID" \
    --extra-url "https://www.perfectgame.org/PGBA/Team/default.aspx?orgid=...&orgteamid=..."

# Or use systemd (installed via setup.sh):
systemctl --user status perfectgame-monitor
```

The `--extra-url` flag can be repeated to add multiple pages. Any URL set as `PLAYER_TEAM_URL` in `.env` is added automatically without passing it on the command line.

### Run a Single Check
```bash
python3 schedule_monitor.py --player "Your Player Name" --player-id "YOUR_PLAYER_ID" --team "Your Team Name"
```

### Force an Email
To send a summary email regardless of whether changes were detected:
```bash
python3 schedule_monitor.py --force
```

### Legacy Cron (Fixed Interval)
If you prefer cron with a fixed 10-minute interval:
```bash
bash setup.sh   # choose option 2
```

## Running Tests
```bash
source .venv/bin/activate
pytest tests/ -v
```

## Anti-Detection Strategy

Perfect Game may rate-limit or block automated requests. This project uses several techniques to appear as organic browser traffic:

- **Rotating User-Agents**: A pool of 20 realistic Chrome, Firefox, Safari, and Edge strings across Windows, macOS, and Linux.
- **Complete Header Sets**: Includes `Sec-CH-UA`, `Sec-CH-UA-Platform`, `Sec-Fetch-*` headers that match the chosen User-Agent.
- **Random Delays**: 1–4 second pauses between sequential HTTP requests to avoid burst patterns.
- **Exponential Backoff**: On 429 or 5xx responses, retries up to 3 times with doubling delays (5s, 10s, 20s).
- **Session Cookies**: Uses `requests.Session()` to maintain cookies across page navigations, mimicking real browsing.
- **Organic Navigation Path**: Navigates Player Profile → Team Page rather than hitting the schedule URL directly.

## Key Files
| File | Description |
|------|-------------|
| `adaptive_scheduler.py` | Long-running daemon with dynamic polling intervals. |
| `schedule_monitor.py` | Core check cycle: scrape → merge → notify. |
| `perfect_game_scraper.py` | HTTP fetching and HTML parsing with retry logic. |
| `browser_profile.py` | Anti-detection: rotating headers and random delays. |
| `config.py` | Centralized configuration constants. |
| `email_schedule.py` | Email formatting and sending. |
| `get_player_games.py` | Multi-team scraper for a given player. |
| `team_schedule.json` | Persistent schedule state (source of truth). |
| `monitor.log` | Timestamped activity log with auto-trimming. |
| `tests/` | Comprehensive test suite (pytest). |
| `setup.sh` | Interactive setup: systemd or cron. |

## How it Works
1. The script navigates to the **Player Profile** page with randomized browser headers.
2. It dynamically identifies the latest **Team Link** based on the team name filter.
3. After a random delay, it fetches the **Team Schedule** page with fresh headers.
4. If `PLAYER_TEAM_URL` (or `--extra-url`) is configured, it fetches that page too and merges the results, deduplicating by `(Date, Opponent)`.
5. It parses game rows from the HTML and merges them into `team_schedule.json`.
6. If new games were added or upcoming games changed, an HTML alert email is sent listing only games within the next 7 days.
7. The adaptive scheduler recalculates the next polling interval based on the closest upcoming game.
