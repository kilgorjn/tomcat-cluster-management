# TCM Security Requirements & Architecture
## Risk Assessment and Implementation Roadmap

---

## 1. Executive Summary

This document outlines security considerations for TCM (Tomcat Cluster Manager) implementation in phases:

- **Phase 0 (Prototype/MVP):** Minimal security (internal network assumed, basic logging)
- **Phase 1 (Hardening):** Add authentication, encryption, audit trails
- **Phase 2 (Production):** Full compliance, SIEM integration, certificate rotation
- **Phase 3 (Enterprise):** LDAP/SSO, advanced RBAC, secrets management

This separation allows rapid prototyping while maintaining a clear path to production-grade security.

---

## 2. Threat Model & Risk Assessment

### 2.1 Assets at Risk

| Asset | Risk | Impact |
|-------|------|--------|
| Console Manager | Compromise / Takeover | Attacker can deploy code to all 300 Tomcats |
| Node Agents | Compromise / Takeover | Attacker can control Tomcat lifecycle on 30 nodes |
| Configuration (YAML) | Unauthorized read/modify | Exposure of cluster topology, credentials |
| WAR Files | Tampering | Deploy malicious code, supply chain attack |
| Audit Logs | Deletion / Tampering | Loss of forensic trail |
| TLS Certificates | Theft / Expiration | Man-in-the-middle attacks, service downtime |

### 2.2 Attack Vectors

**External attacks:**
- Network reconnaissance of TCM ports (9000, 9001)
- Unencrypted credential interception (console login, API keys)
- WAR file tampering during Harness → Manager transfer
- Brute-force API authentication

**Internal attacks (rogue employee/misconfigured host):**
- Unauthorized deployment to production clusters
- Read cluster configs without authorization
- Deploy malicious WAR to sensitive cluster
- Modify deployment history/audit logs

**Operational mistakes:**
- Credentials hardcoded in config files
- Self-signed TLS certs with expired dates
- Logs missing audit trail of who did what
- No backups of critical configs

### 2.3 Trust Boundaries

```
┌─────────────────────────────────────────────────────────┐
│  INTERNAL NETWORK (Trusted)                             │
│                                                          │
│  ┌──────────────────┐           ┌──────────────────┐   │
│  │  Console Manager │◄──────────┤   Node Agents    │   │
│  │  (9000)          │ TLS/Auth  │   (9001)         │   │
│  └────────┬─────────┘           └──────────────────┘   │
│           │                                              │
│           │ ← TRUST BOUNDARY                             │
│           │                                              │
└───────────┼──────────────────────────────────────────────┘
            │
   ┌────────┴────────┐
   │                 │
   ▼                 ▼
[Harness]       [External Monitoring]
(CI/CD)          (Optional: Prometheus, etc.)
(HTTP/REST)      (TLS Required)
```

---

## 3. Security Requirements by Phase

### Phase 0: Prototype/MVP (Current)

**Goal:** Get working system up, assume internal network, defer security hardening.

**Requirements:**

- ✓ Code runs locally (not internet-facing)
- ✓ Basic file permissions (`/etc/tcm/` readable only by tcm user)
- ✓ Console API listens on `localhost` or specific management VLAN
- ✓ HTTP-only (no TLS required yet, internal only)
- ✓ No authentication on API endpoints (internal trust assumed)
- ✓ Plaintext config files (no encrypted credentials)
- ✓ Basic stdout/file logging (no structured audit trail yet)

**Security baseline:**
- Network: Firewall prevents external access to ports 9000, 9001
- Host: OS-level user isolation (tcm user, root for agent)
- Process: Systemd service restrictions (NoNewPrivileges, PrivateTmp, etc.)
- Config: File permissions (400 for config, readable by service user only)

**Known gaps (accepted for prototype):**
- No TLS encryption
- No API authentication
- No audit logging of actions
- Credentials in plaintext YAML
- No certificate management

---

### Phase 1: Initial Hardening (Post-MVP)

