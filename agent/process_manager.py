"""Tomcat process management for TCM Agent.

Manages Tomcat Java processes using subprocess and psutil.
Handles start, stop (graceful), and status checking.
"""

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

from shared.constants import (
    DEFAULT_PID_DIR,
    DEFAULT_TOMCAT_ROOT,
    FORCE_KILL_WAIT,
    GRACEFUL_STOP_TIMEOUT,
    STATUS_CRASHED,
    STATUS_RUNNING,
    STATUS_STARTING,
    STATUS_STOPPED,
)

logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages Tomcat Java processes on the local node."""

    def __init__(
        self,
        tomcat_root: str = DEFAULT_TOMCAT_ROOT,
        pid_dir: str = DEFAULT_PID_DIR,
        graceful_stop_timeout: int = GRACEFUL_STOP_TIMEOUT,
    ) -> None:
        self._tomcat_root = tomcat_root
        self._pid_dir = pid_dir
        self._graceful_stop_timeout = graceful_stop_timeout

        # Ensure PID directory exists
        Path(self._pid_dir).mkdir(parents=True, exist_ok=True)

    def _pid_file(self, app_id: str) -> str:
        """Get the PID file path for an app."""
        return os.path.join(self._pid_dir, f"tomcat-{app_id}.pid")

    def _catalina_base(self, app_id: str) -> str:
        """Get the CATALINA_BASE path for an app."""
        return os.path.join(self._tomcat_root, app_id)

    def _catalina_home(self) -> str:
        """Get CATALINA_HOME (shared Tomcat installation).

        Falls back to CATALINA_HOME env var or /opt/tomcat.
        """
        return os.environ.get("CATALINA_HOME", "/opt/tomcat")

    def get_tomcat_pid(self, app_id: str) -> Optional[int]:
        """Read the PID from the PID file for an app.

        Args:
            app_id: Application identifier.

        Returns:
            PID integer or None if not found.
        """
        pid_file = self._pid_file(app_id)
        if not os.path.exists(pid_file):
            return None

        try:
            with open(pid_file, "r") as f:
                pid_str = f.read().strip()
                if pid_str:
                    return int(pid_str)
        except (ValueError, OSError) as exc:
            logger.warning("Failed to read PID file for %s: %s", app_id, exc)

        return None

    def _remove_pid(self, app_id: str) -> None:
        """Remove PID file."""
        pid_file = self._pid_file(app_id)
        if os.path.exists(pid_file):
            os.remove(pid_file)

    def get_tomcat_status(self, app_id: str) -> str:
        """Check if a Tomcat process is running.

        Args:
            app_id: Application identifier.

        Returns:
            Status string: running, stopped, or crashed.
        """
        pid = self.get_tomcat_pid(app_id)
        if pid is None:
            return STATUS_STOPPED

        if psutil.pid_exists(pid):
            try:
                proc = psutil.Process(pid)
                if proc.status() == psutil.STATUS_ZOMBIE:
                    return STATUS_CRASHED
                return STATUS_RUNNING
            except psutil.NoSuchProcess:
                return STATUS_STOPPED
        else:
            # PID file exists but process is gone
            self._remove_pid(app_id)
            return STATUS_CRASHED

    def start_tomcat(self, app_id: str) -> bool:
        """Start a Tomcat instance.

        Runs catalina.sh start with the appropriate CATALINA_BASE.
        Writes PID to the PID directory.

        Args:
            app_id: Application identifier.

        Returns:
            True if started successfully, False otherwise.
        """
        catalina_base = self._catalina_base(app_id)
        catalina_home = self._catalina_home()
        catalina_sh = os.path.join(catalina_home, "bin", "catalina.sh")

        if not os.path.exists(catalina_base):
            logger.error("CATALINA_BASE not found: %s", catalina_base)
            return False

        if not os.path.exists(catalina_sh):
            logger.error("catalina.sh not found: %s", catalina_sh)
            return False

        # Check if already running
        if self.get_tomcat_status(app_id) == STATUS_RUNNING:
            logger.warning("Tomcat %s is already running", app_id)
            return True

        env = os.environ.copy()
        env["CATALINA_BASE"] = catalina_base
        env["CATALINA_HOME"] = catalina_home
        env["CATALINA_PID"] = self._pid_file(app_id)

        try:
            logger.info("Starting Tomcat %s (base: %s)", app_id, catalina_base)
            result = subprocess.run(
                [catalina_sh, "start"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(
                    "Failed to start Tomcat %s: %s", app_id, result.stderr
                )
                return False

            logger.info("Tomcat %s started successfully", app_id)
            return True

        except subprocess.TimeoutExpired:
            logger.error("Timeout starting Tomcat %s", app_id)
            return False
        except OSError as exc:
            logger.error("Failed to execute catalina.sh for %s: %s", app_id, exc)
            return False

    def stop_tomcat(self, app_id: str) -> bool:
        """Gracefully stop a Tomcat instance.

        Follows the shutdown sequence:
        1. catalina.sh stop
        2. Wait graceful_stop_timeout
        3. SIGTERM if still running
        4. Wait 5 more seconds
        5. SIGKILL if still running

        Args:
            app_id: Application identifier.

        Returns:
            True if stopped successfully, False otherwise.
        """
        pid = self.get_tomcat_pid(app_id)
        if pid is None or not psutil.pid_exists(pid):
            logger.info("Tomcat %s is not running", app_id)
            self._remove_pid(app_id)
            return True

        catalina_base = self._catalina_base(app_id)
        catalina_home = self._catalina_home()
        catalina_sh = os.path.join(catalina_home, "bin", "catalina.sh")

        env = os.environ.copy()
        env["CATALINA_BASE"] = catalina_base
        env["CATALINA_HOME"] = catalina_home
        env["CATALINA_PID"] = self._pid_file(app_id)

        # Step 1: catalina.sh stop
        logger.info("Gracefully stopping Tomcat %s (pid: %d)", app_id, pid)
        try:
            subprocess.run(
                [catalina_sh, "stop"],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("catalina.sh stop failed for %s: %s", app_id, exc)

        # Step 2: Wait for graceful shutdown
        deadline = time.time() + self._graceful_stop_timeout
        while time.time() < deadline:
            if not psutil.pid_exists(pid):
                logger.info("Tomcat %s stopped gracefully", app_id)
                self._remove_pid(app_id)
                return True
            time.sleep(1)

        # Step 3: SIGTERM
        logger.warning(
            "Tomcat %s still running after graceful timeout, sending SIGTERM", app_id
        )
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self._remove_pid(app_id)
            return True

        # Step 4: Wait 5 more seconds
        deadline = time.time() + FORCE_KILL_WAIT
        while time.time() < deadline:
            if not psutil.pid_exists(pid):
                logger.info("Tomcat %s stopped after SIGTERM", app_id)
                self._remove_pid(app_id)
                return True
            time.sleep(1)

        # Step 5: SIGKILL
        logger.warning("Tomcat %s still running, sending SIGKILL", app_id)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            # Process already gone
            self._remove_pid(app_id)
            return True

        # Verify the process actually exited after SIGKILL with a short wait
        kill_deadline = time.time() + 5
        while time.time() < kill_deadline:
            if not psutil.pid_exists(pid):
                logger.info("Tomcat %s stopped after SIGKILL", app_id)
                self._remove_pid(app_id)
                return True
            time.sleep(0.5)

        logger.error("Tomcat %s still running after SIGKILL", app_id)
        return False

    def discover_instances(self) -> list[str]:
        """Discover Tomcat instances by scanning the tomcat_root directory.

        Returns:
            List of app_id strings found under tomcat_root.
        """
        root = Path(self._tomcat_root)
        if not root.exists():
            return []

        instances = []
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and (entry / "webapps").exists():
                instances.append(entry.name)

        return instances
