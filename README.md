# Perfect Game & USSSA Baseball Monitor

An automated tool to monitor any player's Perfect Game and USSSA schedules. It sends alerts via Email and Telegram when games are added, changed, scores are posted, or bracket progress is detected.

## Features

- **Multi-Platform Support**: Monitors both **Perfect Game (PG)** and **USSSA** schedules simultaneously.
- **Weekend Polling Gates**: Polls Perfect Game Thursday through Sunday, with **fast 3-minute "hot" windows** around the two times new games are posted (Saturday games drop Thursday; Sunday brackets/next-round games drop Saturday evening onward) so they are detected within ~5 minutes. A 10-minute baseline covers the rest of the weekend.
- **Tournament Deep-Scanning**: Automatically follows "Schedule" links on tournament pages to find specific game times and field locations that are often hidden on main team pages.
- **Smart Change Detection**:
    - **PG**: Notifies on changes to Score, Time, or Location.
    - **USSSA**: Filters out noisy HTML changes to only alert when team games or bracket summaries actually change.
- **Score & Bracket Promotion**: Automatically detects when an "Upcoming" game becomes a result and notifies you with the final score. Tracks Sunday bracket progress in real-time.
- **Robust Anti-Detection**: Rotating User-Agents, realistic browser headers, random delays, and exponential backoff.
- **Rich Notifications**:
    - **Telegram**: Concise alerts with direct, masked links to team pages.
    - **Email**: Detailed HTML notifications with a 7-day lookahead.

## Setup

### 1. Prerequisites
- Python 3.11+
- `beautifulsoup4`, `requests`, `python-dotenv`, `APScheduler`

### 2. Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration (.env)
```env
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_APP_PASSWORD=your-app-password
TO_EMAILS=recipient@gmail.com

TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

PLAYER_NAME="Parker Bowden"
PLAYER_ID="1646618"
PLAYER_TEAM="D1 Athletics"
TEAM_URL="https://www.perfectgame.org/..."
# PLAYER_TEAM_URL is still supported for backwards compatibility.
```

## How it Works

### Perfect Game Monitor
1.  Starts from the configured **Team Page** URL when `TEAM_URL` or `PLAYER_TEAM_URL` is set.
2.  Falls back to the **Player Profile** only when no team URL is configured.
3.  Fetches the **Team Page** and searches for any **Tournament Schedule** links for upcoming dates.
4.  Performs a deep-scan of tournament pages to extract precise times, fields, and opponent records.
5.  Merges data into `team_schedule.json`.
6.  If a score is posted or a time/field changes, it triggers an alert.

### USSSA Monitors
-   **Team Monitor**: Polls the USSSA Team Info API for new upcoming games.
-   **Bracket Monitor**: Scans the USSSA Game Center. It maintains a state snapshot and only alerts if your team's specific games or the overall bracket structure changes (preventing redundant alerts from minor site updates).

## Usage

### Systemd User Services (Recommended)
The monitors are currently configured as systemd user units for maximum reliability:
```bash
# Check the Perfect Game daemon
systemctl --user status perfectgame-monitor.service

# Check USSSA timers
systemctl --user list-timers "perfectgame-usssa*"

# View logs
tail -f monitor.log         # Perfect Game logs
tail -f usssa_monitor.log   # USSSA Bracket logs
```

### Manual Run
```bash
# Perfect Game check
python3 perfect_game/schedule_monitor.py --force

# USSSA Team check
python3 usssa/usssa_team_monitor.py --once

# USSSA Bracket check
python3 usssa/usssa_bracket_monitor.py --once
```

## Key Files
| File | Description |
|------|-------------|
| `perfect_game/schedule_daemon.py` | Time-aware PG daemon (3-min hot windows, 10-min baseline). |
| `perfect_game/schedule_monitor.py` | One-shot PG scrape/merge/notify CLI. |
| `perfect_game/perfect_game_scraper.py` | BS4-based scraper for PG pages. |
| `usssa/usssa_team_monitor.py` | USSSA API-based team monitor. |
| `usssa/usssa_bracket_monitor.py` | USSSA HTML-based bracket monitor. |
| `shared/telegram_notifier.py` | Shared utility for Telegram alerts. |
| `team_schedule.json` | Local database for PG games. |

## Tournament Weekend Logic
The system is optimized for tournament weekends. The daemon polls faster (every
3 minutes) during the windows when new games are actually posted, so additions
are caught within ~5 minutes (`HOT_POLL_WINDOWS` in `shared/config.py`):

| Window | When (Central) | Catches |
|--------|----------------|---------|
| Saturday games drop | **Thu 12:00 → Sat 00:00** | Saturday schedule posted "sometime Thursday" (Friday buffer). |
| Brackets + Sunday games | **Sat 19:00 → Sun 21:00** | Sunday bracket posted Saturday evening, plus next-round games if the team advances. |

Outside those windows (Thu morning, Sat daytime, late Sunday) it falls back to a
10-minute baseline; Monday–Wednesday it sleeps until the next Thursday.

- **Saturday Evening**: As brackets are finalized, the Sunday game is detected as a "New Game" and reported within ~5 minutes.
- **Sunday Progress**: If the team wins, the next bracket game is picked up in the next 3-minute cycle.
- **Score Reporting**: Completed games are "promoted" in the local database and sent as a "Schedule Update" featuring the final score.
