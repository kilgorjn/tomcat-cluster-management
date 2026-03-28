# TCM (Tomcat Cluster Manager)
## Requirements and Architecture Document

---

## 1. Executive Summary

The Tomcat Cluster Manager (TCM) is a centralized orchestration and lifecycle management system for production Tomcat deployments across distributed node clusters. It provides deployment automation, cluster policy enforcement (min/max instance scaling), and unified monitoring across a 30-node infrastructure running 300+ Tomcat instances organized into 10 logical clusters.

The system integrates with Harness for WAR file staging and deployment coordination, mod_jk-based load balancing for traffic routing, and custom REST APIs for programmatic control of cluster state.

---

## 2. System Overview

### 2.1 Infrastructure Baseline

| Component | Specification |
|-----------|---------------|
| **Total Nodes** | 30 physical/virtual nodes |
| **Tomcat Instances** | 300 (10 per node average) |
| **Clusters** | 10 logical clusters |
| **Web Server Hosts** | 4 redundant hosts |
| **Configuration** | File-based (Git-tracked YAML) |
| **Deployment Orchestrator** | Harness CI/CD |

### 2.2 High-Level Architecture

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

---

## 3. Deployment Architecture

### 3.1 Cluster Structure

Each cluster is a logical grouping of Tomcat instances across multiple nodes:

```
Cluster-1 (min=5, max=10, current=8)
├─ node-1: tomcat-app-a (running)
├─ node-2: tomcat-app-a (running)
├─ node-3: tomcat-app-a (running)
├─ node-4: tomcat-app-a (running)
├─ node-5: tomcat-app-a (running)
├─ node-6: tomcat-app-a (stopped - policy constraint)
├─ node-7: tomcat-app-a (stopped - policy constraint)
├─ node-8: tomcat-app-a (running)
├─ node-9: tomcat-app-a (running)
└─ node-10: tomcat-app-a (stopped - policy constraint)
```

**Key characteristics:**
- All nodes in a cluster run the same WAR (same app version)
- Policy controls how many are active (running vs. stopped)
- Deployment applies to all nodes simultaneously
- WAR persists on disk after stop; only process is killed

### 3.2 Tomcat Instance Organization

Per node (e.g., node-1):

```
/opt/tomcats/
├── app-a/
│   ├── conf/
│   ├── webapps/
│   │   └── app.war (current version)
│   │   └── app.war.1 (backup v-1)
│   │   └── app.war.2 (backup v-2)
│   ├── logs/
│   └── work/
├── app-b/
│   ├── conf/
│   ├── webapps/
│   │   └── app.war
│   ├── logs/
│   └── work/
└── app-c/
    └── ...
```

**Each Tomcat instance:**
- Has isolated `CATALINA_BASE` directory
- Runs as separate Java process (direct process management, no supervisor)
- Maintains versioned WAR backups for quick rollback
- Listens on unique port (9001, 9002, 9003, etc.)
- Exposes AJP port for mod_jk communication (8009 base + instance offset)

---

## 4. Manager Console Architecture

### 4.1 Manager Service

**Technology Stack:**
- Python 3.8+
- FastAPI (REST framework)
- APScheduler (policy enforcement loop)
- File-based config (YAML, Git-tracked)
- In-memory state with periodic persistence

**Deployment:**
- Single service on manager console server
- Port: 9000
- Systemd service: `tomcat-cluster-manager.service`

### 4.2 Manager Responsibilities

1. **Configuration Management**
   - Read/write cluster configs (YAML files)
   - Track cluster membership (which nodes, which apps)
   - Policy definitions (min/max Tomcats per cluster)
   - Version history and Git tracking

2. **Deployment Orchestration**
   - Receive WAR from Harness
   - Distribute WAR to all node agents in target cluster
   - Coordinate sequential deployment steps
   - Validate health checks
   - Report deployment status

3. **Policy Enforcement**
   - Periodic loop (default: 30s interval)
   - Poll all nodes for running Tomcat count per cluster
   - Enforce min/max constraints
   - Issue start/stop commands to node agents
   - Handle manual override (MANUAL vs. AUTO mode)

4. **Monitoring & Observability**
   - Aggregate status from all 300 Tomcats
   - Track deployment history
   - Health check results
   - Node connectivity status
   - API for dashboard/alerting integration

### 4.3 Configuration Storage

**Directory structure:**

