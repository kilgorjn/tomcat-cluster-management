"""Deployment data models for TCM Console."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from shared.constants import DEPLOY_IN_PROGRESS


class DeploymentStatus(BaseModel):
    """Tracks the status of a deployment operation."""

    deployment_id: str = Field(description="Unique deployment identifier")
    cluster_id: str = Field(description="Target cluster identifier")
    version: str = Field(description="Version being deployed")
    status: str = Field(
        default=DEPLOY_IN_PROGRESS, description="Deployment status"
    )
    nodes_completed: int = Field(default=0, description="Nodes completed")
    nodes_total: int = Field(default=0, description="Total nodes to deploy")
    errors: List[str] = Field(
        default_factory=list, description="Error messages from failed nodes"
    )
    started_at: datetime = Field(description="Deployment start timestamp")
    completed_at: Optional[datetime] = Field(
        default=None, description="Deployment completion timestamp"
    )


class DeployRequest(BaseModel):
    """Request body for triggering a deployment."""

    war_path: str = Field(description="Path to WAR file on staging")
    version: str = Field(description="Version identifier for this deployment")


class PolicyUpdateRequest(BaseModel):
    """Request body for updating cluster policy."""

    mode: str = Field(description="Policy mode: AUTO or MANUAL")
    min_instances: Optional[int] = Field(
        default=None, description="Minimum running instances"
    )
    max_instances: Optional[int] = Field(
        default=None, description="Maximum running instances"
    )
