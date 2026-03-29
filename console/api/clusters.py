"""Cluster management API router for TCM Console."""

import logging
import os
from typing import Any, Dict, List

import yaml
from fastapi import APIRouter, HTTPException

from console.models.application import Application
from console.models.cluster import Cluster
from console.models.deployment import PolicyUpdateRequest
from console.services.node_manager import NodeManager
from console.services.policy_service import PolicyService
from shared.constants import AGENT_OFFLINE, HEALTH_UNHEALTHY, STATUS_RUNNING, STATUS_STOPPED

logger = logging.getLogger(__name__)

router = APIRouter(tags=["clusters"])


def _get_clusters() -> Dict[str, Cluster]:
    """Access the clusters dict from app state. Set during app startup."""
    return router.clusters  # type: ignore[attr-defined]


def _get_node_manager() -> NodeManager:
    return router.node_manager  # type: ignore[attr-defined]


def _get_policy_service() -> PolicyService:
    return router.policy_service  # type: ignore[attr-defined]


def _get_config_root() -> str:
    return router.config_root  # type: ignore[attr-defined]


def _get_applications() -> Dict[str, Application]:
    return router.applications  # type: ignore[attr-defined]


def _persist_cluster(cluster: Cluster, config_root: str) -> None:
    clusters_dir = os.path.join(config_root, "clusters")
    os.makedirs(clusters_dir, exist_ok=True)
    yaml_path = os.path.join(clusters_dir, f"{cluster.cluster_id}.yaml")
    with open(yaml_path, "w") as f:
        yaml.safe_dump(cluster.model_dump(), f, default_flow_style=False, sort_keys=False)


@router.post("/clusters", status_code=201)
async def create_cluster(cluster: Cluster) -> Dict[str, Any]:
    """Create a new cluster. Returns 409 if cluster_id already exists, 400 if app_id not found."""
    clusters = _get_clusters()
    if cluster.cluster_id in clusters:
        raise HTTPException(status_code=409, detail=f"Cluster already exists: {cluster.cluster_id}")

    applications = _get_applications()
    if cluster.app_id not in applications:
        raise HTTPException(status_code=400, detail=f"Application not found: {cluster.app_id}")

    clusters[cluster.cluster_id] = cluster

    try:
        _persist_cluster(cluster, _get_config_root())
    except (OSError, yaml.YAMLError) as exc:
        del clusters[cluster.cluster_id]
        logger.error("Failed to persist cluster %s: %s", cluster.cluster_id, exc)
        raise HTTPException(status_code=500, detail="Failed to persist cluster to disk")

    logger.info("Created cluster: %s", cluster.cluster_id)
    return cluster.model_dump()


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, cluster: Cluster) -> Dict[str, Any]:
    """Update an existing cluster. Returns 404 if not found, 400 if app_id not found."""
    clusters = _get_clusters()
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    applications = _get_applications()
    if cluster.app_id not in applications:
        raise HTTPException(status_code=400, detail=f"Application not found: {cluster.app_id}")

    cluster.cluster_id = cluster_id
    previous = clusters[cluster_id]
    clusters[cluster_id] = cluster

    try:
        _persist_cluster(cluster, _get_config_root())
    except (OSError, yaml.YAMLError) as exc:
        clusters[cluster_id] = previous
        logger.error("Failed to persist cluster %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Failed to persist cluster to disk")

    logger.info("Updated cluster: %s", cluster_id)
    return cluster.model_dump()


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str) -> Dict[str, Any]:
    """Delete a cluster. Returns 404 if not found."""
    clusters = _get_clusters()
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    removed = clusters.pop(cluster_id)

    try:
        config_root = _get_config_root()
        yaml_path = os.path.join(config_root, "clusters", f"{cluster_id}.yaml")
        if os.path.exists(yaml_path):
            os.remove(yaml_path)
    except OSError as exc:
        clusters[cluster_id] = removed
        logger.error("Failed to remove cluster file %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Failed to remove cluster from disk")

    logger.info("Deleted cluster: %s", cluster_id)
    return {"detail": f"Cluster deleted: {cluster_id}"}


