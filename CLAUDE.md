# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here
- Read **`MEMORY.md`** (running log of decisions/work) and **`ERRORS.md`** (known pitfalls) before changing anything, and append to them as you go — that's how this repo avoids repeating mistakes.
- `AGENTS.md` holds contribution conventions (style, commit format, testing scope). This file covers commands + architecture; don't duplicate AGENTS.md here.

## Commands
Setup:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
Tests (must run warning-free):
```bash
.venv/bin/python -m pytest -q                          # full suite
.venv/bin/python -m pytest tests/test_adaptive.py -q   # one file
.venv/bin/python -m pytest "tests/test_adaptive.py::TestHotPostingWindows::test_thursday_noon_starts_hot_window" -q  # one test
.venv/bin/python -m compileall perfect_game shared usssa tests   # import/bytecode check
```
Run one scrape/merge/notify cycle by hand:
```bash
.venv/bin/python perfect_game/schedule_monitor.py --dry-run   # fetch+merge, no email/telegram (still writes team_schedule.json)
.venv/bin/python perfect_game/schedule_monitor.py --force     # email the upcoming schedule even with no changes
```
Production is a systemd **user** service:
```bash
systemctl --user restart perfectgame-monitor.service   # REQUIRED after editing code (daemon caches modules at startup)
systemctl --user status  perfectgame-monitor.service
journalctl --user -u perfectgame-monitor.service -f
tail -f monitor.log                                    # application log
bash setup.sh                                          # (re)install the service
```

## Architecture — Perfect Game monitor
One cycle flows through these modules; read them together to understand the whole:

`schedule_daemon.py` → `schedule_monitor.run_check()` → `polling_gate` → `perfect_game_scraper` → `schedule_merge` → `schedule_state` → `notifications` / `shared.email_schedule` / `shared.telegram_notifier` → `shared.history_logger`

- **Two entry points, one core.** `schedule_monitor.run_check()` is the single orchestrator. The long-running `schedule_daemon.py` (APScheduler `BlockingScheduler`) calls it on an interval; the `schedule_monitor.py` CLI calls it once. Put new logic in `run_check`/helpers, not in either entry point.

- **Polling cadence lives in `polling_gate.should_poll_now()`**, not in the daemon. It returns `PollDecision(should_poll, interval_minutes, next_poll_at)`. The daemon reschedules its job to `interval_minutes`; `run_check` uses `should_poll` to skip fetching outside the window. The "hot windows" (3-min polling so new postings are caught within ~5 min), the Thu–Sun gate, and baseline interval are constants in `shared/config.py` (`HOT_POLL_WINDOWS`, `HOT_POLL_INTERVAL_MINUTES`, `POLL_DAYS`, `POLL_INTERVAL_MINUTES`). All times are **local (America/Chicago)** via `datetime.now()`.

- **The scraper does event discovery, not a single-page fetch.** `fetch_team_schedule()` starts at `TEAM_URL` (the org team page), but that page only shows the most-recent *completed* event. The current weekend's games live on per-event `TournamentSchedule.aspx?event=<id>&Date=...` and `Brackets.aspx?event=<id>` pages, which it discovers and follows — date-scoped to `[today-2, today+7]` and the active event id. **The event id changes every weekend; never hardcode it, and don't disable this crawl in team-URL mode** (see ERRORS.md). Selector/parse logic is `parse_and_filter_schedule()`; deep notes in `perfect_game/SCRAPING.md`.

- **Merge semantics (`schedule_merge.merge_into_schedule`)** decide what counts as an alert. Game identity = `(Date, normalized Opponent)` with records like `(3-0-0)` stripped. Past games are locked; Upcoming games update Time/Location/Opponent or promote to Past when a score appears; placeholder opponents (`Unknown`/`TBD`) are replaced by a later named opponent matching date/time/location. Returns `(merged, new_entries, changed_entries)`.

- **Alert policy (`schedule_monitor._notify` + `notifications`).** Emails fire only for new/changed games that are not Past — except Past games within 48h (`is_recent_past_game`). The email body additionally filters to a 7-day lookahead. Email (Gmail SMTP) and Telegram go out together; every send is recorded by `history_logger` into `notification_history.json`.

- **Config & state.** All tunables and paths are centralized in `shared/config.py`, which reads `.env` at import (keys in `.env.example`). Git-ignored runtime state: `team_schedule.json` (source of truth — locked Past + live Upcoming), `monitor.log`, `monitor.pid`, `notification_history.json`.

- **USSSA monitor (`usssa/usssa_team_monitor.py`) is live** — deployed as `usssa-monitor.service` (5-min polling). `usssa_bracket_monitor.py` was deleted (superseded). See USSSA section below for commands and architecture.

## Architecture — USSSA monitor

`usssa/usssa_team_monitor.py` — single file, no daemon helper. Runs its own sleep loop.

Three API calls per cycle (all plain `POST https://www.usssa.com/api/?action=<name>`, form-urlencoded body, no Playwright):

1. **`getUpcomingEventsByTeamID`** (`teamID=3313953`) — discovers active/upcoming events. `ID` field = divisionID; `eventId` field = event. Do not swap — `getGameCenterContent` needs them separately.
2. **`teamInfoV11`** (`teamID=...&page=home&divID=undefined`) — `recentGames` list for score detection. Keyed on `gameId` set stored in `.usssa_monitor_snapshot.json` (never re-alerts on old games). **Do not use `upcomingGames`** — it goes empty once a tournament starts.
3. **`getGameCenterContent`** — pool play (option `101`) + bracket (option `111`) HTML. Body must be `gmParams=<URL-encoded JSON string>`. Strips `Pub\d+-\d+-D[\d.T:]+` timestamp before hashing to avoid false-positive alerts.

Active event = one whose `[startDate, endDate]` window contains today. First run snapshots silently; all subsequent runs alert on new `gameId`s or bracket hash changes.

Service commands:
```bash
systemctl --user restart usssa-monitor.service   # REQUIRED after code edits
systemctl --user status  usssa-monitor.service
journalctl --user -u usssa-monitor.service -f
tail -f usssa_team_monitor.log                   # application log
.venv/bin/python usssa/usssa_team_monitor.py --once   # one-shot check
.venv/bin/python usssa/usssa_team_monitor.py --force  # force notification
```

## Gotchas
- After any code change, **restart the relevant service** — both daemons import modules once at startup (`perfectgame-monitor.service` and `usssa-monitor.service`).
- `pytest` and manual CLI runs append to the **same `monitor.log`** the daemon uses, so it interleaves test noise (e.g. fetches for the placeholder `PLAYER_ID=0000000`). Don't read that as daemon behavior — correlate by PID/timestamp.
- Any test that mocks `should_poll_now` must set `interval_minutes` on the mock — the daemon reads it to reschedule.
- HTTP in tests is mocked with `responses`; the real CLI hits perfectgame.org (429/5xx trigger the scraper's backoff/retry).
- `parse_and_filter_schedule` accepts either a `BeautifulSoup` object or a raw HTML string. Always pass the already-built soup when you have it — re-parsing the same HTML wastes ~58ms per page.
