#!/bin/bash
# setup_cron.sh - Sets up cron jobs to run schedule_monitor.py.
#
# Schedule:
#   Thursday through Sunday: every 10 minutes
#
# Usage: bash setup_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python3"
MONITOR="$SCRIPT_DIR/perfect_game/schedule_monitor.py"

# Fall back to system python if no venv found
if [ ! -f "$PYTHON" ]; then
    PYTHON="$(which python3)"
fi

CMD="cd $SCRIPT_DIR && $PYTHON $MONITOR >> $SCRIPT_DIR/monitor.log 2>&1"

# ── Cron entries ────────────────────────────────────────────────
CRON_PG="*/10 * * * 4-6,0 $CMD"

echo "=========================================="
echo "  PerfectGame Schedule Monitor - Cron Setup"
echo "=========================================="
echo ""
echo "Script dir:  $SCRIPT_DIR"
echo "Python:      $PYTHON"
echo "Monitor:     $MONITOR"
echo ""
echo "Schedule:"
echo "  Thursday through Sunday      →  every 10 min"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -qF "schedule_monitor.py"; then
    echo "⚠️  Existing schedule_monitor cron job(s) found:"
    crontab -l 2>/dev/null | grep "schedule_monitor"
    echo ""
    read -p "Replace them? (y/n): " REPLACE
    if [ "$REPLACE" != "y" ]; then
        echo "Aborted."
        exit 0
    fi
    # Remove existing entries
    crontab -l 2>/dev/null | grep -vF "schedule_monitor.py" | crontab -
fi

# Add the new cron jobs
(
  crontab -l 2>/dev/null
  echo "# PerfectGame monitor — every 10 minutes Thu-Sun"
  echo "$CRON_PG"
) | crontab -

echo ""
echo "✅ Cron jobs installed!"
echo ""
echo "Useful commands:"
echo "  crontab -l                       # View your cron jobs"
echo "  tail -f $SCRIPT_DIR/monitor.log  # Watch the monitor log"
echo "  crontab -e                       # Edit cron jobs manually"
echo ""
echo "To remove the cron jobs later:"
echo "  crontab -l | grep -v schedule_monitor.py | crontab -"
