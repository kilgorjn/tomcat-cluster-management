#!/bin/bash
# Install TCM systemd service files
# Usage: sudo ./systemd/install_systemd.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing TCM systemd service files..."

cp "$SCRIPT_DIR/tcm-console.service" /etc/systemd/system/
cp "$SCRIPT_DIR/tcm-agent.service" /etc/systemd/system/

systemctl daemon-reload

echo "Systemd services installed."
echo ""
echo "To enable and start:"
echo "  Console: sudo systemctl enable --now tcm-console"
echo "  Agent:   sudo systemctl enable --now tcm-agent"
