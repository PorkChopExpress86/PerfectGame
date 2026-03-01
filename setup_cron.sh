#!/bin/bash
# setup_cron.sh - Sets up cron jobs to run schedule_monitor.py.
#
# Schedule:
#   Saturday 7:30 PM – midnight : every 5 minutes  (game night intense monitoring)
#   All other times             : every 10 minutes
#
# Usage: bash setup_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python3"
MONITOR="$SCRIPT_DIR/schedule_monitor.py"

# Fall back to system python if no venv found
if [ ! -f "$PYTHON" ]; then
    PYTHON="$(which python3)"
fi

CMD="cd $SCRIPT_DIR && $PYTHON $MONITOR >> $SCRIPT_DIR/monitor.log 2>&1"

# ── Cron entries ────────────────────────────────────────────────
# Saturday 7:00–7:20 PM  (10-min slots before the 5-min window kicks in)
CRON_SAT_PRE_A="0,10,20 19 * * 6 $CMD"
# Saturday 7:30 PM – 7:59 PM  (every 5 min, starting at :30)
CRON_SAT_INTENSE_A="30,35,40,45,50,55 19 * * 6 $CMD"
# Saturday 8:00 PM – 11:59 PM  (every 5 min)
CRON_SAT_INTENSE_B="*/5 20-23 * * 6 $CMD"
# Saturday midnight – 6:59 PM  (every 10 min, outside the game window)
CRON_SAT_OFF="*/10 0-18 * * 6 $CMD"
# Sun–Fri all day  (every 10 min)
CRON_OTHER="*/10 * * * 0-5 $CMD"

echo "=========================================="
echo "  PerfectGame Schedule Monitor - Cron Setup"
echo "=========================================="
echo ""
echo "Script dir:  $SCRIPT_DIR"
echo "Python:      $PYTHON"
echo "Monitor:     $MONITOR"
echo ""
echo "Schedule:"
echo "  Saturday 7:30 PM – midnight  →  every  5 min (game night)"
echo "  All other times              →  every 10 min"
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
  echo "# PerfectGame monitor — Sat 7:30 PM-midnight every 5 min, otherwise every 10 min"
  echo "$CRON_SAT_PRE_A"
  echo "$CRON_SAT_INTENSE_A"
  echo "$CRON_SAT_INTENSE_B"
  echo "$CRON_SAT_OFF"
  echo "$CRON_OTHER"
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
