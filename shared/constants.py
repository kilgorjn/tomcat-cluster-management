"""Shared constants used across TCM console and agent."""

# Default ports
DEFAULT_CONSOLE_PORT = 9000
DEFAULT_AGENT_PORT = 9001

# Default paths
DEFAULT_CONFIG_PATH = "/etc/tcm/local-config.yaml"
DEFAULT_TOMCAT_ROOT = "/opt/tomcats"
DEFAULT_LOG_DIR = "/var/log/tcm"
DEFAULT_STAGING_DIR = "/opt/tcm/staging"
DEFAULT_PID_DIR = "/var/run/tcm"
DEFAULT_CONFIG_ROOT = "/etc/tcm"

# Timeouts (seconds)
GRACEFUL_STOP_TIMEOUT = 30
STARTUP_TIMEOUT = 60
HEALTH_CHECK_TIMEOUT = 10
FORCE_KILL_WAIT = 5

# Tomcat instance statuses
STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_CRASHED = "crashed"

# Health statuses
HEALTH_HEALTHY = "healthy"
HEALTH_UNHEALTHY = "unhealthy"
HEALTH_UNKNOWN = "unknown"

# Agent statuses
AGENT_ONLINE = "online"
AGENT_OFFLINE = "offline"

# Policy modes
POLICY_AUTO = "AUTO"
POLICY_MANUAL = "MANUAL"

# Deployment statuses
DEPLOY_IN_PROGRESS = "in_progress"
DEPLOY_COMPLETED = "completed"
DEPLOY_FAILED = "failed"

# WAR backup settings
MAX_WAR_BACKUPS = 3
