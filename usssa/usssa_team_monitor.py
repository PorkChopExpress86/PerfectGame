#!/usr/bin/env python3
"""
usssa_team_monitor.py — Dynamic USSSA schedule + bracket monitor for Texas Prospect.

Discovers active tournaments automatically via getUpcomingEventsByTeamID.
Tracks new game results via recentGames (works during and after a tournament).
Tracks bracket/pool changes via getGameCenterContent (direct POST, no Playwright).

Usage:
    .venv/bin/python usssa/usssa_team_monitor.py --once
    .venv/bin/python usssa/usssa_team_monitor.py --force
    .venv/bin/python usssa/usssa_team_monitor.py --interval 5

Environment (from .env):
    EMAIL_ADDRESS, EMAIL_APP_PASSWORD, TO_EMAILS
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import smtplib
import sys
import time
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

from shared.telegram_notifier import send_telegram  # noqa: E402
from shared.history_logger import log_notification  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT_DIR / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EMAIL_ADDRESS: str | None = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD: str | None = os.getenv("EMAIL_APP_PASSWORD")
TO_EMAILS: str = os.getenv("TO_EMAILS", EMAIL_ADDRESS or "")

TEAM_ID = "3313953"
TEAM_NAME = "Texas Prospect"
TEAM_PAGE_URL = f"https://www.usssa.com/baseball/teamHome/?teamID={TEAM_ID}"
USSSA_API = "https://www.usssa.com/api/"

SNAPSHOT_FILE = ROOT_DIR / ".usssa_monitor_snapshot.json"
LOG_FILE = ROOT_DIR / "usssa_team_monitor.log"

DEFAULT_INTERVAL_MINUTES = 5

# Pool play (101) and single-elimination bracket (111)
_BRACKET_OPTIONS = [("101", "Pool Play"), ("111", "Bracket")]

# Strip the volatile publish timestamp baked into bracket HTML before hashing,
# e.g. "Pub1-2687788-D6.13T21:58", so unchanged content doesn't trigger alerts.
_PUB_STAMP_RE = re.compile(r"Pub\d+-\d+-D[\d.T:]+")

_shutdown_requested = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [usssa] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def _api_post(action: str, form_body: str) -> dict | list | None:
    try:
        resp = requests.post(
            USSSA_API,
            params={"action": action},
            data=form_body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        _log(f"  ⚠ API error ({action}): {exc}")
        return None


def fetch_upcoming_events() -> list[dict]:
    """Return events the team is registered for."""
    data = _api_post("getUpcomingEventsByTeamID", f"teamID={TEAM_ID}")
    return data if isinstance(data, list) else []


def fetch_team_info() -> dict | None:
    """Return teamInfoV11 payload (contains recentGames, completedGames, etc.)."""
    return _api_post("teamInfoV11", f"teamID={TEAM_ID}&page=home&divID=undefined")  # type: ignore[return-value]


def fetch_bracket_html(event_id: str, division_id: str, option: str) -> str | None:
    """
    Fetch pool/bracket HTML via getGameCenterContent without Playwright.
    gmParams must be a JSON-encoded, URL-encoded object — discovered from gameCenterCtrl.js.
    """
    gm_params = {
        "eventID": event_id,
        "divisionID": division_id,
        "bnp": "1",
        "bf": "1",
        "option": option,
        "isWinner": "1",
    }
    body = "gmParams=" + quote(json.dumps(gm_params))
    data = _api_post("getGameCenterContent", body)
    if not isinstance(data, dict):
        return None
    return data.get("html") or None


# ---------------------------------------------------------------------------
# Event selection
# ---------------------------------------------------------------------------
def _event_date(ev: dict, key: str) -> date | None:
    try:
        return datetime.fromisoformat(ev[key]).date()
    except (KeyError, ValueError):
        return None


def pick_active_event(events: list[dict]) -> dict | None:
    """
    Return the event whose date window contains today (active tournament),
    otherwise the soonest future registered event.
    """
    today = date.today()
    for ev in events:
        start = _event_date(ev, "startDate") or date.max
        end = _event_date(ev, "endDate") or date.min
        if start <= today <= end:
            return ev
    future = [e for e in events if (_event_date(e, "startDate") or date.min) > today]
    return min(future, key=lambda e: _event_date(e, "startDate")) if future else None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------
def _load_snapshot() -> dict:
    if SNAPSHOT_FILE.exists():
        try:
            return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_snapshot(data: dict) -> None:
    SNAPSHOT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Score change detection
# ---------------------------------------------------------------------------
def _normalize_game(raw: dict) -> dict:
    return {
        "gameId": int(raw.get("gameId") or 0),
        "date": (raw.get("date") or "")[:10],
        "opponent": (raw.get("opponent") or "TBD").title(),
        "result": raw.get("result") or "?",
        "wScore": raw.get("wScore"),
        "lScore": raw.get("lScore"),
    }


def detect_new_games(recent_raw: list[dict], seen_ids: set[int]) -> list[dict]:
    """Return normalized games whose gameId has not been seen before."""
    return [
        _normalize_game(r)
        for r in recent_raw
        if int(r.get("gameId") or 0) and int(r.get("gameId") or 0) not in seen_ids
    ]


# ---------------------------------------------------------------------------
# Bracket change detection
# ---------------------------------------------------------------------------
def _bracket_hash(html: str) -> str:
    cleaned = _PUB_STAMP_RE.sub("", html).strip()
    return hashlib.sha256(cleaned.encode()).hexdigest()[:16]


def _bracket_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace for a readable bracket summary."""
    text = _PUB_STAMP_RE.sub("", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def _score_row(g: dict, highlight: str = "") -> str:
    result_color = "#2d6a4f" if g["result"] == "W" else "#b91c1c"
    result_label = f'<b style="color:{result_color};">{g["result"]}</b>'
    score = f'{g["wScore"]}–{g["lScore"]}' if g["wScore"] is not None else "—"
    bg = f' style="background:{highlight};"' if highlight else ""
    return (
        f"<tr{bg}>"
        f'<td style="padding:8px;border:1px solid #ddd;">{g["date"]}</td>'
        f'<td style="padding:8px;border:1px solid #ddd;">{g["opponent"]}</td>'
        f'<td style="padding:8px;border:1px solid #ddd;text-align:center;">{result_label}</td>'
        f'<td style="padding:8px;border:1px solid #ddd;text-align:center;">{score}</td>'
        "</tr>"
    )


def _build_email_html(
    new_games: list[dict],
    bracket_changes: list[tuple[str, str]],
    active_event: dict | None,
    future_events: list[dict],
) -> str:
    now_str = datetime.now().strftime("%I:%M %p on %B %d, %Y")
    sections = ""

    if new_games:
        header = (
            '<tr style="background:#1a3a5c;color:white;">'
            '<th style="padding:10px;border:1px solid #ddd;">Date</th>'
            '<th style="padding:10px;border:1px solid #ddd;">Opponent</th>'
            '<th style="padding:10px;border:1px solid #ddd;">Result</th>'
            '<th style="padding:10px;border:1px solid #ddd;">Score</th>'
            "</tr>"
        )
        rows = "".join(_score_row(g, "#e8f5e9") for g in new_games)
        sections += f"""
        <h3 style="color:#2d6a4f;">New Game Result(s)</h3>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead>{header}</thead><tbody>{rows}</tbody>
        </table>"""

    for label, text in bracket_changes:
        sections += f"""
        <h3 style="color:#1a3a5c;">{label} Updated</h3>
        <pre style="background:#f4f4f4;padding:12px;border-radius:6px;font-size:11px;
                    max-height:300px;overflow:auto;white-space:pre-wrap;">{text[:2000]}</pre>"""

    if active_event:
        start = (active_event.get("startDate") or "")[:10]
        end = (active_event.get("endDate") or "")[:10]
        div_id = active_event.get("ID", "")
        ev_id = active_event.get("eventId", "")
        gc_url = (
            f"https://usssa.com/baseball/event_gameCenter/"
            f"?eventID={ev_id}&age=10&ageClass=AA&divisionID={div_id}"
            f"&bnp=1&bf=1&isWinner=1&option=101"
        )
        sections += f"""
        <h3 style="color:#555;">Active Tournament</h3>
        <p><strong>{active_event.get("name", "")}</strong> ({start}–{end})<br>
        <a href="{gc_url}">View Game Center →</a></p>"""

    if future_events:
        ev_rows = "".join(
            f'<tr>'
            f'<td style="padding:6px 8px;border:1px solid #ddd;">{e.get("name","")}</td>'
            f'<td style="padding:6px 8px;border:1px solid #ddd;">{(e.get("startDate") or "")[:10]}</td>'
            f'<td style="padding:6px 8px;border:1px solid #ddd;">{(e.get("endDate") or "")[:10]}</td>'
            f"</tr>"
            for e in future_events
        )
        sections += f"""
        <h3 style="color:#555;">Upcoming Registered Events</h3>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead><tr style="background:#1a3a5c;color:white;">
                <th style="padding:8px;border:1px solid #ddd;">Event</th>
                <th style="padding:8px;border:1px solid #ddd;">Start</th>
                <th style="padding:8px;border:1px solid #ddd;">End</th>
            </tr></thead>
            <tbody>{ev_rows}</tbody>
        </table>"""

    return f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">⚾ USSSA Update — {TEAM_NAME}</h2>
        <p>Checked at <strong>{now_str}</strong>.</p>
        {sections}
        <p><a href="{TEAM_PAGE_URL}"
              style="display:inline-block;padding:10px 20px;background:#1a3a5c;
                     color:white;text-decoration:none;border-radius:5px;">
            View Team Page
        </a></p>
        <p style="font-size:12px;color:#888;">USSSA Monitor — {TEAM_NAME} 10u AA</p>
    </body></html>"""


def send_notification(
    new_games: list[dict],
    bracket_changes: list[tuple[str, str]],
    active_event: dict | None = None,
    future_events: list[dict] | None = None,
) -> bool:
    """Build subject + HTML and send email + Telegram. Returns True on success."""
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        _log("ERROR: EMAIL_ADDRESS / EMAIL_APP_PASSWORD not set")
        return False
    recipients = [e.strip() for e in TO_EMAILS.split(",") if e.strip()]
    if not recipients:
        _log("ERROR: No recipients configured (TO_EMAILS in .env)")
        return False

    parts: list[str] = []
    if new_games:
        parts.append(f"{len(new_games)} new result(s)")
    if bracket_changes:
        parts.append(f"{len(bracket_changes)} bracket update(s)")
    if not parts:
        parts.append("update")
    subject = f"⚾ {TEAM_NAME} USSSA — {', '.join(parts)}"

    html_body = _build_email_html(new_games, bracket_changes, active_event, future_events or [])

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        _log(f"  Sending email to {recipients}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, recipients, msg.as_string())
        _log("  ✅ Email sent.")

        tg_lines = []
        for g in new_games:
            icon = "\U0001f3c6" if g["result"] == "W" else "❌"
            tg_lines.append(
                f"{icon} {g['date']} vs {g['opponent']}: "
                f"{g['result']} {g['wScore']}–{g['lScore']}"
            )
        for label, _ in bracket_changes:
            tg_lines.append(f"\U0001f4cb {label} updated")
        send_telegram(subject, "\n".join(tg_lines),
                      team_url=TEAM_PAGE_URL, team_name=f"{TEAM_NAME} (USSSA)")
        log_notification("usssa", subject)
        return True
    except smtplib.SMTPAuthenticationError:
        _log("  ❌ SMTP auth failed — check EMAIL_APP_PASSWORD")
        return False
    except Exception as exc:
        _log(f"  ❌ Email failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------
def check_for_changes(force: bool = False) -> bool:
    """
    Single monitoring cycle. Returns True if a notification was sent.

    Flow:
      1. Discover registered events via getUpcomingEventsByTeamID.
      2. Detect new game results via recentGames (keyed on gameId — never re-alerts).
      3. If a tournament is active today, check pool/bracket HTML for changes.
      4. Notify on new scores or bracket changes; first run only snapshots.
    """
    snapshot = _load_snapshot()
    is_first_run = "seen_game_ids" not in snapshot
    seen_ids: set[int] = set(snapshot.get("seen_game_ids", []))
    bracket_hashes: dict[str, str] = snapshot.get("bracket_hashes", {})

    # 1. Registered events
    upcoming_events = fetch_upcoming_events()
    _log(f"Registered events: {len(upcoming_events)}")
    for e in upcoming_events:
        _log(f"  {e.get('name')} ({(e.get('startDate') or '')[:10]}–{(e.get('endDate') or '')[:10]})")

    active_event = pick_active_event(upcoming_events)
    if active_event:
        _log(
            f"Active tournament: {active_event.get('name')} "
            f"(divisionID={active_event.get('ID')}, eventId={active_event.get('eventId')})"
        )

    # 2. Recent game results
    team_data = fetch_team_info()
    recent_raw: list[dict] = (team_data or {}).get("recentGames") or []
    _log(f"Recent games from API: {len(recent_raw)}")

    new_games: list[dict] = []
    if not is_first_run:
        new_games = detect_new_games(recent_raw, seen_ids)
        for g in new_games:
            _log(f"  \U0001f195 {g['date']} vs {g['opponent']}: {g['result']} {g['wScore']}–{g['lScore']}")

    all_current_ids = {int(r.get("gameId") or 0) for r in recent_raw if r.get("gameId")}

    # 3. Bracket / pool play
    bracket_changes: list[tuple[str, str]] = []
    new_bracket_hashes = dict(bracket_hashes)

    if active_event:
        event_id = str(active_event.get("eventId", ""))
        division_id = str(active_event.get("ID", ""))

        for option, label in _BRACKET_OPTIONS:
            key = f"{event_id}_{division_id}_{option}"
            html = fetch_bracket_html(event_id, division_id, option)
            if html is None:
                _log(f"  ⚠ Could not fetch {label}")
                continue

            new_hash = _bracket_hash(html)
            old_hash = bracket_hashes.get(key, "")
            new_bracket_hashes[key] = new_hash

            if new_hash != old_hash:
                if old_hash:
                    _log(f"  \U0001f514 {label} changed ({old_hash[:8]} → {new_hash[:8]})")
                    bracket_changes.append((label, _bracket_text(html)))
                else:
                    _log(f"  First {label} snapshot ({new_hash[:8]})")
            else:
                _log(f"  ✓ {label} unchanged")

    # 4. Save snapshot
    _save_snapshot({
        "last_checked": datetime.now().isoformat(),
        "seen_game_ids": sorted(seen_ids | all_current_ids),
        "bracket_hashes": new_bracket_hashes,
    })

    if is_first_run:
        _log(
            f"First run — captured {len(all_current_ids)} game IDs + "
            f"{len(new_bracket_hashes)} bracket snapshot(s). No notification sent."
        )
        return False

    if not new_games and not bracket_changes and not force:
        _log("✓ No changes.")
        return False

    # 5. Notify
    future_events = [e for e in upcoming_events if e is not active_event]
    send_notification(new_games, bracket_changes, active_event, future_events)
    return True


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------
def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown_requested
    _log(f"Received {signal.Signals(signum).name} — shutting down.")
    _shutdown_requested = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dynamic USSSA monitor for Texas Prospect 10u AA."
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL_MINUTES,
        help=f"Polling interval in minutes (default: {DEFAULT_INTERVAL_MINUTES}).",
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument(
        "--force", action="store_true",
        help="Send notification even if nothing changed.",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _log("=" * 60)
    _log("USSSA Monitor starting")
    _log(f"  Team:       {TEAM_NAME} (teamID={TEAM_ID})")
    _log(f"  Interval:   {args.interval} min")
    _log(f"  Recipients: {TO_EMAILS}")
    _log("=" * 60)

    if args.once:
        check_for_changes(force=args.force)
        _log("Done.")
        return

    while not _shutdown_requested:
        try:
            check_for_changes(force=args.force)
        except Exception as exc:
            _log(f"Unhandled error: {exc}")

        if _shutdown_requested:
            break

        _log(f"Sleeping {args.interval} min...")
        for _ in range(args.interval * 60):
            if _shutdown_requested:
                break
            time.sleep(1)

    _log("Monitor stopped.")


if __name__ == "__main__":
    main()