```
/etc/cluster-manager/
├── .git/                          # Git repository for audit trail
├── config.yaml                    # Global manager config
├── clusters/
│   ├── cluster-1.yaml
│   ├── cluster-2.yaml
│   └── ...
├── nodes/
│   ├── node-1.yaml
│   ├── node-2.yaml
│   └── ...
└── deployments/                   # History log
    └── deployment-2024-01-15.log
```

**Cluster config example (cluster-1.yaml):**

```yaml
cluster_id: cluster-1
app_id: app-a
app_path: /opt/tomcats/app-a
policy:
  mode: AUTO                    # AUTO or MANUAL
  min_instances: 5
  max_instances: 10
  policy_check_interval: 30     # seconds
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
  graceful_stop_timeout: 30     # seconds
  startup_timeout: 60           # seconds
  health_check_endpoint: /health
  health_check_timeout: 10      # seconds
current_version: v1.2.3
```

**Node config example (node-1.yaml):**

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
    version: v1.2.3
  - app_id: app-b
    instance_port: 9002
    ajp_port: 8010
    status: stopped
    version: v1.1.0
  - app_id: app-c
    instance_port: 9003
    ajp_port: 8011
    status: running
    version: v2.0.0
```

---

## 5. Node Agent Architecture

### 5.1 Node Agent Service

**Technology Stack:**
- Python 3.8+
- FastAPI (REST API server)
- Direct Java process management (subprocess, no supervisor)
- Port: 9001 (configurable per node)

**Deployment:**
- One agent per node (handles all 10 Tomcats on that node)
- Systemd service: `tomcat-node-agent.service`
- Starts on boot, auto-restart on failure

### 5.2 Agent Responsibilities

1. **Tomcat Lifecycle Control**
   - Start/stop individual Tomcat process by `app_id`
   - Graceful shutdown: unload WAR context, then terminate process
   - Monitor process state (running, stopped, crashed)
   - PID file tracking: `/var/run/tomcat-{app-id}.pid`

2. **Deployment Execution**
   - Receive WAR from manager via HTTP PUT/POST
   - Store WAR locally: `/opt/tomcats/{app_id}/webapps/app.war`
   - Backup previous WAR: `app.war.1`, `app.war.2`, etc.
   - Execute deployment steps:
     1. Gracefully stop Tomcat (via `catalina.sh stop`)
     2. Backup current WAR
     3. Deploy new WAR to webapps/
     4. Start Tomcat
     5. Wait for health check (configurable timeout)
     6. Report success/failure

3. **Health Monitoring**
   - Periodic health checks on each Tomcat (GET to `/health` endpoint)
   - Report process status (running, stopped, unhealthy)
   - Log failures for troubleshooting

4. **Status Reporting**
   - Respond to manager polls with current state
   - Report per-Tomcat: running/stopped, version, health status
   - Report node-level metrics: CPU, memory, disk space (optional)

### 5.3 Agent REST Endpoints

**Command polling (manager → agent):**
```
GET /nodes/{node-id}/commands
Response: { "commands": [{"id": "cmd-123", "action": "deploy", "app_id": "app-a", ...}] }
```

**Tomcat control:**
```
POST /nodes/{node-id}/tomcats/{app-id}/start
POST /nodes/{node-id}/tomcats/{app-id}/stop
POST /nodes/{node-id}/tomcats/{app-id}/deploy
  { "war_bytes": <binary>, "version": "v1.2.3" }
GET /nodes/{node-id}/tomcats/{app-id}/status
  Response: { "status": "running", "version": "v1.2.3", "health": "healthy" }
```

**Status reporting:**
```
GET /nodes/{node-id}/status
Response: { 
  "node_id": "node-1",
  "tomcats": {
    "app-a": { "status": "running", "version": "v1.2.3", "pid": 1234, "health": "healthy" },
    "app-b": { "status": "stopped", "version": "v1.1.0", "health": "offline" }
  }
}
```

---

## 6. Deployment Workflow

### 6.1 Deployment Phases

**Pre-deployment:**
```
1. Operations: Set cluster policy to MANUAL
   - POST /clusters/{cluster-id}/policy { "mode": "MANUAL" }
   - Disables auto-scaling until re-enabled

2. Operations: Stop all Tomcats in cluster
   - POST /clusters/{cluster-id}/stop-all
   - Manager sends "stop" command to all node agents
   - Each agent gracefully stops Tomcat process (catalina.sh stop)
   - Waits for all agents to confirm stopped
