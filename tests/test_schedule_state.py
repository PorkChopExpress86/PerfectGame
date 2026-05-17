"""
tests/test_schedule_state.py - Tests for schedule/backoff persistence helpers.
"""

import json

from perfect_game.schedule_state import (
    clear_backoff,
    load_schedule,
    save_schedule,
)


def test_load_schedule_returns_empty_for_missing_file(tmp_path):
    assert load_schedule(tmp_path / "missing.json") == []


def test_load_schedule_returns_empty_for_corrupt_json(tmp_path):
    path = tmp_path / "schedule.json"
    path.write_text("{not json")

    assert load_schedule(path) == []


def test_save_and_load_schedule_round_trip(tmp_path):
    path = tmp_path / "schedule.json"
    games = [{"Date": "Apr 26", "Opponent": "RBC-RED"}]

    save_schedule(games, path)

    assert json.loads(path.read_text()) == games
    assert load_schedule(path) == games


def test_clear_backoff_removes_marker(tmp_path):
    path = tmp_path / "backoff.json"
    path.write_text("{}")

    clear_backoff(path)
    assert not path.exists()


def test_clear_backoff_ignores_missing_marker(tmp_path):
    path = tmp_path / "backoff.json"

    clear_backoff(path)

    assert not path.exists()
