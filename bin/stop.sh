#!/bin/bash

CONFIG_FILE="/etc/tcm/local-config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Configuration file not found: $CONFIG_FILE"
  exit 1
fi

ROLE=$(grep "^role:" "$CONFIG_FILE" | awk '{print $2}')

if [ "$ROLE" = "console" ]; then
  echo "Stopping TCM Console..."
  systemctl stop tcm-console
elif [ "$ROLE" = "agent" ]; then
  echo "Stopping TCM Agent..."
  systemctl stop tcm-agent
else
  echo "Unknown role: $ROLE"
  exit 1
fi