```

**Harness integration:**
```
3. Harness: Stage WAR
   - Harness downloads/builds WAR file
   - Lands on manager console: /opt/cluster-manager/staging/{cluster-id}/{app-id}/app.war
   - (Path configurable)

4. Harness: Trigger manager deployment
   - POST /clusters/{cluster-id}/deploy
   - { "war_path": "/opt/cluster-manager/staging/cluster-1/app-a/app.war", 
       "version": "v1.2.3" }
```

**Manager orchestration:**
```
5. Manager: Push WAR to all nodes
   - Reads WAR from staging path
   - For each node in cluster:
     a) Sends WAR bytes to node agent via POST /nodes/{node-id}/tomcats/{app-id}/deploy
     b) Waits for agent confirmation (WAR received)
   - Once all nodes confirm WAR received, proceeds to next phase

6. Manager: Deploy WAR on all nodes
   - Sends "deploy" command to all node agents
   - Each agent:
     a) Backs up old WAR (versioning)
     b) Deploys new WAR to webapps/
     c) Starts Tomcat
     d) Performs health check (GET /health, timeout 10s)
     e) Reports success/failure
   - Waits for all agents to complete

7. Manager: Validate deployment
   - Checks all nodes reported success
   - If any node fails:
     - Rolls back remaining nodes (restore previous WAR, restart)
     - Aborts deployment
     - Reports error to Harness
   - If all succeed, deployment complete
```

**Post-deployment:**
```
8. Operations: Re-enable cluster policy
   - POST /clusters/{cluster-id}/policy { "mode": "AUTO" }
   - Policy enforcement loop kicks in
   - Scales up to min_instances (if any Tomcats are stopped)
   - Cluster is now fully operational
```

### 6.2 Graceful Tomcat Shutdown

**Process:**
```bash
# Agent executes on node:
1. catalina.sh stop
   - Tomcat unloads WAR context
   - Existing requests are allowed to complete
   - Process waits up to 30 seconds for graceful shutdown
2. If process still running after timeout:
   - kill -TERM <pid>
3. If still running after 5 more seconds:
   - kill -9 <pid> (force kill)
```

---

## 7. Cluster Policy Enforcement

### 7.1 Policy Loop

**Execution (background task):**
- Runs every 30 seconds (configurable)
- Executes only if policy mode is AUTO
- Non-blocking (doesn't wait for previous iteration)

**Algorithm:**

```python
def enforce_policies():
    for cluster in all_clusters:
        if cluster.policy.mode != AUTO:
            continue
        
        # Poll all nodes in cluster
        running_count = 0
        stopped_tomcats = []
        for node in cluster.nodes:
            status = poll_node_agent(node)
            for tomcat in status.tomcats:
                if tomcat.is_running:
                    running_count += 1
                else:
                    stopped_tomcats.append((node, tomcat))
        
        # Enforce constraints
        min_required = cluster.policy.min_instances
        max_allowed = cluster.policy.max_instances
        
        if running_count < min_required:
            # Need to start more
            deficit = min_required - running_count
            for i in range(deficit):
                node, tomcat = stopped_tomcats[i]
                send_start_command(node, tomcat)
        
        elif running_count > max_allowed:
            # Need to stop some
            excess = running_count - max_allowed
            for i in range(excess):
                node, tomcat = get_running_tomcats(cluster)[i]
                send_stop_command(node, tomcat)
```

### 7.2 Manual Override

Operations can temporarily disable policy enforcement:

```
POST /clusters/{cluster-id}/policy
{
  "mode": "MANUAL"
}
```

In MANUAL mode:
- Policy loop skips the cluster
- Operations must explicitly issue start/stop commands
- Example: before deployment, set to MANUAL, stop all, deploy, set to AUTO

---

## 8. Load Balancing & Traffic Routing

### 8.1 Web Server Architecture

**4 redundant web server hosts** (e.g., web-1, web-2, web-3, web-4):

Each host runs **multiple mod_jk instances** (one per cluster):

```
web-1.example.com
├─ Apache instance 1 (port 8080) → cluster-1 → nodes [1,2,3,4,5]
├─ Apache instance 2 (port 8081) → cluster-2 → nodes [1,2,3,4,5]
├─ Apache instance 3 (port 8082) → cluster-3 → nodes [1,2,3,4,5]
└─ ...

