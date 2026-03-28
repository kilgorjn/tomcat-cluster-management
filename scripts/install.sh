#!/bin/bash
set -e

echo "TCM Installation Script"
echo "======================"

# Detect if running as root
if [ "$EUID" -ne 0 ]; then 
  echo "This script must be run as root"
  exit 1
fi

INSTALL_DIR="/opt/tcm"
CONFIG_DIR="/etc/tcm"
LOG_DIR="/var/log/tcm"

# 1. Create tcm system user and group
if ! getent group tcm > /dev/null 2>&1; then
  echo "Creating tcm group..."
  groupadd --system tcm
fi

if ! getent passwd tcm > /dev/null 2>&1; then
  echo "Creating tcm system user..."
  useradd --system --gid tcm --no-create-home --shell /usr/sbin/nologin tcm
fi

# 2. Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"

# 2. Copy package to install directory
cp -r . "$INSTALL_DIR/"
cd "$INSTALL_DIR"

# 3. Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 4. Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r console/requirements.txt
pip install -r agent/requirements.txt

# 5. Determine host role
echo ""
echo "Host Configuration"
echo "=================="
read -p "What is the role of this host? (console/agent): " role

if [ "$role" != "console" ] && [ "$role" != "agent" ]; then
  echo "Invalid role. Must be 'console' or 'agent'."
  exit 1
fi

# 6. Generate configuration file
if [ "$role" = "console" ]; then
  echo "Configuring console host..."
  read -p "Manager port (default 9000): " mgr_port
  mgr_port=${mgr_port:-9000}
  read -p "Manager hostname (default localhost): " mgr_host
  mgr_host=${mgr_host:-localhost}
  
  cat > "$CONFIG_DIR/local-config.yaml" <<EOF
role: console
console:
  host: $mgr_host
  port: $mgr_port
  config_root: $CONFIG_DIR
  log_dir: $LOG_DIR
EOF

elif [ "$role" = "agent" ]; then
  echo "Configuring agent host..."
  read -p "Node ID (e.g., node-1): " node_id
  read -p "Agent port (default 9001): " agent_port
  agent_port=${agent_port:-9001}
  read -p "Tomcat root path (default /opt/tomcats): " tomcat_root
  tomcat_root=${tomcat_root:-/opt/tomcats}
  
  cat > "$CONFIG_DIR/local-config.yaml" <<EOF
role: agent
agent:
  node_id: $node_id
  port: $agent_port
  tomcat_root: $tomcat_root
  log_dir: $LOG_DIR
EOF
fi

# 7. Install systemd services
echo "Installing systemd services..."
sudo cp systemd/tcm-console.service /etc/systemd/system/
sudo cp systemd/tcm-agent.service /etc/systemd/system/
sudo systemctl daemon-reload

# 8. Set permissions
chown -R tcm:tcm "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" 2>/dev/null || true
chmod 750 "$CONFIG_DIR"
chmod 755 "$INSTALL_DIR/bin"/*.sh

# 9. Start service
echo ""
echo "Installation complete!"
echo "Starting TCM $role service..."

if [ "$role" = "console" ]; then
  systemctl start tcm-console
  echo "Console started on port $mgr_port"
  echo "Access at: http://$mgr_host:$mgr_port"
else
  systemctl start tcm-agent
  echo "Agent started on port $agent_port (node: $node_id)"
fi

echo "Enable auto-start: systemctl enable tcm-$role"
