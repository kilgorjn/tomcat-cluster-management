"""TCM Node Agent - FastAPI application entry point.

Per-node agent service that manages local Tomcat instances.
Provides REST API for lifecycle control, deployment, and status reporting.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tomcat_controller import TomcatController
from shared.config_loader import load_config
from shared.constants import (
    DEFAULT_AGENT_PORT,
    DEFAULT_PID_DIR,
    DEFAULT_TOMCAT_ROOT,
    GRACEFUL_STOP_TIMEOUT,
    HEALTH_CHECK_TIMEOUT,
    STARTUP_TIMEOUT,
)
from shared.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Global controller instance
_controller: TomcatController | None = None
_node_id: str = "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize controller on startup."""
    global _controller, _node_id

    # Load configuration
    try:
        config = load_config()
    except FileNotFoundError:
        logger.warning(
            "Config file not found, using defaults. Set CONFIG_PATH env var."
        )
        config = {"role": "agent", "agent": {}}

    agent_cfg = config.get("agent", {})
    _node_id = agent_cfg.get("node_id", "unknown")
    tomcat_root = agent_cfg.get("tomcat_root", DEFAULT_TOMCAT_ROOT)
    log_dir = agent_cfg.get("log_dir", "/var/log/tcm")
    log_level = config.get("logging", {}).get("level", "INFO")
    log_format = config.get("logging", {}).get("format", "json")

    tomcat_cfg = config.get("tomcat", {})
    graceful_stop_timeout = tomcat_cfg.get(
        "graceful_stop_timeout", GRACEFUL_STOP_TIMEOUT
    )
    startup_timeout = tomcat_cfg.get("startup_timeout", STARTUP_TIMEOUT)
    health_check_timeout = tomcat_cfg.get("health_check_timeout", HEALTH_CHECK_TIMEOUT)

    pid_dir = config.get("process_management", {}).get("pid_dir", DEFAULT_PID_DIR)

    setup_logging("agent", log_dir=log_dir, log_level=log_level, log_format=log_format)

    # Initialize TomcatController
    _controller = TomcatController(
        tomcat_root=tomcat_root,
        pid_dir=pid_dir,
        graceful_stop_timeout=graceful_stop_timeout,
        startup_timeout=startup_timeout,
        health_check_timeout=health_check_timeout,
    )

    # Discover existing instances
    instances = _controller.discover_instances()
    logger.info(
        "Node %s: discovered %d Tomcat instances: %s",
        _node_id,
        len(instances),
        instances,
    )

    logger.info("TCM Agent started (node: %s)", _node_id)
    yield
    logger.info("TCM Agent shutting down (node: %s)", _node_id)


app = FastAPI(
    title="TCM Node Agent",
    description="Tomcat Cluster Manager - Node Agent REST API",
    version="1.0.0",
    lifespan=lifespan,
)


def _get_controller() -> TomcatController:
    if _controller is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return _controller


def _validate_node_id(node_id: str) -> None:
    """Validate that the requested node_id matches this agent's node."""
    if node_id != _node_id:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")


@app.get("/nodes/{node_id}/status")
async def get_node_status(node_id: str) -> Dict[str, Any]:
    """Return status of all Tomcat instances on this node."""
    _validate_node_id(node_id)
    controller = _get_controller()

    instances = controller.discover_instances()
    tomcats: Dict[str, Any] = {}

    for app_id in instances:
        status_data = controller.get_status(app_id)
        port = controller.get_instance_port(app_id)

        # Perform health check if port is known and instance is running
        health = "unknown"
        if port and status_data["status"] == "running":
            health = await controller.health_checker.check_health(app_id, port)

        tomcats[app_id] = {
            "status": status_data["status"],
            "pid": status_data["pid"],
            "health": health,
            "version": "unknown",  # Version tracking requires metadata store
        }

    return {
        "node_id": _node_id,
        "tomcats": tomcats,
    }


@app.get("/nodes/{node_id}/tomcats/{app_id}/status")
async def get_tomcat_status(node_id: str, app_id: str) -> Dict[str, Any]:
    """Return status of a specific Tomcat instance."""
    _validate_node_id(node_id)
    controller = _get_controller()
    return controller.get_status(app_id)


@app.post("/nodes/{node_id}/tomcats/{app_id}/start")
async def start_tomcat(node_id: str, app_id: str) -> Dict[str, Any]:
    """Start a specific Tomcat instance."""
    _validate_node_id(node_id)
    controller = _get_controller()
    return await controller.start(app_id)


@app.post("/nodes/{node_id}/tomcats/{app_id}/stop")
async def stop_tomcat(node_id: str, app_id: str) -> Dict[str, Any]:
    """Stop a specific Tomcat instance."""
    _validate_node_id(node_id)
    controller = _get_controller()
    return await controller.stop(app_id)


@app.post("/nodes/{node_id}/tomcats/{app_id}/restart")
async def restart_tomcat(node_id: str, app_id: str) -> Dict[str, Any]:
    """Restart a specific Tomcat instance."""
    _validate_node_id(node_id)
    controller = _get_controller()
    return await controller.restart(app_id)


@app.post("/nodes/{node_id}/tomcats/{app_id}/deploy")
async def deploy_tomcat(
    node_id: str, app_id: str, request: Request
) -> Dict[str, Any]:
    """Receive WAR bytes and deploy to a specific Tomcat instance.

    Expects raw WAR bytes as request body with:
    - Content-Type: application/octet-stream
    - X-Deploy-Version: version string header
    """
    _validate_node_id(node_id)
    controller = _get_controller()

    version = request.headers.get("X-Deploy-Version", "unknown")
    war_filename = request.headers.get("X-War-Filename", "app.war")
    context_path = request.headers.get("X-Context-Path", "/")

    # Validate war_filename to prevent path traversal
    if (
        os.path.basename(war_filename) != war_filename
        or not war_filename.endswith(".war")
        or any(c in war_filename for c in ("\x00", "\n", "\r"))
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid war_filename: must be a simple *.war filename without path separators",
        )

    war_bytes = await request.body()

    if not war_bytes:
        raise HTTPException(status_code=400, detail="Empty WAR file")

    return await controller.deploy(
        app_id, war_bytes, version,
        war_filename=war_filename, context_path=context_path,
    )


@app.delete("/nodes/{node_id}/tomcats/{app_id}")
async def undeploy_tomcat(
    node_id: str,
    app_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Stop a Tomcat instance and remove its WAR and expanded directory.

    Optionally accepts X-War-Filename header to identify the WAR to remove.
    """
    _validate_node_id(node_id)
    controller = _get_controller()
    war_filename = request.headers.get("X-War-Filename", "app.war")
    return await controller.undeploy(app_id, war_filename)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Agent health check endpoint."""
    return {"status": "ok", "node_id": _node_id}


if __name__ == "__main__":
    config = {}
    try:
        config = load_config()
    except FileNotFoundError:
        pass

    agent_cfg = config.get("agent", {})
    port = agent_cfg.get("port", DEFAULT_AGENT_PORT)

    uvicorn.run(
        "agent.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