web-2.example.com
├─ Apache instance 1 (port 8080) → cluster-1 → nodes [1,2,3,4,5]
├─ Apache instance 2 (port 8081) → cluster-2 → nodes [1,2,3,4,5]
└─ ...

(External Load Balancer)
├─ cluster-1 traffic → round-robin across [web-1:8080, web-2:8080, web-3:8080, web-4:8080]
├─ cluster-2 traffic → round-robin across [web-1:8081, web-2:8081, web-3:8081, web-4:8081]
└─ ...
```

### 8.2 Static workers.properties Configuration

**Single static config file per web server host:**

```properties
# /etc/apache2/workers.properties

worker.list=cluster-1,cluster-2,cluster-3,...

# ===== CLUSTER-1 (app-a) =====
worker.cluster-1.type=lb
worker.cluster-1.balance_workers=node-1,node-2,node-3,node-4,node-5,node-6,node-7,node-8,node-9,node-10
worker.cluster-1.sticky_session=1
worker.cluster-1.sticky_session_force=1
worker.cluster-1.method=Weighted

worker.node-1.type=ajp13
worker.node-1.host=192.168.1.10
worker.node-1.port=8009
worker.node-1.ping_mode=A
worker.node-1.ping_interval=30

worker.node-2.type=ajp13
worker.node-2.host=192.168.1.11
worker.node-2.port=8009
worker.node-2.ping_mode=A
worker.node-2.ping_interval=30

# ... (nodes 3-10)

# ===== CLUSTER-2 (app-b) =====
worker.cluster-2.type=lb
worker.cluster-2.balance_workers=node-1,node-2,...
# ... etc
```

**Sticky session behavior:**
- mod_jk encodes route suffix in `JSESSIONID` (e.g., `JSESSIONID=ABC123.node-1`)
- Routes all requests with same session to same node
- If node is down, mod_jk detects via AJP health check (every 30s)
- Automatically routes to next available node, updates session cookie
- Stateless across the 4 web servers (each can independently decode cookie)

### 8.3 Static Content Delivery

**Web servers serve static content from local cache:**

```
/var/www/cluster-1/
├── index.html
├── css/
├── js/
├── images/
└── ...
```

**During deployment:**
- Harness also delivers static content to all 4 web server hosts
- Deployment stage: push static files via SCP/rsync to `/var/www/{cluster-id}/`
- Decoupled from WAR deployment (handled separately by Harness)

---

## 9. Manager REST API

### 9.1 Core Endpoints

#### Cluster Management

```
GET /clusters
  Return: { "clusters": [{"cluster_id": "cluster-1", "status": "healthy", ...}] }

GET /clusters/{cluster-id}
  Return: Cluster config + current state

POST /clusters/{cluster-id}/policy
  Body: { "mode": "AUTO" | "MANUAL", "min_instances": 5, "max_instances": 10 }

POST /clusters/{cluster-id}/stop-all
  Stop all Tomcats in cluster (blocks until complete or timeout)

POST /clusters/{cluster-id}/start-all
  Start Tomcats until min_instances reached

GET /clusters/{cluster-id}/status
  Return: { "running": 8, "stopped": 2, "unhealthy": 0, "policy_mode": "AUTO" }
```

#### Deployment

```
POST /clusters/{cluster-id}/deploy
  Body: {
    "war_path": "/opt/cluster-manager/staging/cluster-1/app-a/app.war",
    "version": "v1.2.3"
  }
  Return: { "deployment_id": "deploy-001", "status": "in_progress" }

GET /clusters/{cluster-id}/deployments/{deployment-id}
  Return: { 
    "status": "completed" | "in_progress" | "failed",
    "version": "v1.2.3",
    "nodes_completed": 8,
    "nodes_total": 10,
    "errors": []
  }

POST /clusters/{cluster-id}/rollback
  Rollback to previous version (if available)
```

#### Node Monitoring

```
GET /nodes
  Return: { "nodes": [{"node_id": "node-1", "status": "healthy", "agent_version": "1.0"}] }

GET /nodes/{node-id}/status
  Return: Current state of all Tomcats on node

GET /nodes/{node-id}/tomcats/{app-id}/status
  Return: { "status": "running", "version": "v1.2.3", "health": "healthy", "pid": 1234 }
