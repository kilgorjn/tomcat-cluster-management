"""WAR file deployment handler for TCM Agent.

Manages WAR file backup, deployment, and rollback on the local node.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from shared.constants import DEFAULT_TOMCAT_ROOT, MAX_WAR_BACKUPS

logger = logging.getLogger(__name__)


class WarDeployer:
    """Handles WAR file deployment and backup management."""

    def __init__(self, tomcat_root: str = DEFAULT_TOMCAT_ROOT) -> None:
        self._tomcat_root = tomcat_root

    def _webapps_dir(self, app_id: str) -> str:
        """Get the webapps directory for an app."""
        return os.path.join(self._tomcat_root, app_id, "webapps")

    def _war_path(self, app_id: str) -> str:
        """Get the main WAR file path."""
        return os.path.join(self._webapps_dir(app_id), "app.war")

    def _backup_path(self, app_id: str, index: int) -> str:
        """Get a backup WAR file path."""
        return os.path.join(self._webapps_dir(app_id), f"app.war.{index}")

    def _rotate_backups(self, app_id: str) -> None:
        """Rotate WAR backups: app.war -> app.war.1, app.war.1 -> app.war.2, etc.

        Keeps the last MAX_WAR_BACKUPS backups.
        """
        self._rotate_backups_for(app_id, "app.war")

    def _rotate_backups_for(self, app_id: str, war_filename: str) -> None:
        """Rotate WAR backups for a given filename.

        Keeps the last MAX_WAR_BACKUPS backups.
        """
        webapps = self._webapps_dir(app_id)

        def _backup(index: int) -> str:
            return os.path.join(webapps, f"{war_filename}.{index}")

        # Remove oldest backup if it exists
        oldest = _backup(MAX_WAR_BACKUPS)
        if os.path.exists(oldest):
            os.remove(oldest)
            logger.debug("Removed oldest backup: %s", oldest)

        # Rotate existing backups
        for i in range(MAX_WAR_BACKUPS - 1, 0, -1):
            src = _backup(i)
            dst = _backup(i + 1)
            if os.path.exists(src):
                shutil.move(src, dst)
                logger.debug("Rotated backup: %s -> %s", src, dst)

        # Copy current WAR to backup slot 1 (original is overwritten by deploy)
        war = os.path.join(webapps, war_filename)
        if os.path.exists(war):
            backup1 = _backup(1)
            shutil.copy2(war, backup1)
            logger.info("Backed up current WAR: %s -> %s", war, backup1)

    def deploy_war(
        self,
        app_id: str,
        war_bytes: bytes,
        version: str,
        war_filename: str = "app.war",
        context_path: str = "/",
    ) -> bool:
        """Deploy a new WAR file for an application.

        1. Backup current WAR (rotate existing backups).
        2. Write new WAR bytes to webapps/{war_filename}.

        Args:
            app_id: Application identifier.
            war_bytes: WAR file content as bytes.
            version: Version string for logging.
            war_filename: Canonical WAR filename, e.g. 'BrokerageMobileWeb.war'.
            context_path: Tomcat context path (logged for reference).

        Returns:
            True if deployment successful, False otherwise.
        """
        webapps = self._webapps_dir(app_id)
        war_file = os.path.join(webapps, war_filename)

        # Ensure webapps directory exists
        os.makedirs(webapps, exist_ok=True)

        try:
            # Rotate backups using the dynamic filename
            self._rotate_backups_for(app_id, war_filename)

            # Write new WAR
            with open(war_file, "wb") as f:
                f.write(war_bytes)

            logger.info(
                "Deployed WAR for %s (version: %s, file: %s, context: %s, size: %d bytes)",
                app_id,
                version,
                war_filename,
                context_path,
                len(war_bytes),
            )
            return True

        except OSError as exc:
            logger.error("Failed to deploy WAR for %s: %s", app_id, exc)
            return False

    def rollback_war(self, app_id: str) -> bool:
        """Rollback to the previous WAR version.

        Restores app.war.1 -> app.war.

        Args:
            app_id: Application identifier.

        Returns:
            True if rollback successful, False otherwise.
        """
        war_file = self._war_path(app_id)
        backup1 = self._backup_path(app_id, 1)

        if not os.path.exists(backup1):
            logger.error("No backup available for rollback: %s", app_id)
            return False

        try:
            shutil.copy2(backup1, war_file)
            logger.info("Rolled back WAR for %s from %s", app_id, backup1)
            return True
        except OSError as exc:
            logger.error("Failed to rollback WAR for %s: %s", app_id, exc)
            return False

    def get_current_war_exists(self, app_id: str) -> bool:
        """Check if a WAR file exists for an app.

        Args:
            app_id: Application identifier.

        Returns:
            True if the WAR file exists.
        """
        return os.path.exists(self._war_path(app_id))
