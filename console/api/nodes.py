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
        # Normalize agent response to match console schema
        return _normalize_node_status(node, status)

    # Agent unreachable - return cached state
    return _normalize_node_status(node, None)


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
        agent_tc = status["tomcats"][app_id]
        return _normalize_tomcat_status(app_id, agent_tc)

    # Fall back to cached state
    tc = node.tomcats.get(app_id)
    if tc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tomcat {app_id} not found on node {node_id}",
        )
    return tc.model_dump()


def _normalize_node_status(
    node: Any, agent_status: Any
) -> Dict[str, Any]:
    """Normalize node status into a consistent response schema.

    Whether the data comes from a live agent poll or cached state,
    the response always has the same shape.
    """
    tomcats: Dict[str, Any] = {}

    if agent_status and "tomcats" in agent_status:
        # Use live agent data but normalize each tomcat entry
        for tc_id, tc_data in agent_status["tomcats"].items():
            tomcats[tc_id] = _normalize_tomcat_status(tc_id, tc_data)
    else:
        # Use cached state from console
        for tc_id, tc in node.tomcats.items():
            tomcats[tc_id] = tc.model_dump()

    return {
        "node_id": node.node_id,
        "agent_status": node.agent_status,
        "tomcats": tomcats,
    }


def _normalize_tomcat_status(
    app_id: str, data: Any
) -> Dict[str, Any]:
    """Normalize a single tomcat status entry to a consistent schema."""
    if isinstance(data, dict):
        return {
            "app_id": data.get("app_id", app_id),
            "status": data.get("status", "unknown"),
            "pid": data.get("pid"),
            "health": data.get("health", data.get("health_status", "unknown")),
            "war_deployed": data.get("war_deployed"),
        }
    return {"app_id": app_id, "status": "unknown", "pid": None, "health": "unknown"}


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
