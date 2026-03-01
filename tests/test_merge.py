"""
tests/test_merge.py - Tests for schedule_monitor.merge_into_schedule()
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from schedule_monitor import merge_into_schedule


class TestMergeIntoSchedule:
    """Tests for the merge algorithm."""

    def test_new_game_added_to_empty(self):
        """A scraped game should be added when existing is empty."""
        scraped = [{"Date": "Mar 5", "Opponent": "Hawks", "Type": "Upcoming",
                     "Time": "2:00 PM", "Location": "Field 1"}]
        merged, new, changed = merge_into_schedule([], scraped)
        assert len(merged) == 1
        assert len(new) == 1
        assert new[0]["Opponent"] == "Hawks"
        assert changed == []

    def test_past_games_are_locked(self):
        """Past games should never be modified, even if scraper returns different data."""
        existing = [{"Date": "Feb 28", "Opponent": "Ducks", "Type": "Past",
                      "Score/Result": "Played (L 19-7)", "Time": "N/A",
                      "Location": "Field 3"}]
        scraped = [{"Date": "Feb 28", "Opponent": "Ducks", "Type": "Past",
                     "Score/Result": "Played (W 10-5)", "Time": "N/A",
                     "Location": "DIFFERENT FIELD"}]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert len(merged) == 1
        assert merged[0]["Score/Result"] == "Played (L 19-7)"  # unchanged
        assert merged[0]["Location"] == "Field 3"  # unchanged
        assert new == []
        assert changed == []

    def test_upcoming_time_change_detected(self):
        """A time change on an upcoming game should be detected and applied."""
        existing = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                      "Time": "11:30 AM", "Location": "Field 1"}]
        scraped = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                     "Time": "2:00 PM", "Location": "Field 1"}]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert len(merged) == 1
        assert merged[0]["Time"] == "2:00 PM"
        assert len(changed) == 1
        assert "Time" in changed[0]["fields"]

    def test_upcoming_location_change_detected(self):
        """A location change on an upcoming game should be detected and applied."""
        existing = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                      "Time": "11:30 AM", "Location": "Field 1"}]
        scraped = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                     "Time": "11:30 AM", "Location": "Field 5 New Park"}]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert merged[0]["Location"] == "Field 5 New Park"
        assert "Location" in changed[0]["fields"]

    def test_upcoming_promoted_to_past(self):
        """An upcoming game with a new score should be promoted to Past."""
        existing = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                      "Time": "11:30 AM", "Location": "Field 1",
                      "Score/Result": "N/A"}]
        scraped = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Past",
                     "Time": "N/A", "Score/Result": "Played (W 8-3)",
                     "Location": "Field 1"}]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert merged[0]["Type"] == "Past"
        assert "Played" in merged[0]["Score/Result"]
        assert len(changed) == 1
        assert "Result" in changed[0]["fields"]

    def test_missing_from_scrape_kept(self):
        """Games in existing but missing from scrape should be retained."""
        existing = [
            {"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
             "Time": "11:30 AM", "Location": "Field 1"},
            {"Date": "Mar 8", "Opponent": "Eagles", "Type": "Upcoming",
             "Time": "9:00 AM", "Location": "Field 2"},
        ]
        scraped = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                     "Time": "11:30 AM", "Location": "Field 1"}]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert len(merged) == 2  # both kept
        opponents = {g["Opponent"] for g in merged}
        assert "Eagles" in opponents

    def test_no_changes_returns_empty_lists(self):
        """When scrape matches existing exactly, new and changed should be empty."""
        existing = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                      "Time": "11:30 AM", "Location": "Field 1"}]
        scraped = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                     "Time": "11:30 AM", "Location": "Field 1"}]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert new == []
        assert changed == []

    def test_deduplication_by_date_opponent(self):
        """Merge key is (Date, Opponent) — duplicates in scraped should not duplicate."""
        existing = [{"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
                      "Time": "11:30 AM", "Location": "Field 1"}]
        scraped = [
            {"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
             "Time": "11:30 AM", "Location": "Field 1"},
            {"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
             "Time": "2:00 PM", "Location": "Field 2"},  # duplicate key
        ]
        merged, new, changed = merge_into_schedule(existing, scraped)
        # Only one entry for (Mar 1, Expos) because scraped_by_key deduplicates
        count = sum(1 for g in merged if g["Opponent"] == "Expos" and g["Date"] == "Mar 1")
        assert count == 1

    def test_multiple_new_games(self):
        """Multiple new games should all be appended and reported."""
        existing = []
        scraped = [
            {"Date": "Mar 5", "Opponent": "Hawks", "Type": "Upcoming",
             "Time": "2:00 PM", "Location": "Field 1"},
            {"Date": "Mar 6", "Opponent": "Eagles", "Type": "Upcoming",
             "Time": "10:00 AM", "Location": "Field 2"},
        ]
        merged, new, changed = merge_into_schedule(existing, scraped)
        assert len(merged) == 2
        assert len(new) == 2

    def test_sort_order_past_before_upcoming(self):
        """Past games should sort before Upcoming in the merged result."""
        existing = []
        scraped = [
            {"Date": "Mar 1", "Opponent": "Expos", "Type": "Upcoming",
             "Time": "11:30 AM", "Location": "Field 1"},
            {"Date": "Feb 28", "Opponent": "Ducks", "Type": "Past",
             "Score/Result": "Played (L 19-7)", "Time": "N/A",
             "Location": "Field 3"},
        ]
        merged, _, _ = merge_into_schedule(existing, scraped)
        assert merged[0]["Type"] == "Past"
        assert merged[1]["Type"] == "Upcoming"
