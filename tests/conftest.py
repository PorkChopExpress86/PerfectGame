"""
Shared test fixtures and sample data for PerfectGame tests.
"""

import json
import pytest

# ---------------------------------------------------------------------------
# Sample HTML snippets
# ---------------------------------------------------------------------------

SAMPLE_SCHEDULE_HTML_ROW = """
<div class="nestedscheduleGridRow">
    <span id="lblMonthDay" class="lbl">Mar 1</span>
    <span id="lblTime" class="lbl">11:30 AM</span>
    <a id="hlOpponentName" href="/team/123">Expos Baseball 10U</a>
    <span id="lblField" class="lbl">Field 3</span>
    <a id="hlBallpark" href="/park/1">Bayer Park</a>
</div>
"""

SAMPLE_PAST_GAME_ROW = """
<div class="nestedscheduleGridRow">
    <span id="lblMonthDay" class="lbl">Feb 28</span>
    <span id="lblTime" class="lbl">N/A</span>
    <a id="hlOpponentName" href="/team/456">Fairfield Ducks</a>
    <span id="lblField" class="lbl">3</span>
    <a id="hlBallpark" href="/park/1">@ Bayer Park</a>
    <span id="lblGameScore" class="lbl">19-7,</span>
    <span style="font-weight:bold;">L, </span>
</div>
"""

SAMPLE_FULL_PAGE = f"""
<html><body>
<div class="scheduleGrid">
    {SAMPLE_PAST_GAME_ROW}
    {SAMPLE_SCHEDULE_HTML_ROW}
</div>
</body></html>
"""

SAMPLE_EMPTY_PAGE = "<html><body><div>No schedule data</div></body></html>"

SAMPLE_MALFORMED_ROW = """
<div class="nestedscheduleGridRow">
    <span id="lblMonthDay" class="lbl">   </span>
    <a id="hlOpponentName" href="/team/789">Mystery Team</a>
</div>
"""

SAMPLE_PROFILE_HTML = """
<html><body>
<a href="/PGBA/Team/default.aspx?orgid=90706&orgteamid=284257&team=1074261&Year=2026">Example Team</a>
<a href="/PGBA/Team/default.aspx?team=9999">Another Team</a>
</body></html>
"""


# ---------------------------------------------------------------------------
# Sample schedule data (dicts)
# ---------------------------------------------------------------------------

@pytest.fixture
def past_game():
    return {
        "Date": "Feb 28",
        "Time": "N/A",
        "Score/Result": "Played (L 19-7)",
        "Opponent": "Fairfield Ducks",
        "Location": "3 @ Bayer Park",
        "Type": "Past",
    }


@pytest.fixture
def upcoming_game():
    return {
        "Date": "Mar 1",
        "Time": "11:30 AM",
        "Score/Result": "N/A",
        "Opponent": "Expos Baseball 10U",
        "Location": "Field 3 Bayer Park",
        "Type": "Upcoming",
    }


@pytest.fixture
def sample_schedule(past_game, upcoming_game):
    return [past_game, upcoming_game]


@pytest.fixture
def schedule_file(tmp_path, sample_schedule):
    """Write sample schedule to a temp JSON file and return the path."""
    path = tmp_path / "team_schedule.json"
    path.write_text(json.dumps(sample_schedule, indent=2))
    return path
