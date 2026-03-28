#!/bin/bash
# TCM Interactive Configuration Wizard
# Generates /etc/tcm/local-config.yaml

CONFIG_DIR="/etc/tcm"
CONFIG_FILE="$CONFIG_DIR/local-config.yaml"

echo "TCM Configuration Wizard"
echo "========================"
echo ""

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root (sudo)"
  exit 1
fi

# Create config directory
mkdir -p "$CONFIG_DIR"

# Determine role
echo "Select the role for this host:"
echo "  1) console - Manager Console (central orchestrator)"
echo "  2) agent   - Node Agent (manages local Tomcats)"
echo ""
read -p "Role (1 or 2): " role_choice

case "$role_choice" in
  1|console)
    ROLE="console"
    ;;
  2|agent)
    ROLE="agent"
    ;;
  *)
    echo "Invalid choice. Exiting."
    exit 1
    ;;
esac

echo ""
echo "Configuring as: $ROLE"
echo ""

if [ "$ROLE" = "console" ]; then
  read -p "Listen host (default 0.0.0.0): " host
  host=${host:-0.0.0.0}

  read -p "Listen port (default 9000): " port
  port=${port:-9000}

  read -p "Config root directory (default /etc/tcm): " config_root
  config_root=${config_root:-/etc/tcm}

  read -p "Log directory (default /var/log/tcm): " log_dir
  log_dir=${log_dir:-/var/log/tcm}

  read -p "Log level (default INFO): " log_level
  log_level=${log_level:-INFO}

  read -p "Staging directory (default /opt/tcm/staging): " staging_dir
  staging_dir=${staging_dir:-/opt/tcm/staging}

  read -p "Max parallel nodes for deployment (default 10): " max_parallel
  max_parallel=${max_parallel:-10}

  cat > "$CONFIG_FILE" <<EOF
role: console
version: 1.0

console:
  host: $host
  port: $port
  config_root: $config_root
  log_dir: $log_dir

logging:
  level: $log_level
  format: json

policy_enforcement:
  enabled: true
  check_interval: 30
  node_timeout: 10

deployment:
  staging_dir: $staging_dir
  max_parallel_nodes: $max_parallel
  health_check_timeout: 10
  startup_timeout: 60
EOF

  # Create subdirectories
  mkdir -p "$config_root/clusters"
  mkdir -p "$config_root/nodes"
  mkdir -p "$log_dir"
  mkdir -p "$staging_dir"

  echo ""
  echo "Console configuration saved to: $CONFIG_FILE"
  echo "Create cluster configs in: $config_root/clusters/"
  echo "Create node configs in: $config_root/nodes/"

elif [ "$ROLE" = "agent" ]; then
  read -p "Node ID (e.g., node-1): " node_id
  if [ -z "$node_id" ]; then
    echo "Node ID is required."
    exit 1
  fi

  read -p "Agent port (default 9001): " port
  port=${port:-9001}

  read -p "Tomcat root path (default /opt/tomcats): " tomcat_root
  tomcat_root=${tomcat_root:-/opt/tomcats}

  read -p "Log directory (default /var/log/tcm): " log_dir
  log_dir=${log_dir:-/var/log/tcm}

  read -p "Log level (default INFO): " log_level
  log_level=${log_level:-INFO}

  read -p "PID directory (default /var/run/tcm): " pid_dir
  pid_dir=${pid_dir:-/var/run/tcm}

  cat > "$CONFIG_FILE" <<EOF
role: agent
version: 1.0

agent:
  node_id: $node_id
  port: $port
  tomcat_root: $tomcat_root
  log_dir: $log_dir

logging:
  level: $log_level
  format: json

tomcat:
  graceful_stop_timeout: 30
  startup_timeout: 60
  health_check_timeout: 10
  max_concurrent_deploys: 3

process_management:
  pid_dir: $pid_dir
  enable_monitoring: true
EOF

  # Create directories
  mkdir -p "$log_dir"
  mkdir -p "$pid_dir"

  echo ""
  echo "Agent configuration saved to: $CONFIG_FILE"
fi

echo ""
echo "Configuration complete! Start the service with:"
echo "  sudo bin/start.sh"
