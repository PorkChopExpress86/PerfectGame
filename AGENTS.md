# Repository Guidelines

## Project Structure & Module Organization
This repository is a Python monitor for Perfect Game and USSSA baseball schedules.
Core Perfect Game code lives in `perfect_game/`: `schedule_daemon.py` runs the fixed
polling service, `schedule_monitor.py` performs one scrape/merge/notify cycle,
`perfect_game_scraper.py` handles HTML scraping, and `schedule_merge.py`,
`schedule_state.py`, `polling_gate.py`, and `notifications.py` isolate business
logic. Shared utilities are in `shared/`. USSSA monitors live in `usssa/`. Tests
live in `tests/`, with fixtures in `tests/conftest.py`. Systemd templates are in
`systemd/`; runtime files such as logs, schedules, `.env`, and snapshots are
ignored.

## Build, Test, and Development Commands
Create and populate the virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Run the full suite:
```bash
.venv/bin/python -m pytest -q
```
Check import/bytecode validity:
```bash
.venv/bin/python -m compileall perfect_game shared usssa tests
```
Run local checks manually:
```bash
.venv/bin/python perfect_game/schedule_monitor.py --dry-run
systemctl --user status perfectgame-monitor.service
```

## Coding Style & Naming Conventions
Use Python 3.11+ and 4-space indentation. Prefer small modules with one clear
responsibility. Function and variable names should be `snake_case`; classes use
`PascalCase`. Keep CLI entrypoints thin and put testable logic in importable
helpers. Avoid committing generated/runtime data. No formatter is currently
configured; keep diffs focused and consistent with nearby code.

## Testing Guidelines
The test framework is `pytest`; HTTP scraper integration tests use `responses`.
Name test files `tests/test_*.py` and write behavior-focused test names. Add or
update tests for parser selectors, merge rules, polling gates, notification
side effects, and CLI entrypoints whenever those areas change. The suite should
run warning-free with `.venv/bin/python -m pytest -q`.

## Commit & Pull Request Guidelines
Recent history uses concise imperative or conventional-style messages, for
example `feat: Include recent scores (<48h) in email alerts` and `fix: Don't
alert on past games`. Keep commits scoped to one logical change. Pull requests
should summarize behavior changes, list verification commands, note service or
configuration impacts, and avoid exposing secrets from `.env`.

## Security & Configuration Tips
Store credentials only in `.env`; use `.env.example` for placeholders. Do not
print email app passwords, Telegram tokens, or live recipient details in docs or
commits. Prefer `TEAM_URL` for Perfect Game team monitoring; `PLAYER_TEAM_URL`
is supported for backwards compatibility.