**Goal:** Add basic encryption, authentication, and audit logging.

**Requirements:**

#### 1A. Console Authentication

**API Key Authentication (simple, no login UI needed):**

```yaml
# /etc/tcm/console-api-keys.yaml (mode 400, owned by tcm)
api_keys:
  - key: "tcm-harness-deploy-key-abc123xyz"
    name: "Harness Deployment Service"
    permissions: ["deploy"]
    created_at: "2025-03-28"
    
  - key: "tcm-ops-readonly-key-def456uvw"
    name: "Operations Dashboard"
    permissions: ["read"]
    created_at: "2025-03-28"
```

**Console API requires `Authorization: Bearer <api-key>` header**

```bash
# Example: Harness calls console
curl -H "Authorization: Bearer tcm-harness-deploy-key-abc123xyz" \
  https://console.internal:9000/clusters/cluster-1/deploy \
  -d '{"war_path": "...", "version": "v1.2.3"}'
```

**Role-based access control (RBAC):**
- `deploy` — trigger deployments, manage clusters
- `read` — view status, logs, cluster configs
- `admin` — manage API keys, configurations

**Implementation:** FastAPI middleware to check Authorization header, validate key, check permissions.

#### 1B. Node Agent Authentication

**Mutual TLS (mTLS) + API Key:**

Agent registers with console at startup:

```bash
# Agent startup:
1. Generate self-signed cert (if not exists)
2. POST /nodes/register
   {
     "node_id": "node-1",
     "agent_version": "1.0.0",
     "cert_fingerprint": "sha256:abc123...",
     "api_key": "tcm-node-1-key-xyz"
   }
3. Console stores mapping: node-1 → fingerprint + api_key
```

Console ↔ Agent communication:

```
Manager → Agent (TLS + auth):
  GET https://node-1.internal:9001/tomcats/status
  Authorization: Bearer tcm-node-1-key-xyz
  (TLS cert must match registered fingerprint)

Agent → Manager (TLS + auth):
  POST https://console.internal:9000/nodes/node-1/report-status
  Authorization: Bearer tcm-node-1-key-xyz
  (TLS cert must match console's cert)
```

#### 1C. Transport Encryption (TLS)

**Self-signed certificates for MVP hardening:**

```bash
# Generate on manager host during install
openssl req -x509 -newkey rsa:2048 -keyout /etc/tcm/tls/console-key.pem \
  -out /etc/tcm/tls/console-cert.pem -days 365 -nodes \
  -subj "/CN=console.internal"

# Generate on each agent host
openssl req -x509 -newkey rsa:2048 -keyout /etc/tcm/tls/agent-key.pem \
  -out /etc/tcm/tls/agent-cert.pem -days 365 -nodes \
  -subj "/CN=node-1.internal"

# Permissions
chmod 400 /etc/tcm/tls/*-key.pem
chmod 444 /etc/tcm/tls/*-cert.pem
```

**FastAPI configuration:**

```python
# console/app.py
import ssl
from fastapi import FastAPI

app = FastAPI()

# Load TLS certs
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(
    certfile="/etc/tcm/tls/console-cert.pem",
    keyfile="/etc/tcm/tls/console-key.pem"
)

# Start with: uvicorn --ssl-keyfile ... --ssl-certfile ...
```

#### 1D. Audit Logging

**Structured audit trail for all actions:**

```json
// /var/log/tcm/audit.log (append-only, mode 640)
{
  "timestamp": "2025-03-28T14:32:15Z",
  "event": "deployment_started",
  "cluster_id": "cluster-1",
  "version": "v1.2.3",
  "initiated_by": "harness-deploy-key",
  "status": "in_progress"
}

{
  "timestamp": "2025-03-28T14:35:22Z",
  "event": "deployment_completed",
  "cluster_id": "cluster-1",
  "version": "v1.2.3",
  "nodes_completed": 10,
  "duration_seconds": 187,
  "status": "success"
}

{
  "timestamp": "2025-03-28T14:36:01Z",
  "event": "policy_violation",
  "cluster_id": "cluster-2",
  "expected_min": 5,
  "actual_running": 3,
  "action": "alerting_ops"
}
```

