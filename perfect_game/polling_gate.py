"""Polling window rules for the Perfect Game monitor."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.config import (
    HOT_POLL_INTERVAL_MINUTES,
    HOT_POLL_WINDOWS,
    POLL_DAYS,
    POLL_INTERVAL_MINUTES,
)


def _minute_of_week(weekday, hour, minute=0):
    """Minutes elapsed since Monday 00:00 (Monday=0 .. Sunday=6)."""
    return weekday * 1440 + hour * 60 + minute


def in_hot_window(now=None):
    """Return True when `now` falls inside a fast-polling posting window."""
    if now is None:
        now = datetime.now()
    current = _minute_of_week(now.weekday(), now.hour, now.minute)
    for start_wd, start_hr, end_wd, end_hr in HOT_POLL_WINDOWS:
        start = _minute_of_week(start_wd, start_hr)
        end = _minute_of_week(end_wd, end_hr)
        if start <= end:
            if start <= current < end:
                return True
        else:  # window wraps past Sunday into Monday
            if current >= start or current < end:
                return True
    return False


@dataclass(frozen=True)
class PollDecision:
    should_poll: bool
    reason: str
    interval_minutes: int = POLL_INTERVAL_MINUTES
    next_poll_at: datetime | None = None


def next_thursday_start(now=None):
    """Return the next Thursday at midnight after `now`."""
    if now is None:
        now = datetime.now()
    days_until = (3 - now.weekday()) % 7
    if days_until == 0:
        days_until = 7
    target = now + timedelta(days=days_until)
    return target.replace(hour=0, minute=0, second=0, microsecond=0)


def current_weekend_window(now=None):
    """Return the Thursday-Sunday window that contains or precedes `now`."""
    if now is None:
        now = datetime.now()
    days_since_thursday = (now.weekday() - 3) % 7
    start = (now - timedelta(days=days_since_thursday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = (start + timedelta(days=3)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    return start, end


def _parse_game_date(date_str, now):
    date_str = (date_str or "").strip()
    if not date_str:
        return None
    if "," in date_str:
        date_str = date_str.split(",", 1)[1].strip()
    for fmt in ("%b %d %Y", "%B %d %Y", "%m/%d/%Y", "%b %d", "%B %d"):
        try:
            if "%Y" in fmt:
                parsed = datetime.strptime(date_str, fmt)
            else:
                parsed = datetime.strptime(f"{date_str} {now.year}", f"{fmt} %Y")
            if (now - parsed).days > 180:
                parsed = parsed.replace(year=now.year + 1)
            elif (parsed - now).days > 180:
                parsed = parsed.replace(year=now.year - 1)
            return parsed
        except ValueError:
            continue
    return None


def has_upcoming_game_in_current_window(games, now=None):
    """Return True when any upcoming game is dated in the active Thu-Sun window."""
    if now is None:
        now = datetime.now()
    start, end = current_weekend_window(now)
    for game in games:
        if game.get("Type") != "Upcoming":
            continue
        game_date = _parse_game_date(game.get("Date"), now)
        if game_date and start <= game_date <= end:
            return True
    return False


def should_poll_now(games, now=None):
    """Decide whether the Perfect Game monitor should poll at this time."""
    if now is None:
        now = datetime.now()
    if now.weekday() not in POLL_DAYS:
        next_poll = next_thursday_start(now)
        return PollDecision(
            False,
            "outside Thursday-Sunday polling window",
            next_poll_at=next_poll,
        )
    if in_hot_window(now):
        return PollDecision(
            True,
            "within hot posting window",
            interval_minutes=HOT_POLL_INTERVAL_MINUTES,
        )
    return PollDecision(
        True,
        "within Thursday-Sunday polling window",
        interval_minutes=POLL_INTERVAL_MINUTES,
    )
