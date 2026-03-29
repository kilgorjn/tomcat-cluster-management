"""Deployment API router for TCM Console."""

import logging
import tempfile
from typing import Any, Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from console.models.application import Application
from console.models.cluster import Cluster
from console.models.deployment import DeployRequest
from console.services.deployment_service import DeploymentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deployments"])


def _get_clusters() -> Dict[str, Cluster]:
    return router.clusters  # type: ignore[attr-defined]


def _get_deployment_service() -> DeploymentService:
    return router.deployment_service  # type: ignore[attr-defined]


def _get_applications() -> Dict[str, Application]:
    return router.applications  # type: ignore[attr-defined]


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

    # Resolve the Application for this cluster's app_id
    applications = _get_applications()
    application = applications.get(cluster.app_id)
    if application is None:
        raise HTTPException(
            status_code=404,
            detail=f"Application not found for cluster {cluster_id}: {cluster.app_id}",
        )

    deployment_service = _get_deployment_service()

    try:
        deployment = await deployment_service.start_deployment(
            cluster=cluster,
            war_path=request.war_path,
            version=request.version,
            war_filename=application.war_filename,
            context_path=application.context_path,
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


@router.post("/clusters/{cluster_id}/upload-deploy", status_code=202)
async def upload_deploy(
    cluster_id: str,
    war: UploadFile = File(..., description="WAR file to deploy"),
    version: str = Form(..., description="Version identifier for this deployment"),
) -> Dict[str, Any]:
    """Upload a WAR file and deploy it to all nodes in a cluster.

    Accepts a multipart/form-data POST with the WAR bytes and a version string.
    Writes the WAR to a temp file, then hands off to the deployment service.
    The deployment runs in the background; poll the returned deployment_id for status.
    """
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    applications = _get_applications()
    application = applications.get(cluster.app_id)
    if application is None:
        raise HTTPException(
            status_code=404,
            detail=f"Application not found for cluster {cluster_id}: {cluster.app_id}",
        )

    if not war.filename or not war.filename.endswith(".war"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .war file")

    war_bytes = await war.read()
    if not war_bytes:
        raise HTTPException(status_code=400, detail="Uploaded WAR file is empty")

    # Write to a named temp file so DeploymentService can read it by path
    with tempfile.NamedTemporaryFile(suffix=".war", delete=False) as tmp:
        tmp.write(war_bytes)
        tmp_path = tmp.name

    logger.info(
        "WAR upload for cluster %s: %s (%d bytes), version %s",
        cluster_id, war.filename, len(war_bytes), version,
    )

    deployment_service = _get_deployment_service()
    try:
        deployment = await deployment_service.start_deployment(
            cluster=cluster,
            war_path=tmp_path,
            version=version,
            war_filename=application.war_filename,
            context_path=application.context_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "deployment_id": deployment.deployment_id,
        "status": deployment.status,
        "cluster_id": cluster_id,
        "version": version,
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

    Rollback is now managed by the external deployment tool (Harness/UCD).
    """
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    raise HTTPException(
        status_code=501,
        detail="Rollback is managed by the external deployment tool (Harness/UCD)",
    )