```

#### Manual Control (Operations)

```
POST /nodes/{node-id}/tomcats/{app-id}/start
POST /nodes/{node-id}/tomcats/{app-id}/stop
POST /nodes/{node-id}/tomcats/{app-id}/restart
```

---

## 10. Data Model

### 10.1 Cluster State

```python
class Cluster:
    cluster_id: str                # e.g., "cluster-1"
    app_id: str                    # e.g., "app-a"
    app_path: str                  # e.g., "/opt/tomcats/app-a"
    nodes: List[str]               # node IDs in this cluster
    
    policy: ClusterPolicy
    current_version: str           # e.g., "v1.2.3"
    previous_version: Optional[str]
    
    deployment_status: DeploymentStatus  # current or last deployment
```

### 10.2 Node State

```python
class Node:
    node_id: str                   # e.g., "node-1"
    hostname: str
    ip_address: str
    agent_port: int                # 9001
    agent_status: str              # "online", "offline", "unhealthy"
    last_heartbeat: datetime
    
    tomcats: Dict[str, TomcatInstance]
```

### 10.3 Tomcat Instance State

```python
class TomcatInstance:
    app_id: str                    # e.g., "app-a"
    instance_port: int             # 9001, 9002, 9003, ...
    ajp_port: int                  # 8009, 8010, 8011, ...
    
    status: str                    # "running", "stopped", "starting", "crashed"
    current_version: str           # e.g., "v1.2.3"
    pid: Optional[int]
    
    health_status: str             # "healthy", "unhealthy", "unknown"
    last_health_check: datetime
    
    created_at: datetime
    last_state_change: datetime
```

---

## 11. Integration Points

### 11.1 Harness Integration

**Harness actions:**

1. **Build/prepare WAR**
   - Output: WAR file artifact
   - Stage: Save to `/opt/cluster-manager/staging/{cluster-id}/{app-id}/app.war`

2. **Trigger TCM deployment**
   - API call: `POST http://manager-console:9000/clusters/{cluster-id}/deploy`
   - Payload: `{ "war_path": "...", "version": "v1.2.3" }`
   - Wait for response (polling or webhook)

3. **Deploy static content** (parallel)
   - SCP/rsync static files to all 4 web servers
   - Destination: `/var/www/{cluster-id}/`

4. **Handle deployment result**
   - Success: deployment complete, Harness advances to next stage
   - Failure: rollback triggered, Harness fails deployment

### 11.2 Monitoring Integration (Optional)

For future enhancement:

- **Prometheus metrics endpoint:** `GET /metrics`
  - Tomcat instance counts per cluster
  - Policy compliance (running vs. min/max)
  - Deployment success/failure rates
  - Node agent health

- **Alerting hooks:**
  - Policy violation (running < min)
  - Deployment failure
  - Node agent offline

---

## 12. Security Considerations

### 12.1 Network Access

- Manager console: Protected by firewall, Harness authentication
- Node agents: Internal network only (no external access)
- WAR distribution: HTTPS between manager and agents (TLS cert management)
- Static content: Served over HTTPS via external LB

### 12.2 Audit Trail

- All deployments logged with timestamp, version, user (via Harness)
- Config changes tracked in Git repo
- Node agent actions logged locally
- Deployment history stored (optional: centralized log aggregation)

---

## 13. Failure Handling

### 13.1 Deployment Failures

**Scenario: Agent fails during WAR deployment**

```
1. Agent receives WAR, starts extracting to webapps/
2. Network error / disk full / permission denied
3. Agent reports error: "Failed to deploy WAR"
4. Manager:
   a) Marks deployment as FAILED
   b) Does NOT proceed with restart
   c) Node retains old WAR (safe state)
   d) Notifies Harness of failure
```

**Scenario: Tomcat fails to start after WAR deploy**

```
1. Manager sent start command
2. Tomcat process starts but crashes on startup
3. Agent detects process not running after startup timeout
4. Agent:
   a) Backs up failed WAR to app.war.failed
   b) Restores previous WAR
   c) Restarts with old WAR
   d) Reports startup failure
5. Manager marks deployment as FAILED, logs details
```

### 13.2 Node Agent Offline

**Manager behavior:**

```
1. Manager polls node, agent doesn't respond
2. Retries 3 times (configurable) with backoff
3. Marks node as OFFLINE
4. Policy enforcement skips offline nodes
5. Manual deployment to offline cluster:
   a) Manager reports "N nodes offline"
   b) Harness decides: proceed or abort
   c) If proceed: deploys to online nodes only
```

