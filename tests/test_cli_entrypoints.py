"""
tests/test_cli_entrypoints.py - Tests for direct script entrypoints.
"""

import subprocess
import sys


def test_schedule_daemon_help_runs_when_executed_as_script():
    result = subprocess.run(
        [sys.executable, "perfect_game/schedule_daemon.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "PerfectGame schedule monitor daemon" in result.stdout