**Agent audit logging:**

```json
// /var/log/tcm/audit.log (on each node)
{
  "timestamp": "2025-03-28T14:32:45Z",
  "node_id": "node-1",
  "event": "tomcat_stopped",
  "app_id": "app-a",
  "pid": 12345,
  "initiated_by": "console-deployment-001"
}

{
  "timestamp": "2025-03-28T14:33:01Z",
  "node_id": "node-1",
  "event": "war_deployed",
  "app_id": "app-a",
  "version": "v1.2.3",
  "war_hash": "sha256:abc123...",
  "status": "success"
}
```

#### 1E. Secret Management

**Move secrets out of plaintext YAML:**

```yaml
# /etc/tcm/local-config.yaml (plaintext, non-sensitive)
role: console
console:
  host: 0.0.0.0
  port: 9000

# Sensitive configs in separate file
# /etc/tcm/secrets.yaml (mode 400)
api_keys:
  harness_deploy_key: "tcm-harness-deploy-key-abc123xyz"
  ops_read_key: "tcm-ops-readonly-key-def456uvw"

tls:
  console_cert_path: "/etc/tcm/tls/console-cert.pem"
  console_key_path: "/etc/tcm/tls/console-key.pem"
```

**Load at runtime:**

```python
import yaml
from pathlib import Path

def load_secrets():
    with open("/etc/tcm/secrets.yaml", "r") as f:
        return yaml.safe_load(f)

secrets = load_secrets()
api_keys = secrets["api_keys"]
```

---

### Phase 2: Production Hardening

**Goal:** CA-signed certificates, advanced RBAC, SIEM integration, secrets rotation.

#### 2A. Certificate Management

**Self-signed → CA-signed certificates:**

```bash
# Generate CSR
openssl req -new -key /etc/tcm/tls/console-key.pem \
  -out /etc/tcm/tls/console.csr \
  -subj "/CN=console.internal/O=Company/C=US"

# Submit to internal CA
# Receive signed cert: console-cert.pem (valid 1 year)

# Implement cert rotation (annual + 30 days before expiry warning)
```

**Certificate pinning (node agents verify console cert):**

```python
# agent/config.py
import ssl

# Node agent verifies console cert matches pinned fingerprint
CONSOLE_CERT_FINGERPRINT = "sha256:abc123def456..."  # Calculated at install

def verify_console_connection():
    context = ssl.create_default_context()
    context.check_hostname = False  # We verify fingerprint manually
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations("/etc/tcm/tls/console-ca.pem")
    
    # Additional check: verify cert fingerprint
    cert = context.get_ca_certs()
    fingerprint = hashlib.sha256(cert).hexdigest()
    assert fingerprint == CONSOLE_CERT_FINGERPRINT
```

#### 2B. Advanced RBAC

**Role hierarchy:**

```yaml
# /etc/tcm/rbac.yaml
roles:
  admin:
    permissions:
      - "clusters:*"
      - "deployments:*"
      - "nodes:*"
      - "config:write"
      - "logs:read"
      - "api_keys:manage"
  
  deployer:
    permissions:
      - "deployments:create"
      - "deployments:read"
      - "clusters:read"
      - "nodes:read"
  
  operator:
    permissions:
      - "clusters:read"
      - "nodes:read"
      - "nodes:start"
      - "nodes:stop"
      - "logs:read"
  
  viewer:
    permissions:
      - "clusters:read"
      - "nodes:read"
      - "logs:read"

api_keys:
  harness-deploy:
    role: deployer
    expires_at: "2026-03-28"
  
  ops-team:
    role: operator
    expires_at: "2025-06-28"
```

#### 2C. SIEM Integration

