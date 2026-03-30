"""Node management service for TCM Console.

Maintains in-memory state of all nodes and provides communication
with node agents via HTTP.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from console.models.node import Node, TomcatInstance
from shared.constants import AGENT_OFFLINE, AGENT_ONLINE, HEALTH_CHECK_TIMEOUT
from shared.utils import utc_now

logger = logging.getLogger(__name__)


class NodeManager:
    """Manages node state and communication with node agents."""

    def __init__(self, node_timeout: int = HEALTH_CHECK_TIMEOUT) -> None:
        self._nodes: Dict[str, Node] = {}
        self._node_timeout = node_timeout

    def load_nodes(self, node_configs: List[Dict[str, Any]]) -> None:
        """Load node configurations from parsed YAML configs.

        Args:
            node_configs: List of node configuration dicts from YAML files.
        """
        for nc in node_configs:
            node_id = nc["node_id"]
            tomcats: Dict[str, TomcatInstance] = {}
            for tc in nc.get("tomcats", []):
                tomcats[tc["app_id"]] = TomcatInstance(
                    app_id=tc["app_id"],
                    instance_port=tc["instance_port"],
                    ajp_port=tc["ajp_port"],
                    status=tc.get("status", "stopped"),
                )

            self._nodes[node_id] = Node(
                node_id=node_id,
                hostname=nc["hostname"],
                ip_address=nc["ip_address"],
                agent_port=nc.get("agent_port", 9001),
                tomcats=tomcats,
            )
            logger.info("Loaded node: %s (%s)", node_id, nc["hostname"])

    def get_node(self, node_id: str) -> Optional[Node]:
        """Return a node by ID.

        Args:
            node_id: The node identifier.

        Returns:
            Node object or None if not found.
        """
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> List[Node]:
        """Return all registered nodes.

        Returns:
            List of all Node objects.
        """
        return list(self._nodes.values())

    def add_node(self, node: Node) -> None:
        """Add a node to the registry.

        Args:
            node: Node to add.

        Raises:
            ValueError: If node_id already exists.
        """
        if node.node_id in self._nodes:
            raise ValueError(f"Node already exists: {node.node_id}")
        self._nodes[node.node_id] = node

    def update_node(self, node: Node) -> None:
        """Replace an existing node in the registry.

        Args:
            node: Updated node (must already exist).

        Raises:
            ValueError: If node_id is not found.
        """
        if node.node_id not in self._nodes:
            raise ValueError(f"Node not found: {node.node_id}")
        self._nodes[node.node_id] = node

    def remove_node(self, node_id: str) -> Node:
        """Remove a node from the registry and return it.

        Args:
            node_id: ID of the node to remove.

        Raises:
            ValueError: If node_id is not found.
        """
        if node_id not in self._nodes:
            raise ValueError(f"Node not found: {node_id}")
        return self._nodes.pop(node_id)

    def get_nodes_for_cluster(self, node_ids: List[str]) -> List[Node]:
        """Return nodes matching the given IDs.

        Args:
            node_ids: List of node IDs to look up.

        Returns:
            List of matching Node objects.
        """
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def _agent_url(self, node: Node) -> str:
        """Build the base URL for a node agent.

        Args:
            node: Node object.

        Returns:
            Base URL string.
        """
        return f"http://{node.ip_address}:{node.agent_port}"

    async def poll_node_status(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Poll a node agent for current status.

        Args:
            node_id: The node identifier.

        Returns:
            Status dict from agent, or None on failure.
        """
        node = self.get_node(node_id)
        if node is None:
            return None

        url = f"{self._agent_url(node)}/nodes/{node_id}/status"
        try:
            async with httpx.AsyncClient(timeout=self._node_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                node.agent_status = AGENT_ONLINE
                node.last_heartbeat = utc_now()

                # Update local tomcat state from agent response
                for app_id, tc_data in data.get("tomcats", {}).items():
                    if app_id in node.tomcats:
                        node.tomcats[app_id].status = tc_data.get(
                            "status", node.tomcats[app_id].status
                        )
                        node.tomcats[app_id].pid = tc_data.get("pid")
                        node.tomcats[app_id].health_status = tc_data.get(
                            "health", "unknown"
                        )
                        node.tomcats[app_id].last_health_check = utc_now()

                return data
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            logger.warning("Failed to poll node %s: %s", node_id, exc)
            node.agent_status = AGENT_OFFLINE
            return None

    async def send_command(
        self, node_id: str, app_id: str, action: str
    ) -> Optional[Dict[str, Any]]:
        """Send a command to a node agent for a specific tomcat instance.

        Args:
            node_id: Target node identifier.
            app_id: Target application identifier.
            action: Action to perform (start, stop, restart).

        Returns:
            Response dict from agent, or None on failure.
        """
        node = self.get_node(node_id)
        if node is None:
            logger.error("Node not found: %s", node_id)
            return None

        url = f"{self._agent_url(node)}/nodes/{node_id}/tomcats/{app_id}/{action}"
        try:
            async with httpx.AsyncClient(timeout=self._node_timeout) as client:
                response = await client.post(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            logger.error(
                "Failed to send %s to %s/%s: %s", action, node_id, app_id, exc
            )
            node.agent_status = AGENT_OFFLINE
            return None

    async def deploy_to_node(
        self,
        node_id: str,
        app_id: str,
        war_bytes: bytes,
        version: str,
        war_filename: str = "app.war",
        context_path: str = "/",
    ) -> Optional[Dict[str, Any]]:
        """Send WAR file to a node agent for deployment.

        Args:
            node_id: Target node identifier.
            app_id: Target application identifier.
            war_bytes: WAR file content as bytes.
            version: Version string for the deployment.
            war_filename: Canonical WAR filename.
            context_path: Tomcat context path.

        Returns:
            Response dict from agent, or None on failure.
        """
        node = self.get_node(node_id)
        if node is None:
            logger.error("Node not found: %s", node_id)
            return None

        url = f"{self._agent_url(node)}/nodes/{node_id}/tomcats/{app_id}/deploy"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=10.0)
            ) as client:
                response = await client.post(
                    url,
                    content=war_bytes,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Deploy-Version": version,
                        "X-War-Filename": war_filename,
                        "X-Context-Path": context_path,
                    },
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            logger.error("Failed to deploy to %s/%s: %s", node_id, app_id, exc)
            node.agent_status = AGENT_OFFLINE
            return None

    async def undeploy_from_node(
        self, node_id: str, app_id: str
    ) -> Optional[Dict[str, Any]]:
        """Tell a node agent to stop and remove an application.

        Args:
            node_id: Target node identifier.
            app_id: Target application identifier.

        Returns:
            Response dict from agent, or None on failure.
        """
        node = self.get_node(node_id)
        if node is None:
            logger.error("Node not found: %s", node_id)
            return None

        url = f"{self._agent_url(node)}/nodes/{node_id}/tomcats/{app_id}"
        try:
            async with httpx.AsyncClient(timeout=self._node_timeout) as client:
                response = await client.delete(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            logger.error("Failed to undeploy %s from %s: %s", app_id, node_id, exc)
            node.agent_status = AGENT_OFFLINE
            return None
