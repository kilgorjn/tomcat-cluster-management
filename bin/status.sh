#!/bin/bash

CONFIG_FILE="/etc/tcm/local-config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Configuration file not found: $CONFIG_FILE"
  exit 1
fi

ROLE=$(grep "^role:" "$CONFIG_FILE" | awk '{print $2}')

if [ "$ROLE" = "console" ]; then
  systemctl status tcm-console
elif [ "$ROLE" = "agent" ]; then
  systemctl status tcm-agent
else
  echo "Unknown role: $ROLE"
  exit 1
fi
