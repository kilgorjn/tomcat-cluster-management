#!/bin/bash
# TCM Configuration Initialization Script
# Creates sample cluster and node configs in /etc/tcm/

CONFIG_DIR="${1:-/etc/tcm}"

echo "TCM Configuration Initialization"
echo "================================="
echo "Config directory: $CONFIG_DIR"
echo ""

# Create directories
mkdir -p "$CONFIG_DIR/clusters"
mkdir -p "$CONFIG_DIR/nodes"

# Create sample cluster config
cat > "$CONFIG_DIR/clusters/cluster-1.yaml" <<EOF
cluster_id: cluster-1
app_id: app-a
app_path: /opt/tomcats/app-a
policy:
  mode: AUTO
  min_instances: 5
  max_instances: 10
  policy_check_interval: 30
nodes:
  - node-1
  - node-2
  - node-3
  - node-4
  - node-5
  - node-6
  - node-7
  - node-8
  - node-9
  - node-10
deployment:
  graceful_stop_timeout: 30
  startup_timeout: 60
  health_check_endpoint: /health
  health_check_timeout: 10
current_version: v1.0.0
EOF

# Create sample node config
cat > "$CONFIG_DIR/nodes/node-1.yaml" <<EOF
node_id: node-1
hostname: tomcat-node-1.internal
ip_address: 192.168.1.10
agent_port: 9001
tomcats:
  - app_id: app-a
    instance_port: 9001
    ajp_port: 8009
    status: stopped
    version: v1.0.0
EOF

echo "Sample configurations created:"
echo "  $CONFIG_DIR/clusters/cluster-1.yaml"
echo "  $CONFIG_DIR/nodes/node-1.yaml"
echo ""
echo "Edit these files to match your environment."