@router.get("/clusters")
async def list_clusters() -> Dict[str, Any]:
    """Return list of all clusters with status summary."""
    clusters = _get_clusters()
    cluster_list = []
    for cluster in clusters.values():
        cluster_list.append({
            "cluster_id": cluster.cluster_id,
            "app_id": cluster.app_id,
            "policy_mode": cluster.policy.mode,
            "node_count": len(cluster.nodes),
        })
    return {"clusters": cluster_list}


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: str) -> Dict[str, Any]:
    """Return cluster config and current state."""
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")
    return cluster.model_dump()


@router.post("/clusters/{cluster_id}/policy")
async def update_policy(
    cluster_id: str, request: PolicyUpdateRequest
) -> Dict[str, Any]:
    """Update cluster policy (mode, min/max instances)."""
    clusters = _get_clusters()
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    policy_service = _get_policy_service()
    try:
        updated = policy_service.update_policy(
            cluster_id,
            request.mode,
            request.min_instances,
            request.max_instances,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if updated is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    # Persist to YAML
    config_root = _get_config_root()
    persisted = policy_service.persist_policy(cluster_id, config_root)
    if not persisted:
        logger.error(
            "Failed to persist policy for cluster %s to config root %s",
            cluster_id,
            config_root,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist policy for cluster: {cluster_id}",
        )

    return {"cluster_id": cluster_id, "policy": updated.model_dump()}


@router.post("/clusters/{cluster_id}/stop-all")
async def stop_all(cluster_id: str) -> Dict[str, Any]:
    """Stop all Tomcat instances in the cluster."""
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    node_manager = _get_node_manager()
    results: List[Dict[str, Any]] = []

    for node_id in cluster.nodes:
        node = node_manager.get_node(node_id)
        if node is None:
            results.append({"node_id": node_id, "status": "error", "error": "Node not found"})
            continue

        result = await node_manager.send_command(node_id, cluster.app_id, "stop")
        if result:
            results.append({"node_id": node_id, "status": "stopped"})
        else:
            results.append({"node_id": node_id, "status": "error", "error": "Agent unreachable"})

    stopped = sum(1 for r in results if r["status"] == "stopped")
    failed = sum(1 for r in results if r["status"] == "error")

    return {
        "cluster_id": cluster_id,
        "action": "stop-all",
        "stopped": stopped,
        "failed": failed,
        "results": results,
    }


@router.post("/clusters/{cluster_id}/start-all")
async def start_all(cluster_id: str) -> Dict[str, Any]:
    """Start Tomcat instances until min_instances is reached."""
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    node_manager = _get_node_manager()
    min_instances = cluster.policy.min_instances
    results: List[Dict[str, Any]] = []
    started = 0

    for node_id in cluster.nodes:
        if started >= min_instances:
            break

        node = node_manager.get_node(node_id)
        if node is None:
            results.append({"node_id": node_id, "status": "error", "error": "Node not found"})
            continue

        result = await node_manager.send_command(node_id, cluster.app_id, "start")
        if result:
            results.append({"node_id": node_id, "status": "started"})
            started += 1
        else:
            results.append({"node_id": node_id, "status": "error", "error": "Agent unreachable"})

    return {
        "cluster_id": cluster_id,
        "action": "start-all",
        "started": started,
        "target": min_instances,
        "results": results,
    }


@router.get("/clusters/{cluster_id}/status")
async def cluster_status(cluster_id: str) -> Dict[str, Any]:
    """Return cluster status summary with counts of running/stopped/unhealthy."""
    clusters = _get_clusters()
    cluster = clusters.get(cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"Cluster not found: {cluster_id}")

    node_manager = _get_node_manager()
    running = 0
    stopped = 0
    unhealthy = 0

    for node_id in cluster.nodes:
        node = node_manager.get_node(node_id)
        if node is None:
            continue
        tc = node.tomcats.get(cluster.app_id)
        if tc is None:
            continue
        if tc.status == STATUS_RUNNING:
            running += 1
            if tc.health_status == HEALTH_UNHEALTHY:
                unhealthy += 1
        elif tc.status == STATUS_STOPPED:
            stopped += 1

    return {
        "cluster_id": cluster_id,
        "running": running,
        "stopped": stopped,
        "unhealthy": unhealthy,
        "policy_mode": cluster.policy.mode,
    }
