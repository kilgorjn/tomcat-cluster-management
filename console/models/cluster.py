"""Cluster data models for TCM Console."""

from typing import List

from pydantic import BaseModel, Field

from shared.constants import POLICY_AUTO


class ClusterPolicy(BaseModel):
    """Policy configuration for a cluster."""

    mode: str = Field(default=POLICY_AUTO, description="Policy mode: AUTO or MANUAL")
    min_instances: int = Field(default=1, description="Minimum running instances")
    max_instances: int = Field(default=10, description="Maximum running instances")
    policy_check_interval: int = Field(
        default=30, description="Policy check interval in seconds"
    )


class DeploymentConfig(BaseModel):
    """Deployment configuration for a cluster."""

    graceful_stop_timeout: int = Field(
        default=30, description="Graceful stop timeout in seconds"
    )
    startup_timeout: int = Field(
        default=60, description="Startup timeout in seconds"
    )
    health_check_endpoint: str = Field(
        default="/health", description="Health check endpoint path"
    )
    health_check_timeout: int = Field(
        default=10, description="Health check timeout in seconds"
    )


class Cluster(BaseModel):
    """Cluster configuration and state."""

    cluster_id: str = Field(description="Unique cluster identifier")
    app_id: str = Field(description="Application identifier")
    nodes: List[str] = Field(default_factory=list, description="Node IDs in cluster")
    policy: ClusterPolicy = Field(default_factory=ClusterPolicy)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
