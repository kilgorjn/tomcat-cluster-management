# TCM - Tomcat Cluster Manager

A centralized orchestration and lifecycle management system for production Tomcat deployments across distributed node clusters. TCM provides deployment automation, cluster policy enforcement (min/max instance scaling), and unified monitoring across a 30-node infrastructure running 300+ Tomcat instances organized into 10 logical clusters.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│         Harness CI/CD Platform                      │
│  (WAR staging, deployment triggers)                 │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌─────────────────┐    ┌──────────────────────┐
│  Manager Console│    │  Static Content      │
│  (REST API)     │    │  (4 Web Server Hosts)│
│  Port: 9000     │    │  Port: 8080-8089     │
└────────┬────────┘    └──────────┬───────────┘
         │                        │
         │   ┌────────────────────┘
         │   │
         ▼   ▼
    ┌─────────────────────────────────┐
    │  30 Node Agents                 │
    │  Port: 9001 (REST API)          │
    │  Direct Tomcat Process Mgmt     │
    └────────┬────────────────────────┘
             │
    ┌────────┴──────────┐
    │                   │
    ▼                   ▼
  300 Tomcat Instances  mod_jk Load Balancing
  (1 WAR each)         (Sticky Sessions)
```

### Components

- **Console Manager** (`console/`): Central orchestrator with REST API (port 9000). Manages cluster topology, coordinates deployments, and monitors node status.
- **Node Agent** (`agent/`): Per-node service (port 9001) that manages local Tomcat instances — start/stop/deploy/health check.
- **Shared** (`shared/`): Common utilities, configuration loading, and constants.

## Quick Start

### Prerequisites

- Python 3.8+
- pip (Python package manager)
- systemd (for service management)

### Installation

```bash
# Extract package
tar -xzf tcm-1.0.0.tar.gz
cd tcm-1.0.0

# Run interactive installation
sudo ./scripts/install.sh
```

### Development Setup

```bash
# Clone the repository
git clone <repo-url>
cd tomcat-cluster-management

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r console/requirements.txt
pip install -r agent/requirements.txt
pip install pytest

# Run tests
pytest tests/ -v

# Start console (development mode)
CONFIG_PATH=config/local-config.yaml python -m console.app

# Start agent (development mode)
CONFIG_PATH=agent/config/agent.yaml.example python -m agent.app
```

## API Endpoint Reference

### Console Manager (Port 9000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/clusters` | List all clusters |
| `GET` | `/clusters/{id}` | Get cluster details |
| `POST` | `/clusters/{id}/policy` | Update cluster policy |
| `POST` | `/clusters/{id}/stop-all` | Stop all instances in cluster |
| `POST` | `/clusters/{id}/start-all` | Start instances to min_instances |
| `GET` | `/clusters/{id}/status` | Cluster status summary |
| `POST` | `/clusters/{id}/deploy` | Trigger deployment |
| `GET` | `/clusters/{id}/deployments/{did}` | Deployment status |
| `POST` | `/clusters/{id}/rollback` | Rollback to previous version |
| `GET` | `/nodes` | List all nodes |
| `GET` | `/nodes/{id}/status` | Node status |
| `GET` | `/nodes/{id}/tomcats/{app}/status` | Tomcat instance status |
| `POST` | `/nodes/{id}/tomcats/{app}/start` | Start Tomcat instance |
| `POST` | `/nodes/{id}/tomcats/{app}/stop` | Stop Tomcat instance |
| `POST` | `/nodes/{id}/tomcats/{app}/restart` | Restart Tomcat instance |
| `GET` | `/health` | Console health check |
| `GET` | `/status` | System status summary |

### Node Agent (Port 9001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/nodes/{id}/status` | All Tomcats on this node |
| `GET` | `/nodes/{id}/tomcats/{app}/status` | Specific Tomcat status |
| `POST` | `/nodes/{id}/tomcats/{app}/start` | Start Tomcat |
| `POST` | `/nodes/{id}/tomcats/{app}/stop` | Stop Tomcat |
| `POST` | `/nodes/{id}/tomcats/{app}/deploy` | Deploy WAR file |
| `GET` | `/health` | Agent health check |

## Configuration

### Console Configuration (`/etc/tcm/local-config.yaml`)

```yaml
role: console
version: 1.0

console:
  host: 0.0.0.0
  port: 9000
  config_root: /etc/tcm
  log_dir: /var/log/tcm

logging:
  level: INFO
  format: json

policy_enforcement:
  enabled: true
  check_interval: 30
  node_timeout: 10

deployment:
  staging_dir: /opt/tcm/staging
  max_parallel_nodes: 10
  health_check_timeout: 10
  startup_timeout: 60
```

### Agent Configuration (`/etc/tcm/local-config.yaml`)

```yaml
role: agent
version: 1.0

agent:
  node_id: node-1
  port: 9001
  tomcat_root: /opt/tomcats
  log_dir: /var/log/tcm

logging:
  level: INFO
  format: json

tomcat:
  graceful_stop_timeout: 30
  startup_timeout: 60
  health_check_timeout: 10

process_management:
  pid_dir: /var/run/tcm
```

### Cluster Configuration (`/etc/tcm/clusters/cluster-1.yaml`)

```yaml
cluster_id: cluster-1
app_id: app-a
app_path: /opt/tomcats/app-a
policy:
  mode: AUTO
  min_instances: 5
  max_instances: 10
nodes:
  - node-1
  - node-2
  - node-3
deployment:
  graceful_stop_timeout: 30
  startup_timeout: 60
  health_check_endpoint: /health
current_version: v1.0.0
```

### Node Configuration (`/etc/tcm/nodes/node-1.yaml`)

```yaml
node_id: node-1
hostname: tomcat-node-1.internal
ip_address: 192.168.1.10
agent_port: 9001
tomcats:
  - app_id: app-a
    instance_port: 9001
    ajp_port: 8009
    status: running
    version: v1.0.0
```

## Deployment Workflow

1. Set cluster to MANUAL mode: `POST /clusters/{id}/policy {"mode": "MANUAL"}`
2. Stop all instances: `POST /clusters/{id}/stop-all`
3. Stage WAR file to `/opt/tcm/staging/{cluster-id}/{app-id}/app.war`
4. Trigger deployment: `POST /clusters/{id}/deploy {"war_path": "...", "version": "v1.2.3"}`
5. Poll status: `GET /clusters/{id}/deployments/{deployment-id}`
6. Re-enable AUTO mode: `POST /clusters/{id}/policy {"mode": "AUTO"}`

## Security

Phase 0 (MVP): HTTP-only, no authentication, internal network assumed. See `docs/TCM_SECURITY_REQUIREMENTS.md` for the security roadmap.

## Project Structure

```
tcm-1.0.0/
├── bin/                    # Startup/management scripts
├── console/                # Manager Console service
│   ├── api/                # REST API routers
│   ├── models/             # Pydantic data models
│   ├── services/           # Business logic services
│   └── config/             # Example configs
├── agent/                  # Node Agent service
│   └── config/             # Example configs
├── shared/                 # Common utilities
├── systemd/                # Systemd service files
├── scripts/                # Install/upgrade/uninstall
├── config/                 # Default configuration
├── tests/                  # Test suite
└── docs/                   # Design & security docs
```
