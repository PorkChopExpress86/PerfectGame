#!/bin/bash
# setup.sh - Sets up the PerfectGame schedule monitor.
#
# Offers two modes:
#   1. systemd service (recommended) – adaptive daemon with dynamic intervals
#   2. cron (legacy)                  – fixed 10-minute polling
#
# Usage: bash setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python3"
SERVICE_SRC="$SCRIPT_DIR/systemd/perfectgame-monitor.service"
SERVICE_NAME="perfectgame-monitor"

# ── Colours ─────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # No colour

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  PerfectGame Schedule Monitor - Setup${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

# ── Check prerequisites ────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo -e "${YELLOW}Virtual environment not found at .venv/${NC}"
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
fi

echo "Installing / upgrading dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
echo -e "${GREEN}✅ Dependencies installed.${NC}"
echo ""

# ── Check .env ──────────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}⚠️  No .env file found.${NC}"
    echo "   Create $SCRIPT_DIR/.env with:"
    echo "     EMAIL_ADDRESS=you@gmail.com"
    echo "     EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx"
    echo ""
fi

# ── Choose mode ─────────────────────────────────────────────────
echo "How would you like to run the monitor?"
echo ""
echo "  1) systemd service  (recommended)"
echo "     Long-running daemon with adaptive polling intervals."
echo "     Polls faster near game time, slower when games are far away."
echo ""
echo "  2) cron (legacy)"
echo "     Fixed 10-minute polling via cron jobs."
echo ""
read -p "Choose [1/2] (default: 1): " MODE
MODE=${MODE:-1}
echo ""

if [ "$MODE" = "1" ]; then
    # ── systemd service ─────────────────────────────────────────
    echo -e "${GREEN}Setting up systemd service...${NC}"

    # Generate service file with correct paths
    SERVICE_DEST="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
    mkdir -p "$HOME/.config/systemd/user"

    cat > "$SERVICE_DEST" <<EOF
[Unit]
Description=PerfectGame Schedule Monitor Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON $SCRIPT_DIR/adaptive_scheduler.py
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=30

# Games are on weekends; the daemon adapts polling automatically
# and slows down on weekdays to conserve resources.

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME"
    systemctl --user start "$SERVICE_NAME"

    # Enable linger so the user service starts at boot (no login required)
    if ! loginctl show-user "$USER" 2>/dev/null | grep -q 'Linger=yes'; then
        echo "Enabling linger for $USER (service will start on boot)..."
        loginctl enable-linger "$USER"
    fi

    echo ""
    echo -e "${GREEN}✅ systemd user service installed and started!${NC}"
    echo ""
    echo "Useful commands:"
    echo "  systemctl --user status  $SERVICE_NAME   # Check status"
    echo "  systemctl --user stop    $SERVICE_NAME   # Stop"
    echo "  systemctl --user restart $SERVICE_NAME   # Restart"
    echo "  journalctl --user -u $SERVICE_NAME -f    # Follow logs"
    echo "  tail -f $SCRIPT_DIR/monitor.log          # Application log"
    echo ""
    echo "To uninstall:"
    echo "  systemctl --user stop $SERVICE_NAME"
    echo "  systemctl --user disable $SERVICE_NAME"
    echo "  rm $SERVICE_DEST"

elif [ "$MODE" = "2" ]; then
    # ── cron (legacy) ───────────────────────────────────────────
    echo -e "${YELLOW}Setting up cron jobs (10-minute fixed interval)...${NC}"

    MONITOR="$SCRIPT_DIR/schedule_monitor.py"
    CMD="cd $SCRIPT_DIR && $PYTHON $MONITOR >> $SCRIPT_DIR/monitor.log 2>&1"
    CRON_ENTRY="*/10 * * * * $CMD"

    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -qF "schedule_monitor.py"; then
        echo -e "${YELLOW}⚠️  Existing schedule_monitor cron job(s) found:${NC}"
        crontab -l 2>/dev/null | grep "schedule_monitor"
        echo ""
        read -p "Replace them? (y/n): " REPLACE
        if [ "$REPLACE" != "y" ]; then
            echo "Aborted."
            exit 0
        fi
        crontab -l 2>/dev/null | grep -vF "schedule_monitor.py" | crontab -
    fi

    (
      crontab -l 2>/dev/null
      echo "# PerfectGame monitor — every 10 minutes"
      echo "$CRON_ENTRY"
    ) | crontab -

    echo ""
    echo -e "${GREEN}✅ Cron job installed!${NC}"
    echo ""
    echo "Useful commands:"
    echo "  crontab -l                       # View your cron jobs"
    echo "  tail -f $SCRIPT_DIR/monitor.log  # Watch the monitor log"
    echo ""
    echo "Note: cron uses a fixed 10-minute interval."
    echo "For adaptive intervals, re-run this script and choose option 1 (systemd)."
else
    echo -e "${RED}Invalid choice. Exiting.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Setup complete!${NC}"
