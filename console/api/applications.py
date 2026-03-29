"""Application management API router for TCM Console."""

import logging
import os
from typing import Any, Dict, List

import yaml
from fastapi import APIRouter, HTTPException

from console.models.application import Application
from console.models.cluster import Cluster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["applications"])


def _get_applications() -> Dict[str, Application]:
    return router.applications  # type: ignore[attr-defined]


def _get_clusters() -> Dict[str, Cluster]:
    return router.clusters  # type: ignore[attr-defined]


def _get_config_root() -> str:
    return router.config_root  # type: ignore[attr-defined]


@router.get("")
async def list_applications() -> List[Application]:
    """Return list of all applications."""
    applications = _get_applications()
    return list(applications.values())


@router.get("/{app_id}")
async def get_application(app_id: str) -> Application:
    """Return a single application by app_id."""
    applications = _get_applications()
    application = applications.get(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail=f"Application not found: {app_id}")
    return application


@router.post("", status_code=201)
async def create_application(application: Application) -> Application:
    """Create a new application. Returns 409 if app_id already exists."""
    applications = _get_applications()
    if application.app_id in applications:
        raise HTTPException(
            status_code=409,
            detail=f"Application already exists: {application.app_id}",
        )

    applications[application.app_id] = application

    # Persist to YAML — rollback in-memory on failure
    try:
        config_root = _get_config_root()
        apps_dir = os.path.join(config_root, "applications")
        os.makedirs(apps_dir, exist_ok=True)
        yaml_path = os.path.join(apps_dir, f"{application.app_id}.yaml")
        with open(yaml_path, "w") as f:
            yaml.safe_dump(application.model_dump(), f, default_flow_style=False, sort_keys=False)
    except (OSError, yaml.YAMLError) as exc:
        del applications[application.app_id]
        logger.error("Failed to persist application %s: %s", application.app_id, exc)
        raise HTTPException(status_code=500, detail="Failed to persist application to disk")

    logger.info("Created application: %s", application.app_id)
    return application


@router.put("/{app_id}")
async def update_application(app_id: str, application: Application) -> Application:
    """Update an existing application. Returns 404 if not found."""
    applications = _get_applications()
    if app_id not in applications:
        raise HTTPException(status_code=404, detail=f"Application not found: {app_id}")

    previous = applications[app_id]
    applications[app_id] = application

    # Persist to YAML — rollback in-memory on failure
    try:
        config_root = _get_config_root()
        apps_dir = os.path.join(config_root, "applications")
        os.makedirs(apps_dir, exist_ok=True)
        yaml_path = os.path.join(apps_dir, f"{app_id}.yaml")
        with open(yaml_path, "w") as f:
            yaml.safe_dump(application.model_dump(), f, default_flow_style=False, sort_keys=False)
    except (OSError, yaml.YAMLError) as exc:
        applications[app_id] = previous
        logger.error("Failed to persist application %s: %s", app_id, exc)
        raise HTTPException(status_code=500, detail="Failed to persist application to disk")

    logger.info("Updated application: %s", app_id)
    return application


@router.delete("/{app_id}")
async def delete_application(app_id: str) -> Dict[str, Any]:
    """Delete an application. Returns 404 if not found, 409 if referenced by a cluster."""
    applications = _get_applications()
    if app_id not in applications:
        raise HTTPException(status_code=404, detail=f"Application not found: {app_id}")

    # Check if any cluster references this app_id
    clusters = _get_clusters()
    referencing_clusters = [
        c.cluster_id for c in clusters.values() if c.app_id == app_id
    ]
    if referencing_clusters:
        raise HTTPException(
            status_code=409,
            detail=f"Application {app_id} is referenced by clusters: {referencing_clusters}",
        )

    removed = applications.pop(app_id)

    # Remove YAML file — rollback in-memory on failure
    try:
        config_root = _get_config_root()
        yaml_path = os.path.join(config_root, "applications", f"{app_id}.yaml")
        if os.path.exists(yaml_path):
            os.remove(yaml_path)
    except OSError as exc:
        applications[app_id] = removed
        logger.error("Failed to remove application file %s: %s", app_id, exc)
        raise HTTPException(status_code=500, detail="Failed to remove application from disk")

    logger.info("Deleted application: %s", app_id)
    return {"detail": f"Application deleted: {app_id}"}
