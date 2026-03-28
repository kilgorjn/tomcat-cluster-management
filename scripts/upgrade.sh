#!/bin/bash
set -e

# TCM Upgrade Script
# Usage: sudo ./scripts/upgrade.sh /opt/tcm

if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root"
  exit 1
fi

INSTALL_DIR="${1:-/opt/tcm}"
CONFIG_DIR="/etc/tcm"
BACKUP_SUFFIX=$(date +%Y%m%d%H%M%S)

echo "TCM Upgrade Script"
echo "==================="
echo "Install directory: $INSTALL_DIR"
echo "Config directory:  $CONFIG_DIR"
echo ""

# 1. Back up existing installation
echo "Backing up current installation..."
if [ -d "$CONFIG_DIR" ]; then
  cp -r "$CONFIG_DIR" "${CONFIG_DIR}.bak.${BACKUP_SUFFIX}"
  echo "  Config backed up to: ${CONFIG_DIR}.bak.${BACKUP_SUFFIX}"
fi

if [ -d "$INSTALL_DIR" ]; then
  cp -r "$INSTALL_DIR" "${INSTALL_DIR}.bak.${BACKUP_SUFFIX}"
  echo "  Install dir backed up to: ${INSTALL_DIR}.bak.${BACKUP_SUFFIX}"
fi

# 2. Determine role from config
ROLE=$(grep "^role:" "$CONFIG_DIR/local-config.yaml" 2>/dev/null | awk '{print $2}')
if [ -z "$ROLE" ]; then
  echo "Could not determine role from config. Aborting."
  exit 1
fi
echo "Detected role: $ROLE"

# 3. Stop service
echo "Stopping TCM $ROLE service..."
systemctl stop "tcm-$ROLE" 2>/dev/null || true

# 4. Copy new files (preserve venv and config)
echo "Copying new files..."
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
for dir in bin console agent shared systemd scripts; do
  if [ -d "$SCRIPT_DIR/$dir" ]; then
    cp -r "$SCRIPT_DIR/$dir" "$INSTALL_DIR/"
  fi
done

# 5. Update pip dependencies
echo "Updating dependencies..."
source "$INSTALL_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$INSTALL_DIR/console/requirements.txt"
pip install -r "$INSTALL_DIR/agent/requirements.txt"

# 6. Update systemd service files
cp "$INSTALL_DIR/systemd/tcm-console.service" /etc/systemd/system/
cp "$INSTALL_DIR/systemd/tcm-agent.service" /etc/systemd/system/
systemctl daemon-reload

# 7. Set permissions
chmod 755 "$INSTALL_DIR/bin"/*.sh 2>/dev/null || true

# 8. Start service
echo "Starting TCM $ROLE service..."
systemctl start "tcm-$ROLE"

# 9. Verify health
echo "Verifying health..."
sleep 3

if [ "$ROLE" = "console" ]; then
  PORT=$(grep "port:" "$CONFIG_DIR/local-config.yaml" | head -1 | awk '{print $2}')
  PORT=${PORT:-9000}
  if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
    echo "Console is healthy!"
  else
    echo "WARNING: Console health check failed. Check logs: journalctl -u tcm-console"
  fi
elif [ "$ROLE" = "agent" ]; then
  PORT=$(grep "port:" "$CONFIG_DIR/local-config.yaml" | head -1 | awk '{print $2}')
  PORT=${PORT:-9001}
  if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
    echo "Agent is healthy!"
  else
    echo "WARNING: Agent health check failed. Check logs: journalctl -u tcm-agent"
  fi
fi

echo ""
echo "Upgrade complete!"
echo "Previous installation backed up to: ${INSTALL_DIR}.bak.${BACKUP_SUFFIX}"
