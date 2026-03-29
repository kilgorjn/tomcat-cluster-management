"""TCM Console Manager - FastAPI application entry point.

Central orchestration service for managing Tomcat clusters.
Provides REST API for cluster management, deployment orchestration,
and node monitoring.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from console.api import applications, clusters, deployments, monitoring, nodes
from console.models.application import Application
from console.models.cluster import Cluster, ClusterPolicy, DeploymentConfig
from console.services.deployment_service import DeploymentService
from console.services.node_manager import NodeManager
from console.services.policy_service import PolicyService
from shared.config_loader import load_application_configs, load_cluster_configs, load_config, load_node_configs
from shared.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONSOLE_PORT
from shared.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Global service instances
_applications: dict[str, Application] = {}
_clusters: dict[str, Cluster] = {}
_node_manager: NodeManager | None = None
_deployment_service: DeploymentService | None = None
_policy_service: PolicyService | None = None
_config_root: str = DEFAULT_CONFIG_ROOT


def _build_application(cfg: dict) -> Application:
    """Build an Application model from a raw config dict.

    Uses Application(**cfg) so Pydantic validates all required fields.
    """
    return Application(**cfg)


def _build_cluster(cfg: dict) -> Cluster:
    """Build a Cluster model from a raw config dict."""
    policy_data = cfg.get("policy", {})
    deploy_data = cfg.get("deployment", {})
    return Cluster(
        cluster_id=cfg["cluster_id"],
        app_id=cfg["app_id"],
        nodes=cfg.get("nodes", []),
        policy=ClusterPolicy(**policy_data),
        deployment=DeploymentConfig(**deploy_data),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize services on startup."""
    global _applications, _clusters, _node_manager, _deployment_service, _policy_service, _config_root

    # Load configuration
    try:
        config = load_config()
    except FileNotFoundError:
        logger.warning(
            "Config file not found, using defaults. Set CONFIG_PATH env var."
        )
        config = {"role": "console", "console": {}}

    console_cfg = config.get("console", {})
    _config_root = console_cfg.get("config_root", DEFAULT_CONFIG_ROOT)
    log_dir = console_cfg.get("log_dir", "/var/log/tcm")
    log_level = config.get("logging", {}).get("level", "INFO")
    log_format = config.get("logging", {}).get("format", "json")

    setup_logging("console", log_dir=log_dir, log_level=log_level, log_format=log_format)

    # Load application configs
    app_configs = load_application_configs(_config_root)
    for cfg in app_configs:
        try:
            application = _build_application(cfg)
            _applications[application.app_id] = application
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed application config %s: %s", cfg.get("app_id", "<unknown>"), exc)
    logger.info("Loaded %d application configurations", len(_applications))

    # Load cluster configs
    cluster_configs = load_cluster_configs(_config_root)
    for cfg in cluster_configs:
        cluster = _build_cluster(cfg)
        _clusters[cluster.cluster_id] = cluster
    logger.info("Loaded %d cluster configurations", len(_clusters))

    # Validate referential integrity: warn about clusters referencing unknown applications
    for cluster in _clusters.values():
        if cluster.app_id not in _applications:
            logger.warning(
                "Cluster %s references unknown application: %s",
                cluster.cluster_id,
                cluster.app_id,
            )

    # Load node configs and initialize NodeManager
    node_timeout = config.get("policy_enforcement", {}).get("node_timeout", 10)
    _node_manager = NodeManager(node_timeout=node_timeout)
    node_configs = load_node_configs(_config_root)
    _node_manager.load_nodes(node_configs)
    logger.info("Loaded %d node configurations", len(node_configs))

    # Initialize DeploymentService
    max_parallel = config.get("deployment", {}).get("max_parallel_nodes", 10)
    _deployment_service = DeploymentService(
        node_manager=_node_manager,
        max_parallel_nodes=max_parallel,
    )

    # Initialize PolicyService
    _policy_service = PolicyService()
    _policy_service.load_clusters(_clusters)

    # Attach services to routers
    clusters.router.clusters = _clusters  # type: ignore[attr-defined]
    clusters.router.node_manager = _node_manager  # type: ignore[attr-defined]
    clusters.router.policy_service = _policy_service  # type: ignore[attr-defined]
    clusters.router.config_root = _config_root  # type: ignore[attr-defined]
    clusters.router.applications = _applications  # type: ignore[attr-defined]

    deployments.router.clusters = _clusters  # type: ignore[attr-defined]
    deployments.router.deployment_service = _deployment_service  # type: ignore[attr-defined]
    deployments.router.applications = _applications  # type: ignore[attr-defined]

    applications.router.applications = _applications  # type: ignore[attr-defined]
    applications.router.clusters = _clusters  # type: ignore[attr-defined]
    applications.router.config_root = _config_root  # type: ignore[attr-defined]

    nodes.router.node_manager = _node_manager  # type: ignore[attr-defined]
    nodes.router.clusters = _clusters  # type: ignore[attr-defined]
    nodes.router.config_root = _config_root  # type: ignore[attr-defined]

    monitoring.router.clusters = _clusters  # type: ignore[attr-defined]
    monitoring.router.node_manager = _node_manager  # type: ignore[attr-defined]

    logger.info("TCM Console Manager started")
    yield
    logger.info("TCM Console Manager shutting down")


app = FastAPI(
    title="TCM Console Manager",
    description="Tomcat Cluster Manager - Central orchestration REST API",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(clusters.router, prefix="/api")
app.include_router(deployments.router, prefix="/api")
app.include_router(nodes.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(applications.router, prefix="/api")

# Serve Vue frontend static files (built output)
_frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    config = {}
    try:
        config = load_config()
    except FileNotFoundError:
        pass

    console_cfg = config.get("console", {})
    host = console_cfg.get("host", "0.0.0.0")
    port = console_cfg.get("port", DEFAULT_CONSOLE_PORT)

    uvicorn.run(
        "console.app:app",
        host=host,
        port=port,
        log_level="info",
    )
