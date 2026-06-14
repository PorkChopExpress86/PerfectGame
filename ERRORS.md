# ERRORS.md — Known pitfalls & how to avoid them

Mistakes and dead-ends already hit in this repo, recorded so they aren't repeated.
Add an entry whenever you lose time to something non-obvious: **symptom → cause → fix.**

## USSSA `getGameCenterContent` returns `{}` (empty)

- **Symptom:** `fetch_bracket_html` returns `None`; API response is `{}` with no `html` key.
- **Cause:** The `gmParams` body field must be a **URL-encoded JSON string** (matching what the AngularJS SPA does via `encodeURIComponent(angular.toJson(gmParams))`). Sending the JSON directly as a plain form field or as a nested dict produces an empty response.
- **Fix:** `body = "gmParams=" + urllib.parse.quote(json.dumps(gm_params))` — quote the entire JSON string, then prefix with `gmParams=`. Do not let `requests` encode it as a nested dict.

## USSSA bracket hash alerts on every poll (timestamp false-positive)

- **Symptom:** Bracket change notification fires every 5 minutes even though the bracket hasn't changed.
- **Cause:** The bracket HTML contains a volatile publish timestamp like `Pub1-2687788-D6.13T21:58` that changes on every CDN republish, so a naive SHA-256 of the raw HTML changes constantly.
- **Fix:** Strip the timestamp before hashing: `re.sub(r'Pub\d+-\d+-D[\d.T:]+', '', html)`. This is already done in `_bracket_hash()` in `usssa_team_monitor.py`.

## USSSA `upcomingGames` is empty during/after a tournament

- **Symptom:** Team monitor shows 0 upcoming games on tournament weekend; score changes are never detected.
- **Cause:** `upcomingGames` in the `teamInfoV11` response goes empty once a tournament begins. Scores appear in `recentGames` (and `completedGames`), not `upcomingGames`.
- **Fix:** Use `recentGames` for score detection, keyed on `gameId`. Already fixed in `usssa_team_monitor.py`.

## Daemon keeps running old code after an edit
- **Symptom:** A code change has no effect; `monitor.log` shows the old behavior.
- **Cause:** `perfectgame-monitor.service` imports modules once at startup and runs indefinitely.
- **Fix:** `systemctl --user restart perfectgame-monitor.service` after editing. Confirm the new
  PID via the `Daemon started (PID ...)` log line.

## "0 games" / "Site may be blocking" while the team clearly has a tournament
- **Symptom:** `fetch_team_schedule` returns 0 games; log says "No games returned... Site may be
  blocking or no games are scheduled" — even though there's an event this weekend.
- **Cause:** The configured `TEAM_URL` (`PGBA/Team/default.aspx`) only renders the most-recent
  *completed* event's schedule grid. The current weekend's games live on
  `TournamentSchedule.aspx?event=<id>&Date=...` and `Brackets.aspx?event=<id>` pages. If event-link
  discovery is disabled in team-URL mode, the scraper never reaches them. The "blocking" text is a
  generic 0-games message — it also prints when the fetch was HTTP 200 with no current games.
- **Fix:** Keep event discovery enabled in team-URL mode, scoped to the current event (date filter
  `[today-2, today+7]`, same-event-id, bracket gated on `current_event_id`). Verify with
  `.venv/bin/python perfect_game/schedule_monitor.py --dry-run` and look for `-> Discovered:` lines
  and a non-zero `Total games found`.

## monitor.log looks corrupted / has impossible entries
- **Symptom:** Interleaved lines that don't match the running daemon — e.g. fetch errors for
  `Playerprofile.aspx?ID=0000000`, or `Interval change: 10 -> 6660 min` on a Saturday.
- **Cause:** `schedule_monitor.log()` and the scraper's `_log()` both append to `monitor.log`.
  Running `pytest` or manual CLI commands writes there too — including daemon unit tests that mock a
  far-future `next_poll_at` (hence the huge interval) and integration tests using the placeholder
  `PLAYER_ID=0000000`.
- **Fix:** Correlate by timestamp/PID against `Daemon started (PID ...)`; ignore lines whose
  traceback paths contain `tests/..` and anything referencing placeholder IDs.

## Daemon test fails comparing a MagicMock to an int
- **Symptom:** `test_daemon_*` fails, or the daemon reschedules to a nonsense interval, when
  `should_poll_now` is mocked.
- **Cause:** `schedule_daemon._run_check` reads `decision.interval_minutes`. A bare
  `MagicMock(should_poll=True)` returns a Mock (not an int) for that attribute.
- **Fix:** Set `interval_minutes=POLL_INTERVAL_MINUTES` (or `HOT_POLL_INTERVAL_MINUTES`) on the mock.

## A newly detected bracket game shows opponent "Unknown" (not a bug)
- **Symptom:** A fresh Sunday/bracket alert reads `vs Unknown` instead of a team name.
- **Cause:** Perfect Game posts bracket games before the feeder games finish, so the opponent
  is still TBD; `parse_and_filter_schedule` records it as `Unknown`. (Observed/validated
  2026-05-30: `May 31 1:15 PM vs Unknown @ Field 4 @ Doss Park`.)
- **Fix:** Nothing — this is expected. `schedule_merge` replaces the `Unknown`/`TBD` placeholder
  with the real opponent (matched on date/time/location) on a later poll once PG fills it in,
  and that update goes out as a "changed" alert. Don't special-case or suppress it.
