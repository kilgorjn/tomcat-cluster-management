"""Monitoring API router for TCM Console."""

from typing import Any, Dict

from fastapi import APIRouter

from console.models.cluster import Cluster
from console.services.node_manager import NodeManager
from shared.constants import STATUS_RUNNING

router = APIRouter(tags=["monitoring"])


def _get_clusters() -> Dict[str, Cluster]:
    return router.clusters  # type: ignore[attr-defined]


def _get_node_manager() -> NodeManager:
    return router.node_manager  # type: ignore[attr-defined]


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Console health check endpoint."""
    return {"status": "ok"}


@router.get("/status")
async def system_status() -> Dict[str, Any]:
    """Overall system status summary."""
    clusters = _get_clusters()
    node_manager = _get_node_manager()
    nodes = node_manager.get_all_nodes()

    total_tomcats = 0
    running_tomcats = 0
    for node in nodes:
        total_tomcats += len(node.tomcats)
        for tc in node.tomcats.values():
            if tc.status == STATUS_RUNNING:
                running_tomcats += 1

    return {
        "total_clusters": len(clusters),
        "total_nodes": len(nodes),
        "total_tomcats": total_tomcats,
        "running_tomcats": running_tomcats,
    }