### 13.3 Policy Enforcement Conflicts

**Scenario: Deployment + policy scaling conflict**

```
Pre-deployment: Cluster at max=10, running=10
Operations sets MANUAL, deployment begins

During deployment:
- All Tomcats stopped gracefully
- WAR pushed and deployed
- Tomcats restarting

After deployment:
- Operations sets mode to AUTO
- Policy enforcement runs
- Running count < min_required → starts Tomcats until min reached
- Result: cluster at expected state
```

---

## 14. Implementation Phases

### Phase 1: Core Manager & Agent (MVP)

- Manager REST API (core endpoints)
- Node agent with Tomcat control
- Basic deployment workflow
- File-based configuration
- Status monitoring

### Phase 2: Policy Enforcement

- Policy loop implementation
- Min/max enforcement
- Manual override support
- Harness integration testing

### Phase 3: Resilience & Observability

- Health check integration
- Failure handling & rollback
- Metrics/logging
- Comprehensive error messages

### Phase 4: Web Tier Integration

- Static content delivery coordination
- mod_jk configuration validation
- Load balancer health checks
- Test sticky session routing

### Phase 5: Production Hardening

- TLS for agent communication
- Rate limiting & throttling
- Audit logging
- High-availability manager (optional)

---

## 15. Technology Stack

### Manager Service

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.8+ | |
| Web Framework | FastAPI | Async-capable, good for I/O |
| Scheduler | APScheduler | Background policy enforcement loop |
| Config | YAML files | Git-tracked, human-readable |
| Process Mgmt | subprocess module | Direct Java process spawning |
| HTTP Client | httpx/requests | Communication with node agents |
| Testing | pytest | Unit & integration tests |
| Deployment | systemd service | Single binary/script deployment |

### Node Agent

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.8+ | Same as manager for consistency |
| Web Framework | FastAPI | Lightweight, fast |
| Process Mgmt | subprocess + psutil | Monitor Tomcat processes |
| HTTP Client | httpx/requests | Reporting to manager |
| Deployment | systemd service | Auto-restart on failure |

---

## 16. Installation & Deployment

### 16.1 Package Structure

Single unified package (`tcm-1.0.0.tar.gz`) contains both console and node agent code. Role determination happens at installation/startup time.

```
tcm-1.0.0/
├── bin/
│   ├── start.sh                    # Main entry point (starts console or agent)
│   ├── stop.sh                     # Stop service
│   ├── status.sh                   # Check status
│   └── configure.sh                # Interactive configuration
├── console/
│   ├── app.py                      # FastAPI manager service
│   ├── requirements.txt
│   ├── api/
│   │   ├── clusters.py
│   │   ├── deployments.py
│   │   ├── nodes.py
│   │   └── monitoring.py
│   ├── models/
│   │   ├── cluster.py
│   │   ├── node.py
│   │   └── deployment.py
│   ├── services/
│   │   ├── deployment_service.py
│   │   ├── policy_service.py
│   │   └── node_manager.py
│   └── config/
│       └── console.yaml.example
├── agent/
│   ├── app.py                      # FastAPI node agent service
│   ├── requirements.txt
│   ├── tomcat_controller.py        # Tomcat lifecycle management
│   ├── health_checker.py           # Health monitoring
│   ├── war_deployer.py             # WAR distribution & deployment
│   ├── process_manager.py          # Direct Java process management
│   └── config/
│       └── agent.yaml.example
├── shared/
│   ├── utils.py                    # Common utilities
│   ├── config_loader.py            # YAML config loading
│   ├── logging_config.py           # Structured logging
│   └── constants.py                # Shared constants
├── systemd/
│   ├── tcm-console.service         # Systemd service for console
│   ├── tcm-agent.service           # Systemd service for agent
│   └── install_systemd.sh          # Service installation helper
├── scripts/
│   ├── install.sh                  # Installation script (run once)
│   ├── uninstall.sh                # Uninstall script
│   ├── upgrade.sh                  # Upgrade script
│   └── init_config.sh              # Configuration wizard
├── config/
│   └── local-config.yaml           # Generated at install time
├── docs/
│   ├── INSTALLATION.md
│   ├── QUICKSTART.md
│   └── TROUBLESHOOTING.md
└── README.md
```

### 16.2 Installation Process

**Prerequisites:**
- Python 3.8 or later
- pip (Python package manager)
- systemd (for service management)
- 2GB free disk space minimum

