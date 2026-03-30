"""High-level Tomcat lifecycle controller for TCM Agent.

Combines ProcessManager, WarDeployer, and HealthChecker into
a unified orchestration layer.
"""

import asyncio
import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from agent.health_checker import HealthChecker
from agent.process_manager import ProcessManager
from agent.war_deployer import WarDeployer
from shared.constants import (
    DEFAULT_PID_DIR,
    DEFAULT_TOMCAT_ROOT,
    GRACEFUL_STOP_TIMEOUT,
    HEALTH_CHECK_TIMEOUT,
    HEALTH_HEALTHY,
    HEALTH_UNKNOWN,
    STARTUP_TIMEOUT,
    STATUS_RUNNING,
    STATUS_STOPPED,
)

logger = logging.getLogger(__name__)


class TomcatController:
    """Orchestrates Tomcat lifecycle operations."""

    def __init__(
        self,
        tomcat_root: str = DEFAULT_TOMCAT_ROOT,
        pid_dir: str = DEFAULT_PID_DIR,
        graceful_stop_timeout: int = GRACEFUL_STOP_TIMEOUT,
        startup_timeout: int = STARTUP_TIMEOUT,
        health_check_timeout: int = HEALTH_CHECK_TIMEOUT,
    ) -> None:
        self._tomcat_root = tomcat_root
        self._startup_timeout = startup_timeout

        self.process_manager = ProcessManager(
            tomcat_root=tomcat_root,
            pid_dir=pid_dir,
            graceful_stop_timeout=graceful_stop_timeout,
        )
        self.war_deployer = WarDeployer(tomcat_root=tomcat_root)
        self.health_checker = HealthChecker(timeout=health_check_timeout)

        # Instance port mapping populated from config or discovery
        self._instance_ports: Dict[str, int] = {}
        self._health_endpoints: Dict[str, str] = {}

    def set_instance_port(self, app_id: str, port: int) -> None:
        """Register the HTTP port for an app instance."""
        self._instance_ports[app_id] = port

    def set_health_endpoint(self, app_id: str, endpoint: str) -> None:
        """Register a custom health endpoint for an app instance."""
        self._health_endpoints[app_id] = endpoint

    def get_instance_port(self, app_id: str) -> Optional[int]:
        """Get the HTTP port for an app instance."""
        return self._instance_ports.get(app_id)

    async def start(self, app_id: str) -> Dict[str, Any]:
        """Start a Tomcat instance and wait for health check.

        Args:
            app_id: Application identifier.

        Returns:
            Dict with status and details.
        """
        logger.info("Starting Tomcat instance: %s", app_id)

        success = self.process_manager.start_tomcat(app_id)
        if not success:
            return {"status": "error", "error": f"Failed to start Tomcat {app_id}"}

        # Wait for health check
        port = self._instance_ports.get(app_id)
        if port:
            endpoint = self._health_endpoints.get(app_id, "/health")
            health = await self._wait_for_health(app_id, port, endpoint)
            return {
                "status": "started",
                "app_id": app_id,
                "health": health,
                "pid": self.process_manager.get_tomcat_pid(app_id),
            }

        return {
            "status": "started",
            "app_id": app_id,
            "pid": self.process_manager.get_tomcat_pid(app_id),
        }

    async def stop(self, app_id: str) -> Dict[str, Any]:
        """Gracefully stop a Tomcat instance.

        Args:
            app_id: Application identifier.

        Returns:
            Dict with status and details.
        """
        logger.info("Stopping Tomcat instance: %s", app_id)

        success = self.process_manager.stop_tomcat(app_id)
        if not success:
            return {"status": "error", "error": f"Failed to stop Tomcat {app_id}"}

        return {"status": "stopped", "app_id": app_id}

    async def restart(self, app_id: str) -> Dict[str, Any]:
        """Restart a Tomcat instance (stop then start).

        Args:
            app_id: Application identifier.

        Returns:
            Dict with status and details.
        """
        logger.info("Restarting Tomcat instance: %s", app_id)

        stop_result = await self.stop(app_id)
        if stop_result["status"] == "error":
            return stop_result

        return await self.start(app_id)

    async def deploy(
        self,
        app_id: str,
        war_bytes: bytes,
        version: str,
        war_filename: str = "app.war",
        context_path: str = "/",
    ) -> Dict[str, Any]:
        """Full deploy workflow for a Tomcat instance.

        1. Stop tomcat (graceful)
        2. Backup and deploy new WAR
        3. Start tomcat
        4. Wait for health check
        5. Return success/failure

        Args:
            app_id: Application identifier.
            war_bytes: WAR file content as bytes.
            version: Version string.

        Returns:
            Dict with status and details.
        """
        logger.info("Deploying version %s to %s", version, app_id)

        # Step 1: Stop
        current_status = self.process_manager.get_tomcat_status(app_id)
        if current_status == STATUS_RUNNING:
            stop_result = await self.stop(app_id)
            if stop_result["status"] == "error":
                return {
                    "status": "error",
                    "error": f"Failed to stop {app_id} before deploy",
                    "phase": "stop",
                }

        # Step 2: Deploy WAR
        deploy_ok = self.war_deployer.deploy_war(
            app_id, war_bytes, version,
            war_filename=war_filename, context_path=context_path,
        )
        if not deploy_ok:
            return {
                "status": "error",
                "error": f"Failed to deploy WAR for {app_id}",
                "phase": "deploy",
            }

        # Step 3: Start
        start_result = await self.start(app_id)
        if start_result["status"] == "error":
            return {
                "status": "error",
                "error": f"Failed to start {app_id} after deploy",
                "phase": "start",
            }

        return {
            "status": "deployed",
            "app_id": app_id,
            "version": version,
            "health": start_result.get("health", HEALTH_UNKNOWN),
            "pid": start_result.get("pid"),
        }

    async def undeploy(self, app_id: str, war_filename: str = "app.war") -> Dict[str, Any]:
        """Stop a Tomcat instance and remove its WAR and expanded directory.

        Args:
            app_id: Application identifier.
            war_filename: Canonical WAR filename to remove.

        Returns:
            Dict with status and details.
        """
        logger.info("Undeploying %s from instance %s", war_filename, app_id)

        # Stop first if running
        if self.process_manager.get_tomcat_status(app_id) == STATUS_RUNNING:
            stop_result = await self.stop(app_id)
            if stop_result["status"] == "error":
                return {
                    "status": "error",
                    "error": f"Failed to stop {app_id} before undeploy",
                }

        ok = self.war_deployer.undeploy_war(app_id, war_filename)
        if not ok:
            return {"status": "error", "error": f"Failed to remove WAR for {app_id}"}

        return {"status": "undeployed", "app_id": app_id}

    def get_status(self, app_id: str) -> Dict[str, Any]:
        """Get the current status of a Tomcat instance.

        Args:
            app_id: Application identifier.

        Returns:
            Dict with status details.
        """
        status = self.process_manager.get_tomcat_status(app_id)
        pid = self.process_manager.get_tomcat_pid(app_id)
        has_war = self.war_deployer.get_current_war_exists(app_id)

        return {
            "app_id": app_id,
            "status": status,
            "pid": pid,
            "war_deployed": has_war,
        }

    def discover_instances(self) -> list[str]:
        """Discover Tomcat instances on this node.

        Also populates instance ports by parsing each instance's
        server.xml for the HTTP Connector port.

        Returns:
            List of app_id strings.
        """
        instances = self.process_manager.discover_instances()
        for app_id in instances:
            if app_id not in self._instance_ports:
                port = self._discover_port_from_server_xml(app_id)
                if port is not None:
                    self._instance_ports[app_id] = port
                    logger.debug(
                        "Discovered port %d for %s from server.xml", port, app_id
                    )
        return instances

    def _discover_port_from_server_xml(self, app_id: str) -> Optional[int]:
        """Parse server.xml to find the HTTP Connector port for an instance.

        Args:
            app_id: Application identifier.

        Returns:
            HTTP port integer or None if not found.
        """
        server_xml = os.path.join(self._tomcat_root, app_id, "conf", "server.xml")
        if not os.path.exists(server_xml):
            return None

        try:
            tree = ET.parse(server_xml)
            root = tree.getroot()
            for connector in root.iter("Connector"):
                protocol = connector.get("protocol", "HTTP/1.1")
                if "HTTP" in protocol.upper() or protocol == "":
                    port_str = connector.get("port")
                    if port_str is not None:
                        return int(port_str)
        except (ET.ParseError, ValueError, OSError) as exc:
            logger.warning(
                "Failed to parse server.xml for %s: %s", app_id, exc
            )

        return None

    async def _wait_for_health(
        self, app_id: str, port: int, endpoint: str
    ) -> str:
        """Wait for a Tomcat instance to become healthy.

        Args:
            app_id: Application identifier.
            port: HTTP port.
            endpoint: Health check URL path.

        Returns:
            Final health status string.
        """
        deadline = time.time() + self._startup_timeout
        while time.time() < deadline:
            health = await self.health_checker.check_health(app_id, port, endpoint)
            if health == HEALTH_HEALTHY:
                logger.info("Tomcat %s is healthy on port %d", app_id, port)
                return health
            await asyncio.sleep(2)

        logger.warning(
            "Tomcat %s did not become healthy within %ds", app_id, self._startup_timeout
        )
        return HEALTH_UNKNOWN
