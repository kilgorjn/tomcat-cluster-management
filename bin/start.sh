#!/bin/bash
set -e

CONFIG_FILE="/etc/tcm/local-config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Configuration file not found: $CONFIG_FILE"
  echo "Run 'sudo ./scripts/install.sh' first."
  exit 1
fi

# Extract role from config
ROLE=$(grep "^role:" "$CONFIG_FILE" | awk '{print $2}')

if [ "$ROLE" = "console" ]; then
  echo "Starting TCM Console..."
  systemctl start tcm-console
  echo "Console started. Check status with: systemctl status tcm-console"
elif [ "$ROLE" = "agent" ]; then
  echo "Starting TCM Agent..."
  systemctl start tcm-agent
  echo "Agent started. Check status with: systemctl status tcm-agent"
else
  echo "Unknown role in config: $ROLE"
  exit 1
fi