**Forward logs to centralized system (Splunk, ELK, etc.):**

```yaml
# /etc/tcm/logging.yaml
handlers:
  file:
    filename: /var/log/tcm/tcm.log
    formatter: json
  
  syslog:
    address: /dev/log
    facility: local0
    formatter: json
  
  siem_forward:
    type: syslog
    host: siem-collector.internal
    port: 514
    protocol: tcp+tls
    ca_cert: /etc/tcm/tls/siem-ca.pem
    formatter: json

root:
  handlers: [file, syslog, siem_forward]
  level: INFO
```

#### 2D. Secrets Rotation

**Implement key rotation policy:**

```bash
# Rotate API keys annually or on compromise
# Generate new key, add to secrets.yaml, mark old key as "deprecated"
# Clients have 30-day grace period to switch to new key

api_keys:
  harness_deploy_key_2025:
    key: "tcm-harness-deploy-key-2025-abc123xyz"
    status: "active"
    created_at: "2025-03-28"
  
  harness_deploy_key_2024:
    key: "tcm-harness-deploy-key-2024-old987uvw"
    status: "deprecated"  # Still works, will be removed in 30 days
    created_at: "2024-03-28"
    deprecated_at: "2025-03-28"
    expires_at: "2025-04-28"
```

**Automatic TLS cert renewal:**

```bash
# Implement cert renewal 30 days before expiry
# Use certbot (Let's Encrypt) or internal CA API

# Systemd timer: check certs daily, renew if < 30 days left
# systemctl enable tcm-cert-renewal.timer
```

---

### Phase 3: Enterprise Security

**Goal:** LDAP/SSO integration, advanced secrets management, comprehensive compliance.

#### 3A. LDAP/SSO Authentication

**Replace API keys with OAuth2/OIDC via existing infrastructure:**

```yaml
# /etc/tcm/auth.yaml
auth:
  type: oauth2
  provider: okta  # or your SSO provider
  client_id: tcm-app-client-id
  client_secret: <from-vault>
  discovery_url: https://okta.example.com/.well-known/openid-configuration
  
  # Scope users to specific LDAP groups
  required_groups:
    - "tcm-admins"
    - "tcm-deployers"

# Console login:
# 1. User clicks "Login with SSO"
# 2. Redirects to LDAP/Okta
# 3. Returns JWT token
# 4. Token validated on all API calls
```

#### 3B. Secrets Vault Integration

**Use HashiCorp Vault or AWS Secrets Manager:**

```python
# console/config.py
from hvac import Client

vault_client = Client(
    url="https://vault.internal:8200",
    auth_method="kubernetes"  # K8s auth if running on Kubernetes
)

def get_api_key(key_name):
    secret = vault_client.secrets.kv.read_secret_version(
        path=f"tcm/api-keys/{key_name}"
    )
    return secret["data"]["data"]["key"]

def get_tls_cert():
    secret = vault_client.secrets.kv.read_secret_version(
        path="tcm/tls/console"
    )
    return secret["data"]["data"]["cert"], secret["data"]["data"]["key"]
```

#### 3C. WAR File Integrity & Signing

**Verify WAR files before deployment:**

```python
# agent/war_deployer.py
import hashlib
import json

def verify_war_integrity(war_file, expected_hash):
    """Verify WAR hash against manifest"""
    actual_hash = hashlib.sha256(open(war_file, "rb").read()).hexdigest()
    assert actual_hash == expected_hash, "WAR integrity check failed"
    
def verify_war_signature(war_file, signature, public_key):
    """Verify WAR was signed by approved builder"""
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    
    signature_valid = public_key.verify(
        signature,
        open(war_file, "rb").read(),
        padding.PSS(...),
        hashes.SHA256()
    )
    return signature_valid
```

**Harness includes WAR manifest:**

```json
{
  "war_file": "app-a-v1.2.3.war",
  "hash": "sha256:abc123def456...",
  "signature": "<digital-signature>",
  "signed_by": "harness-build-pipeline",
  "timestamp": "2025-03-28T14:30:00Z"
}
```