**Installation steps:**

```bash
# 1. Extract package
tar -xzf tcm-1.0.0.tar.gz
cd tcm-1.0.0

# 2. Run installation script (interactive)
sudo ./scripts/install.sh
```

**install.sh workflow:**

```bash
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

# 1. Create directories
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
```

### 16.3 Configuration File

**Generated at install time: `/etc/tcm/local-config.yaml`**

**Console configuration example:**

```yaml
# /etc/tcm/local-config.yaml (on console host)
role: console
version: 1.0

console:
  host: 0.0.0.0              # Listen on all interfaces
  port: 9000
  config_root: /etc/tcm      # Where cluster configs live
  log_dir: /var/log/tcm
  
logging:
  level: INFO
  format: json               # Structured logging for parsing
  
policy_enforcement:
  enabled: true
  check_interval: 30         # seconds
  node_timeout: 10           # seconds for node response
  
deployment:
  staging_dir: /opt/tcm/staging
  max_parallel_nodes: 10     # Deploy to N nodes in parallel
  health_check_timeout: 10
  startup_timeout: 60
```

**Agent configuration example:**

```yaml
# /etc/tcm/local-config.yaml (on agent host, e.g., node-1)
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
  graceful_stop_timeout: 30  # seconds
  startup_timeout: 60        # seconds
  health_check_timeout: 10
  max_concurrent_deploys: 3  # per node
  
process_management:
  pid_dir: /var/run/tcm
  enable_monitoring: true    # Monitor process CPU, memory
```

### 16.4 Systemd Service Files

**Console service: `/etc/systemd/system/tcm-console.service`**

```ini
[Unit]
Description=TCM Console Manager
After=network.target

[Service]
Type=simple
User=tcm
Group=tcm
WorkingDirectory=/opt/tcm

ExecStart=/opt/tcm/venv/bin/python console/app.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=tcm-console

Environment="PYTHONUNBUFFERED=1"
Environment="CONFIG_PATH=/etc/tcm/local-config.yaml"

[Install]
WantedBy=multi-user.target
```

**Agent service: `/etc/systemd/system/tcm-agent.service`**

```ini
[Unit]
Description=TCM Node Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tcm

ExecStart=/opt/tcm/venv/bin/python agent/app.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=tcm-agent

Environment="PYTHONUNBUFFERED=1"
Environment="CONFIG_PATH=/etc/tcm/local-config.yaml"

[Install]
WantedBy=multi-user.target
```

### 16.5 Startup Scripts

**`bin/start.sh` - Start or restart service**

```bash
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
```

**`bin/stop.sh` - Stop service**

```bash
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
```

**`bin/status.sh` - Check service status**

```bash
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
```

### 16.6 First-Time Setup (After Installation)

**Console host first steps:**

```bash
# 1. Verify console is running
systemctl status tcm-console

# 2. Check logs
journalctl -u tcm-console -f

# 3. Test API
curl http://localhost:9000/clusters

# 4. Create initial cluster configs
# (Manually create /etc/tcm/clusters/cluster-1.yaml, etc.)
# Or via API: POST http://localhost:9000/clusters

# 5. Enable auto-start on reboot
sudo systemctl enable tcm-console
```

**Agent host first steps:**

```bash
# 1. Verify agent is running
systemctl status tcm-agent

# 2. Check logs
journalctl -u tcm-agent -f

# 3. Test API
curl http://localhost:9001/nodes/node-1/status

# 4. Manager should discover this node
# (Agent polls manager or manager polls agent)

# 5. Enable auto-start on reboot
sudo systemctl enable tcm-agent
```

### 16.7 Upgrade Process

**To upgrade to a new version:**

```bash
# 1. Extract new package
tar -xzf tcm-1.1.0.tar.gz -C /tmp/tcm-upgrade

# 2. Run upgrade script
sudo /tmp/tcm-upgrade/scripts/upgrade.sh /opt/tcm

# Upgrade script:
# - Backs up /etc/tcm to /etc/tcm.bak
# - Backs up /opt/tcm to /opt/tcm.bak
# - Updates Python dependencies
# - Stops service gracefully
# - Copies new files
# - Runs any config migrations
# - Starts service
# - Verifies health
```

### 16.8 Uninstall Process

**To remove TCM:**

```bash
sudo /opt/tcm/scripts/uninstall.sh
```

**Uninstall script:**

