"""Node management API router for TCM Console."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from console.services.node_manager import NodeManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nodes"])


def _get_node_manager() -> NodeManager:
    return router.node_manager  # type: ignore[attr-defined]


@router.get("/nodes")
async def list_nodes() -> Dict[str, Any]:
    """Return list of all nodes with status."""
    node_manager = _get_node_manager()
    nodes = node_manager.get_all_nodes()
    node_list = []
    for node in nodes:
        node_list.append({
            "node_id": node.node_id,
            "hostname": node.hostname,
            "ip_address": node.ip_address,
            "agent_port": node.agent_port,
            "agent_status": node.agent_status,
            "tomcat_count": len(node.tomcats),
        })
    return {"nodes": node_list}


@router.get("/nodes/{node_id}/status")
async def get_node_status(node_id: str) -> Dict[str, Any]:
    """Poll the node agent and return current status."""
    node_manager = _get_node_manager()
    node = node_manager.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    # Poll agent for live status
    status = await node_manager.poll_node_status(node_id)
    if status is not None:
        return status

    # Agent unreachable - return cached state
    return {
        "node_id": node.node_id,
        "agent_status": node.agent_status,
        "tomcats": {
            app_id: tc.model_dump()
            for app_id, tc in node.tomcats.items()
        },
    }


@router.get("/nodes/{node_id}/tomcats/{app_id}/status")
async def get_tomcat_status(node_id: str, app_id: str) -> Dict[str, Any]:
    """Proxy status request for a specific tomcat instance to the agent."""
    node_manager = _get_node_manager()
    node = node_manager.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    # Try to poll agent
    status = await node_manager.poll_node_status(node_id)
    if status and "tomcats" in status and app_id in status["tomcats"]:
        return status["tomcats"][app_id]

    # Fall back to cached state
    tc = node.tomcats.get(app_id)
    if tc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tomcat {app_id} not found on node {node_id}",
        )
    return tc.model_dump()


@router.post("/nodes/{node_id}/tomcats/{app_id}/start")
async def start_tomcat(node_id: str, app_id: str) -> Dict[str, Any]:
    """Forward start command to the node agent."""
    node_manager = _get_node_manager()
    node = node_manager.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    result = await node_manager.send_command(node_id, app_id, "start")
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to communicate with agent on {node_id}",
        )
    return result


@router.post("/nodes/{node_id}/tomcats/{app_id}/stop")
async def stop_tomcat(node_id: str, app_id: str) -> Dict[str, Any]:
    """Forward stop command to the node agent."""
    node_manager = _get_node_manager()
    node = node_manager.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    result = await node_manager.send_command(node_id, app_id, "stop")
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to communicate with agent on {node_id}",
        )
    return result


@router.post("/nodes/{node_id}/tomcats/{app_id}/restart")
async def restart_tomcat(node_id: str, app_id: str) -> Dict[str, Any]:
    """Forward restart command to the node agent."""
    node_manager = _get_node_manager()
    node = node_manager.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    result = await node_manager.send_command(node_id, app_id, "restart")
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to communicate with agent on {node_id}",
        )
    return result