---

## 4. Network Security

### 4.1 Network Segmentation

**Recommended topology:**

```
┌──────────────────────────────────────────────────┐
│  Management VLAN (10.0.10.0/24)                 │
│  - Console Manager (10.0.10.10:9000)            │
│  - Ops Dashboard (10.0.10.20)                   │
└──────────────────────────────────────────────────┘
                      │
       ┌──────────────┼──────────────┐
       │              │              │
┌──────▼──────┐ ┌────▼─────┐ ┌─────▼────┐
│Application  │ │Application│ │Application│
│VLAN 1       │ │VLAN 2     │ │VLAN 3     │
│(10.0.1.0)   │ │(10.0.2.0) │ │(10.0.3.0) │
│             │ │           │ │           │
│Nodes 1-10   │ │Nodes 11-20│ │Nodes 21-30│
│Port 9001    │ │Port 9001  │ │Port 9001  │
└─────────────┘ └───────────┘ └───────────┘

┌──────────────────────────────────────────────────┐
│  DMZ / Web Tier VLAN (10.0.20.0/24)             │
│  - 4 Web Server Hosts (mod_jk)                  │
│  - External LB                                   │
└──────────────────────────────────────────────────┘
```

### 4.2 Firewall Rules

**Inbound rules (default DENY):**

```
Console Manager (10.0.10.10):
  - Allow 10.0.10.0/24 → 9000/tcp    (Management VLAN only)
  - Allow 10.0.1.0/24 → 9000/tcp     (App VLAN agents polling for commands)
  - Allow 10.0.2.0/24 → 9000/tcp
  - Allow 10.0.3.0/24 → 9000/tcp
  - DENY all others

Node Agents (10.0.*.* port 9001):
  - Allow 10.0.10.10 → 9001/tcp      (Console can command agents)
  - DENY all others

Web Servers (10.0.20.0/24 port 8080-8089):
  - Allow 0.0.0.0/0 → 8080-8089/tcp  (Public internet traffic)
  - Allow 10.0.*.* → 8009/tcp        (AJP from mod_jk to Tomcats)
```

### 4.3 VPN/Bastion Access

**For remote operations:**

```bash
# Ops teams connect via VPN
# VPN gateway authenticates against LDAP
# VPN users placed in Management VLAN (10.0.10.0/24)
# Can access console API, not direct node access
```

---

## 5. Data Protection

### 5.1 Configuration Data

**Sensitive files and permissions:**

```bash
# Cluster configs (minimal sensitive data, mostly topology)
-rw-r----- 1 tcm tcm /etc/tcm/clusters/cluster-1.yaml

# API keys (HIGHLY SENSITIVE)
-r-------- 1 tcm tcm /etc/tcm/secrets.yaml

# TLS certificates (sensitive, but acceptable read access for service user)
-r-------- 1 tcm tcm /etc/tcm/tls/console-key.pem
-r--r--r-- 1 tcm tcm /etc/tcm/tls/console-cert.pem

# Logs (should be write-only for service, read for admins)
-rw-r----- 1 tcm root /var/log/tcm/tcm.log
-rw-r----- 1 tcm root /var/log/tcm/audit.log
```

### 5.2 WAR File Storage

**Harness staging → Agent deployment:**

```
/opt/tcm/staging/
  ├── cluster-1/app-a/
  │   └── app.war (uploaded by Harness)
  │        [should verify hash/signature before agent deploys]
  
/opt/tomcats/
  ├── app-a/
  │   └── webapps/
  │       ├── app.war          (current, running)
  │       ├── app.war.1        (previous version, backup)
  │       └── app.war.failed   (if startup failed, kept for debugging)

# Backup retention: Keep last 3 versions
# Cleanup: Remove staging WAR after successful deployment
```

### 5.3 Log Retention & Deletion

**Audit logs are append-only, no deletion:**

