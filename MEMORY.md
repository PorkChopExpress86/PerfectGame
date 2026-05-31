# MEMORY.md — Project work log

A running log of notable changes and decisions, so future sessions have continuity.
**Newest first.** Append a short entry when you finish a meaningful change: what changed,
why, and any follow-up. This is separate from `ERRORS.md` (which tracks pitfalls) and from
`CLAUDE.md` (which is stable guidance).

## 2026-05-30
- **✅ Validated live (22:02 CDT).** The daemon detected the Sunday bracket game
  (`May 31 1:15 PM vs Unknown @ Field 4 @ Doss Park`) as NEW within a 3-min hot-window cycle
  (posted between the 21:59 and 22:02 polls), and the email/Telegram alert was received.
  End-to-end timing + event discovery confirmed working. The opponent posted as `Unknown`
  because it was a bracket game still TBD — `schedule_merge` replaces that placeholder with
  the named team on a later cycle (see `ERRORS.md`).
- **5-minute alert window via hot polling.** Added `HOT_POLL_INTERVAL_MINUTES = 3` and
  `HOT_POLL_WINDOWS` to `shared/config.py`; `polling_gate.in_hot_window()` +
  `should_poll_now()` now return a 3-min interval inside the posting windows, and
  `schedule_daemon` honors `PollDecision.interval_minutes` (it had hardcoded 10 and ignored
  the field). Windows (Central): **Thu 12:00 → Sat 00:00** (Saturday games drop "sometime
  Thursday", Fri buffer) and **Sat 19:00 → Sun 21:00** (Sunday bracket posts Sat evening +
  next-round games if the team advances). Baseline stays 10 min Thu–Sun; Mon–Wed idle.
- **Made team-URL mode actually see tournament games.** Re-enabled event-link discovery in
  `fetch_team_schedule()` for team-URL mode (a WIP change had disabled it), scoped to the
  current event: date filter `[today-2, today+7]` on schedule links, bracket-following gated
  on `current_event_id` so old brackets aren't fetched. Without this the daemon only saw the
  stale team page and never alerted. Details in `ERRORS.md`.
- **Tests:** added `tests/test_adaptive.py::TestHotPostingWindows` (9 cases) and a daemon
  hot-interval test; updated a daemon mock to supply `interval_minutes`. Full suite: 120 green.
- **Docs:** updated `README.md`, `setup.sh`, and the systemd template comments to describe the
  hot-window cadence.
- **Context:** team is **Texas Prospects** (renamed from "D1 Athletics"); USSSA monitors are
  intentionally removed/dormant — don't recreate them.

### Follow-ups / known-minor
- The discovery crawl fetches both padded and non-padded date URLs (`Date=05/30/2026` and
  `Date=5/30/2026`) as distinct pages → ~1 redundant fetch per cycle. Harmless; could dedupe
  by canonicalizing the `Date` query param if request volume becomes a concern.
