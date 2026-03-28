"""Cluster policy management service for TCM Console.

Manages cluster policies (AUTO/MANUAL mode, min/max instances).
The policy enforcement loop is stubbed for Phase 1 MVP and will
be activated in Phase 2.
"""

import logging
from typing import Any, Dict, Optional

import yaml

from console.models.cluster import Cluster, ClusterPolicy
from shared.constants import POLICY_AUTO, POLICY_MANUAL

logger = logging.getLogger(__name__)


class PolicyService:
    """Manages cluster policies and (future) enforcement."""

    def __init__(self) -> None:
        self._clusters: Dict[str, Cluster] = {}

    def load_clusters(self, clusters: Dict[str, Cluster]) -> None:
        """Load cluster references for policy management.

        Args:
            clusters: Dict of cluster_id -> Cluster objects.
        """
        self._clusters = clusters
        logger.info("PolicyService loaded %d clusters", len(clusters))

    def get_policy(self, cluster_id: str) -> Optional[ClusterPolicy]:
        """Get the current policy for a cluster.

        Args:
            cluster_id: The cluster identifier.

        Returns:
            ClusterPolicy object or None if cluster not found.
        """
        cluster = self._clusters.get(cluster_id)
        if cluster is None:
            return None
        return cluster.policy

    def update_policy(
        self,
        cluster_id: str,
        mode: str,
        min_instances: Optional[int] = None,
        max_instances: Optional[int] = None,
    ) -> Optional[ClusterPolicy]:
        """Update the policy for a cluster.

        Args:
            cluster_id: The cluster identifier.
            mode: New policy mode (AUTO or MANUAL).
            min_instances: New minimum instances (optional).
            max_instances: New maximum instances (optional).

        Returns:
            Updated ClusterPolicy or None if cluster not found.

        Raises:
            ValueError: If mode is invalid.
        """
        if mode not in (POLICY_AUTO, POLICY_MANUAL):
            raise ValueError(f"Invalid policy mode: {mode}")

        cluster = self._clusters.get(cluster_id)
        if cluster is None:
            return None

        cluster.policy.mode = mode
        if min_instances is not None:
            cluster.policy.min_instances = min_instances
        if max_instances is not None:
            cluster.policy.max_instances = max_instances

        logger.info(
            "Updated policy for cluster %s: mode=%s, min=%d, max=%d",
            cluster_id,
            cluster.policy.mode,
            cluster.policy.min_instances,
            cluster.policy.max_instances,
        )

        return cluster.policy

    def persist_policy(self, cluster_id: str, config_root: str) -> bool:
        """Persist a cluster's policy back to its YAML config file.

        Args:
            cluster_id: The cluster identifier.
            config_root: Root configuration directory path.

        Returns:
            True if persisted successfully, False otherwise.
        """
        cluster = self._clusters.get(cluster_id)
        if cluster is None:
            return False

        config_path = f"{config_root}/clusters/{cluster_id}.yaml"
        try:
            cluster_data = cluster.model_dump()
            # Remove fields that aren't part of the config file
            cluster_data.pop("previous_version", None)

            with open(config_path, "w") as f:
                yaml.safe_dump(cluster_data, f, default_flow_style=False, sort_keys=False)

            logger.info("Persisted policy for cluster %s to %s", cluster_id, config_path)
            return True
        except OSError as exc:
            logger.error("Failed to persist policy for %s: %s", cluster_id, exc)
            return False
