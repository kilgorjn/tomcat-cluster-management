"""Health check module for TCM Agent.

Performs HTTP health checks against local Tomcat instances.
"""

import logging

import httpx

from shared.constants import HEALTH_CHECK_TIMEOUT, HEALTH_HEALTHY, HEALTH_UNHEALTHY, HEALTH_UNKNOWN

logger = logging.getLogger(__name__)


class HealthChecker:
    """Performs health checks on local Tomcat instances."""

    def __init__(self, timeout: int = HEALTH_CHECK_TIMEOUT) -> None:
        self._timeout = timeout

    async def check_health(
        self,
        app_id: str,
        instance_port: int,
        health_endpoint: str = "/health",
        timeout: int | None = None,
    ) -> str:
        """Check health of a Tomcat instance via HTTP GET.

        Args:
            app_id: Application identifier (for logging).
            instance_port: HTTP port of the Tomcat instance.
            health_endpoint: Health check URL path.
            timeout: Request timeout in seconds (uses default if None).

        Returns:
            "healthy" if 200 OK, "unhealthy" if non-200, "unknown" on error.
        """
        if timeout is None:
            timeout = self._timeout

        url = f"http://localhost:{instance_port}{health_endpoint}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    logger.debug("Health check OK for %s on port %d", app_id, instance_port)
                    return HEALTH_HEALTHY
                else:
                    logger.warning(
                        "Health check failed for %s on port %d: HTTP %d",
                        app_id,
                        instance_port,
                        response.status_code,
                    )
                    return HEALTH_UNHEALTHY
        except httpx.TimeoutException:
            logger.warning(
                "Health check timeout for %s on port %d", app_id, instance_port
            )
            return HEALTH_UNKNOWN
        except httpx.ConnectError:
            logger.debug(
                "Health check connection error for %s on port %d",
                app_id,
                instance_port,
            )
            return HEALTH_UNKNOWN
        except httpx.HTTPError as exc:
            logger.warning(
                "Health check error for %s on port %d: %s",
                app_id,
                instance_port,
                exc,
            )
            return HEALTH_UNKNOWN