```bash
# /var/log/tcm/audit.log
# - Immutable once written (append-only)
# - Compressed and archived monthly
# - Retained for 2+ years (comply with regulations)
# - Backed up daily to secure storage
```

---

## 6. Compliance & Auditing

### 6.1 Compliance Frameworks

**Map TCM security to common frameworks:**

| Framework | Requirement | TCM Implementation |
|-----------|-------------|-------------------|
| SOC2 C1.1 | Logical access control | API key auth (Phase 1), LDAP (Phase 3) |
| SOC2 C1.2 | Prevent unauthorized access | Network segmentation, firewall rules |
| SOC2 CC7.1 | System monitoring & alerting | Audit logging, SIEM (Phase 2) |
| ISO 27001 A.9.2 | User access management | RBAC, API key rotation (Phase 2) |
| ISO 27001 A.9.4 | Encryption | TLS for all communication (Phase 1) |
| NIST CSF PR.AC-1 | Identity management | Centralized auth (Phase 3) |
| NIST CSF PR.DS-1 | Data protection | TLS, encryption at rest (Phase 2) |

### 6.2 Audit Trail Example

**Answering "Who deployed what, when?"**

```bash
# Query audit logs
grep "deployment_completed" /var/log/tcm/audit.log | tail -20

# Result:
{
  "timestamp": "2025-03-28T14:35:22Z",
  "event": "deployment_completed",
  "cluster_id": "cluster-1",
  "version": "v1.2.3",
  "initiated_by": "harness-deploy-key",
  "nodes_completed": 10,
  "status": "success"
}

# Can trace back to Harness: which Git commit, which pipeline, which user triggered it
```

### 6.3 Alerting & Incident Response

**Security events that should alert:**

```yaml
alerts:
  - event: "failed_authentication"
    threshold: "3 failures in 5 minutes"
    action: "block_api_key_for_15_min"
  
  - event: "unauthorized_deployment"
    threshold: "deployment_denied (api_key lacks permission)"
    action: "alert_security_team"
  
  - event: "policy_violation"
    threshold: "running_instances < min"
    description: "Node may be down or misconfigured"
    action: "alert_ops_team"
  
  - event: "certificate_expiry"
    threshold: "cert_expires_in < 30_days"
    action: "alert_ops_team_to_renew"
  
  - event: "audit_log_integrity_failure"
    threshold: "write_to_audit_log failed"
    action: "immediate_alert_to_security"
```

---

## 7. Security by Design Principles

### 7.1 Defense in Depth

**Multiple layers of protection:**

```
Layer 1: Network isolation (VLAN, firewall)
Layer 2: TLS encryption (transport security)
Layer 3: API authentication (API keys, LDAP)
Layer 4: RBAC (authorization, least privilege)
Layer 5: Audit logging (forensics, accountability)
Layer 6: Secrets management (vault, rotation)
```

### 7.2 Principle of Least Privilege

**Minimal permissions by default:**

```yaml
# Default API key for new deployment service
harness_key:
  role: deployer
  permissions:
    - "deployments:create"  # Only can deploy
    - "clusters:read"       # Can read cluster status
    - "deployments:read"    # Can check deployment status
  # CANNOT: manage configs, delete deployments, access logs, etc.
```

### 7.3 Separation of Concerns

**Distinct security domains:**

```
Console Manager:
  - Authentication (API keys, LDAP)
  - Authorization (RBAC)
  - Audit logging
  - Policy enforcement
  [Does NOT manage secrets directly]

Node Agent:
  - Tomcat process management (privileged)
  - Health checks
  - Local audit logging
  [Does NOT manage deployments, only executes commands]

Harness:
  - Code builds
  - WAR staging
  - Deployment orchestration
  [Does NOT manage cluster configs or authentication]
```

---

## 8. Security Incident Procedures

### 8.1 Suspected Compromise Checklist

**If console manager is compromised:**

