"""Node and TomcatInstance data models for TCM Console."""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field

from shared.constants import DEFAULT_AGENT_PORT, HEALTH_UNKNOWN


class TomcatInstance(BaseModel):
    """Represents a single Tomcat instance on a node."""

    app_id: str = Field(description="Application identifier")
    instance_port: int = Field(description="Tomcat HTTP port")
    ajp_port: int = Field(description="AJP connector port")
    status: str = Field(default="stopped", description="Instance status")
    current_version: str = Field(default="unknown", description="Current WAR version")
    pid: Optional[int] = Field(default=None, description="Process ID if running")
    health_status: str = Field(
        default=HEALTH_UNKNOWN, description="Health check status"
    )
    last_health_check: Optional[datetime] = Field(
        default=None, description="Last health check timestamp"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Instance creation timestamp"
    )
    last_state_change: Optional[datetime] = Field(
        default=None, description="Last state change timestamp"
    )


class Node(BaseModel):
    """Represents a physical or virtual node running Tomcat instances."""

    node_id: str = Field(description="Unique node identifier")
    hostname: str = Field(description="Node hostname")
    ip_address: str = Field(description="Node IP address")
    agent_port: int = Field(
        default=DEFAULT_AGENT_PORT, description="Agent REST API port"
    )
    agent_status: str = Field(default="unknown", description="Agent connectivity status")
    last_heartbeat: Optional[datetime] = Field(
        default=None, description="Last successful heartbeat"
    )
    tomcats: Dict[str, TomcatInstance] = Field(
        default_factory=dict, description="Tomcat instances keyed by app_id"
    )
