"""Deployment orchestration service for TCM Console.

Manages the lifecycle of deployments: distributing WAR files to nodes,
tracking per-node completion, and updating cluster state.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from console.models.cluster import Cluster
from console.models.deployment import DeploymentStatus
from console.services.node_manager import NodeManager
from shared.constants import DEPLOY_COMPLETED, DEPLOY_FAILED, DEPLOY_IN_PROGRESS
from shared.utils import generate_deployment_id, utc_now

logger = logging.getLogger(__name__)


class DeploymentService:
    """Orchestrates WAR deployments across cluster nodes."""

    def __init__(
        self,
        node_manager: NodeManager,
        max_parallel_nodes: int = 10,
    ) -> None:
        self._node_manager = node_manager
        self._max_parallel_nodes = max_parallel_nodes
        self._deployments: Dict[str, DeploymentStatus] = {}
        self._lock = asyncio.Lock()

    def get_deployment_status(
        self, deployment_id: str
    ) -> Optional[DeploymentStatus]:
        """Get the current status of a deployment.

        Args:
            deployment_id: The deployment identifier.

        Returns:
            DeploymentStatus object or None if not found.
        """
        return self._deployments.get(deployment_id)

    async def start_deployment(
        self,
        cluster: Cluster,
        war_path: str,
        version: str,
    ) -> DeploymentStatus:
        """Start a deployment to all nodes in a cluster.

        Reads the WAR file, creates a deployment record, and begins
        distributing to nodes in the background.

        Args:
            cluster: Target cluster.
            war_path: Path to the WAR file on staging.
            version: Version string for the deployment.

        Returns:
            DeploymentStatus with initial state.

        Raises:
            FileNotFoundError: If the WAR file does not exist.
        """
        war_file = Path(war_path)
        if not war_file.exists():
            raise FileNotFoundError(f"WAR file not found: {war_path}")

        war_bytes = war_file.read_bytes()

        deployment_id = generate_deployment_id()
        node_ids = cluster.nodes
        deployment = DeploymentStatus(
            deployment_id=deployment_id,
            cluster_id=cluster.cluster_id,
            version=version,
            status=DEPLOY_IN_PROGRESS,
            nodes_total=len(node_ids),
            started_at=utc_now(),
        )
        self._deployments[deployment_id] = deployment

        logger.info(
            "Starting deployment %s for cluster %s (version %s, %d nodes)",
            deployment_id,
            cluster.cluster_id,
            version,
            len(node_ids),
        )

        # Launch background deployment task with top-level error handling
        asyncio.create_task(
            self._safe_execute_deployment(
                deployment, cluster, node_ids, war_bytes, version
            )
        )

        return deployment

    async def _safe_execute_deployment(
        self,
        deployment: DeploymentStatus,
        cluster: Cluster,
        node_ids: List[str],
        war_bytes: bytes,
        version: str,
    ) -> None:
        """Wrapper that catches exceptions so the task never fails silently."""
        try:
            await self._execute_deployment(
                deployment, cluster, node_ids, war_bytes, version
            )
        except Exception as exc:
            logger.exception(
                "Deployment %s failed with unexpected error: %s",
                deployment.deployment_id,
                exc,
            )
            deployment.status = DEPLOY_FAILED
            deployment.errors.append(f"Unexpected error: {exc}")
            deployment.completed_at = utc_now()

    async def _execute_deployment(
        self,
        deployment: DeploymentStatus,
        cluster: Cluster,
        node_ids: List[str],
        war_bytes: bytes,
        version: str,
    ) -> None:
        """Execute the deployment across nodes with bounded parallelism.

        Args:
            deployment: The deployment status to update.
            cluster: Target cluster.
            node_ids: List of node IDs to deploy to.
            war_bytes: WAR file content.
            version: Version string.
        """
        semaphore = asyncio.Semaphore(self._max_parallel_nodes)

        async def deploy_single_node(node_id: str) -> bool:
            async with semaphore:
                logger.info(
                    "Deploying %s to node %s",
                    deployment.deployment_id,
                    node_id,
                )
                result = await self._node_manager.deploy_to_node(
                    node_id, cluster.app_id, war_bytes, version
                )
                if result and result.get("status") != "error":
                    async with self._lock:
                        deployment.nodes_completed += 1
                    logger.info(
                        "Node %s completed (%d/%d)",
                        node_id,
                        deployment.nodes_completed,
                        deployment.nodes_total,
                    )
                    return True
                else:
                    error_msg = (
                        result.get("error", "Unknown error")
                        if result
                        else f"Agent unreachable on {node_id}"
                    )
                    deployment.errors.append(f"{node_id}: {error_msg}")
                    logger.error(
                        "Deployment failed on node %s: %s", node_id, error_msg
                    )
                    return False

        tasks = [deploy_single_node(nid) for nid in node_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                deployment.errors.append(f"{node_ids[i]}: {result}")

        # Determine final status
        if deployment.nodes_completed == deployment.nodes_total:
            deployment.status = DEPLOY_COMPLETED
            cluster.previous_version = cluster.current_version
            cluster.current_version = version
            logger.info(
                "Deployment %s completed successfully", deployment.deployment_id
            )
        else:
            deployment.status = DEPLOY_FAILED
            logger.error(
                "Deployment %s failed: %d/%d nodes completed",
                deployment.deployment_id,
                deployment.nodes_completed,
                deployment.nodes_total,
            )

        deployment.completed_at = utc_now()
