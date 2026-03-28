"""Deployment API router for TCM Console."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException

from console.models.cluster import Cluster
from console.models.deployment import DeployRequest
from console.services.deployment_service import DeploymentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deployments"])


def _get_clusters() -> Dict[str, Cluster]:
    return router.clusters  # type: ignore[attr-defined]


def _get_deployment_service() -> DeploymentService:
    return router.deployment_service  # type: ignore[attr-defined]


@router.post("/clusters/{cluster_id}/deploy")
async def deploy(cluster_id: str, request: DeployRequest) -> Dict[str, Any]:
    """Trigger a deployment to all nodes in a cluster.

    Accepts a WAR file path and version, distributes to all node agents
    via HTTP POST. The deployment runs as a background task and returns
    immediately with a deployment_id for status polling.
    """
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    deployment_service = _get_deployment_service()

    try:
        deployment = await deployment_service.start_deployment(
            cluster=cluster,
            war_path=request.war_path,
            version=request.version,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "deployment_id": deployment.deployment_id,
        "status": deployment.status,
        "cluster_id": cluster_id,
        "version": request.version,
        "nodes_total": deployment.nodes_total,
    }


@router.get("/clusters/{cluster_id}/deployments/{deployment_id}")
async def get_deployment_status(
    cluster_id: str, deployment_id: str
) -> Dict[str, Any]:
    """Return the current status of a deployment."""
    deployment_service = _get_deployment_service()
    deployment = deployment_service.get_deployment_status(deployment_id)

    if deployment is None:
        raise HTTPException(
            status_code=404, detail=f"Deployment not found: {deployment_id}"
        )

    if deployment.cluster_id != cluster_id:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment {deployment_id} not found in cluster {cluster_id}",
        )

    return deployment.model_dump()


@router.post("/clusters/{cluster_id}/rollback")
async def rollback(cluster_id: str) -> Dict[str, Any]:
    """Rollback cluster to previous version.

    Phase 1 MVP: Returns basic rollback status. Full rollback
    orchestration will be implemented in Phase 3.
    """
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    if cluster.previous_version is None:
        raise HTTPException(
            status_code=409,
            detail=f"No previous version available for cluster {cluster_id}",
        )

    return {
        "cluster_id": cluster_id,
        "message": "Rollback support is limited in Phase 1 MVP",
        "current_version": cluster.current_version,
        "previous_version": cluster.previous_version,
    }