```bash
#!/bin/bash
# Stops services, removes systemd units, leaves config/data intact (backup first!)

read -p "This will uninstall TCM. Continue? (y/n): " confirm
if [ "$confirm" != "y" ]; then exit 0; fi

# Stop services
systemctl stop tcm-console tcm-agent 2>/dev/null || true

# Disable auto-start
systemctl disable tcm-console tcm-agent 2>/dev/null || true

# Remove systemd units
rm /etc/systemd/system/tcm-console.service
rm /etc/systemd/system/tcm-agent.service
systemctl daemon-reload

# Remove install directory
rm -rf /opt/tcm

echo "TCM uninstalled."
echo "Config preserved at /etc/tcm (backup before deleting)"
echo "Logs preserved at /var/log/tcm"
```

### 16.9 Directory Permissions & User Account

**Create dedicated user/group (optional but recommended):**

```bash
# During install.sh (run as root):
useradd -r -s /bin/false tcm 2>/dev/null || true

# Set permissions
chown -R tcm:tcm /opt/tcm
chown -R tcm:tcm /etc/tcm
chown -R tcm:tcm /var/log/tcm

chmod 750 /etc/tcm           # Only tcm can read config
chmod 755 /opt/tcm/bin/*.sh  # Executables readable
chmod 750 /var/log/tcm       # Only tcm can write logs
```

**Note:** Agent service runs as `root` (needs to control Tomcat processes). Console can run as `tcm` user.

---

## 17. Appendix: File Locations Reference

```
Manager Console Server:
  /etc/tcm/                          # Config root
    local-config.yaml                # Role and console settings
    clusters/                         # Cluster configs
      cluster-1.yaml
      cluster-2.yaml
      ...
    nodes/                            # Node definitions
      node-1.yaml
      node-2.yaml
      ...
  /opt/tcm/                          # Installation directory
    bin/                              # Startup scripts
    console/                          # Manager service code
    agent/                            # Agent code (not used on console)
    systemd/                          # Service files
    scripts/                          # Install/upgrade scripts
    venv/                             # Python virtual environment
  /opt/tcm/staging/                  # WAR files from Harness (temporary)
    cluster-1/
      app-a/
        app.war
    cluster-2/
      app-b/
        app.war
  /var/log/tcm/                      # Console and agent logs
    tcm-console.log
    tcm-agent.log

Tomcat Nodes (Agent hosts):
  /etc/tcm/                          # Agent config (same structure as console)
    local-config.yaml                # Role and agent settings
  /opt/tcm/                          # Installation directory (same as console)
    agent/                            # Agent service code
    venv/                             # Python virtual environment
  /opt/tomcats/                      # All Tomcat instances
    app-a/                           # One Tomcat per app
      conf/
        server.xml
      webapps/
        app.war                      # Current version
        app.war.1                    # Previous versions (backups)
        app.war.2
      logs/
        catalina.out
      work/
    app-b/
      (similar structure)
    app-c/
      (similar structure)
  /var/run/tcm/                      # PID files
    tomcat-app-a.pid
    tomcat-app-b.pid
    tomcat-app-c.pid
  /var/log/tcm/                      # Agent logs
    tcm-agent.log

Web Server Hosts:
  /var/www/                          # Static content per cluster
    cluster-1/
      index.html
      css/
      js/
      images/
    cluster-2/
      ...
  /etc/apache2/workers.properties    # mod_jk config (static, generated once)
  /etc/apache2/sites-enabled/        # Apache vhost configs
    cluster-1.conf
    cluster-2.conf
    ...
```

---

## 17. Success Criteria

The system is production-ready when:

1. ✓ 30 nodes, 300 Tomcats managed via single manager console
2. ✓ Deployments complete without manual per-node steps
3. ✓ Policy enforcement maintains min/max instances automatically
4. ✓ Sticky sessions work correctly across 4 redundant web servers
5. ✓ Rollback available (revert to previous WAR version)
6. ✓ Manual control available (stop/start individual Tomcats)
7. ✓ Graceful shutdown: in-flight requests complete before stop
8. ✓ Clear error messages and audit trail for troubleshooting
9. ✓ <5 minute deployment cycle for full cluster (30 nodes)
10. ✓ Zero downtime switchover (external LB handles failover)

---

**Document Version:** 1.0  
**Last Updated:** 2026-03-28  
**Author:** Architecture Design Session  
**Status:** Ready for Implementation
