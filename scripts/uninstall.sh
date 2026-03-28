#!/bin/bash
# Stops services, removes systemd units, leaves config/data intact (backup first!)

read -p "This will uninstall TCM. Continue? (y/n): " confirm
if [ "$confirm" != "y" ]; then exit 0; fi

# Stop services
systemctl stop tcm-console tcm-agent 2>/dev/null || true

# Disable auto-start
systemctl disable tcm-console tcm-agent 2>/dev/null || true

# Remove systemd units
rm -f /etc/systemd/system/tcm-console.service
rm -f /etc/systemd/system/tcm-agent.service
systemctl daemon-reload

# Remove install directory
rm -rf /opt/tcm

echo "TCM uninstalled."
echo "Config preserved at /etc/tcm (backup before deleting)"
echo "Logs preserved at /var/log/tcm"
