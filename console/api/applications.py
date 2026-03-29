"""Application management API router for TCM Console."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from console.models.application import Application
from console.models.cluster import Cluster
from shared.config_loader import save_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["applications"])

_app_lock = asyncio.Lock()

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_id(value: str, label: str) -> None:
    if not _SAFE_ID_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}: must match [A-Za-z0-9_-]+")


def _get_applications() -> Dict[str, Application]:
    return router.applications  # type: ignore[attr-defined]


def _get_clusters() -> Dict[str, Cluster]:
    return router.clusters  # type: ignore[attr-defined]


def _get_config_root() -> str:
    return router.config_root  # type: ignore[attr-defined]


def _app_yaml_path(app_id: str, config_root: str) -> Path:
    apps_dir = Path(config_root) / "applications"
    target = apps_dir / f"{app_id}.yaml"
    if not str(target.resolve()).startswith(str(apps_dir.resolve())):
        raise OSError(f"Refusing to write outside config directory: {target}")
    return target


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
    _validate_id(application.app_id, "app_id")

    async with _app_lock:
        applications = _get_applications()
        if application.app_id in applications:
            raise HTTPException(
                status_code=409,
                detail=f"Application already exists: {application.app_id}",
            )

        applications[application.app_id] = application

        try:
            save_yaml(application.model_dump(), str(_app_yaml_path(application.app_id, _get_config_root())))
        except (OSError, Exception) as exc:
            del applications[application.app_id]
            logger.error("Failed to persist application %s: %s", application.app_id, exc)
            raise HTTPException(status_code=500, detail="Failed to persist application to disk")

    logger.info("Created application: %s", application.app_id)
    return application


@router.put("/{app_id}")
async def update_application(app_id: str, application: Application) -> Application:
    """Update an existing application. Returns 404 if not found."""
    _validate_id(app_id, "app_id")

    async with _app_lock:
        applications = _get_applications()
        if app_id not in applications:
            raise HTTPException(status_code=404, detail=f"Application not found: {app_id}")

        updated = application.model_copy(update={"app_id": app_id})
        previous = applications[app_id]
        applications[app_id] = updated

        try:
            save_yaml(updated.model_dump(), str(_app_yaml_path(app_id, _get_config_root())))
        except (OSError, Exception) as exc:
            applications[app_id] = previous
            logger.error("Failed to persist application %s: %s", app_id, exc)
            raise HTTPException(status_code=500, detail="Failed to persist application to disk")

    logger.info("Updated application: %s", app_id)
    return updated


@router.delete("/{app_id}")
async def delete_application(app_id: str) -> Dict[str, Any]:
    """Delete an application. Returns 404 if not found, 409 if referenced by a cluster."""
    _validate_id(app_id, "app_id")

    async with _app_lock:
        applications = _get_applications()
        if app_id not in applications:
            raise HTTPException(status_code=404, detail=f"Application not found: {app_id}")

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

        try:
            yaml_path = _app_yaml_path(app_id, _get_config_root())
            if yaml_path.exists():
                yaml_path.unlink()
        except OSError as exc:
            applications[app_id] = removed
            logger.error("Failed to remove application file %s: %s", app_id, exc)
            raise HTTPException(status_code=500, detail="Failed to remove application from disk")

    logger.info("Deleted application: %s", app_id)
    return {"detail": f"Application deleted: {app_id}"}