```bash
1. IMMEDIATE: Disable all API keys
   - Edit /etc/tcm/secrets.yaml, remove all active keys
   - All future API calls fail (Harness cannot deploy)
   - This is intended (contain the breach)

2. Isolate console host
   - Disconnect from network or drop firewall rules
   - Prevent it from polling agents

3. Review audit logs
   - What was deployed? When? To which clusters?
   - Check git history of /etc/tcm/clusters/ (was config modified?)

4. Verify agents
   - Ensure agents are only running approved Tomcats
   - Look for unauthorized WAR versions

5. Restore from backup
   - Redeploy console from clean image
   - Restore config from git (last known good commit)
   - Issue new API keys

6. Investigation
   - Determine entry point (how was it compromised?)
   - Check network logs, OS logs, application logs
   - Implement fix to prevent recurrence
```

**If node agent is compromised:**

```bash
1. IMMEDIATE: Isolate node
   - Firewall drop all traffic to/from node (except bastion access)
   - Node cannot execute Tomcat commands

2. Preserve evidence
   - Back up /var/log/tcm on the node
   - Check /var/run/tcm for suspicious PIDs
   - Check /opt/tomcats/ for unauthorized WAR versions

3. Redeploy node
   - Rebuild from clean OS image
   - Redeploy TCM agent package
   - Move Tomcat workloads to other nodes (policy scaling)

4. Investigation
   - How was it accessed? Unpatched OS? Stolen credentials?
   - Check other nodes for same indicators of compromise
```

---

## 9. Appendix: Security Checklist

### Pre-MVP Launch

- [ ] Console listens on internal network only (not 0.0.0.0:9000 on internet-facing interface)
- [ ] Firewall rules restrict access (default DENY)
- [ ] File permissions set correctly (secrets readable only by service user)
- [ ] No credentials hardcoded in code (use environment variables or config files)
- [ ] OS-level user isolation (tcm user for console, root for agent)

### Phase 1 Implementation

- [ ] API key authentication implemented
- [ ] TLS (self-signed) enabled for all communication
- [ ] Audit logging structured and tested
- [ ] Secrets file created and permissions hardened
- [ ] Agent registration with fingerprint verification working

### Phase 2 Implementation

- [ ] CA-signed certificates deployed
- [ ] Certificate renewal automated
- [ ] RBAC policies defined and tested
- [ ] SIEM integration working
- [ ] API key rotation policy in place and tested

### Phase 3 Implementation

- [ ] LDAP/SSO integrated with existing infrastructure
- [ ] Secrets vault (Hashicorp, AWS) integrated
- [ ] WAR file signature verification implemented
- [ ] Comprehensive compliance audit completed
- [ ] Incident response procedures documented and tested

---

## 10. Security Decision Matrix

**Decisions to make before Phase 1 starts:**

| Decision | Options | Notes |
|----------|---------|-------|
| **Auth method** | API Keys only / LDAP/SSO | Phase 1: Keys. Phase 3: LDAP |
| **TLS certs** | Self-signed / Internal CA / External CA | Phase 1: Self-signed. Phase 2: CA. |
| **Secrets storage** | File-based / Vault | Phase 1: File. Phase 3: Vault |
| **Audit destination** | Local file / SIEM | Phase 1: Local. Phase 2: SIEM |
| **Network segmentation** | Single VLAN / Multi-VLAN | Recommended: Multi-VLAN from start |
| **WAR verification** | Hash only / Hash + Signature | Phase 1: Hash. Phase 3: Signature |

---

## 11. References & Resources

**Useful links for implementation:**

- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
- OWASP Top 10: https://owasp.org/Top10/
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework
- HashiCorp Vault: https://www.vaultproject.io/
- OpenSSL TLS setup: https://www.ssl.com/article/using-openssl-to-generate-ssl-certificates/

---

**Document Version:** 1.0  
**Status:** Ready for Review  
**Next Step:** Approve Phase 1 security requirements and begin MVP implementation
