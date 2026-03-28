"""Common utility functions for TCM."""

import time
import uuid
from datetime import datetime, timezone


def generate_deployment_id() -> str:
    """Generate a unique deployment ID.

    Returns:
        A deployment ID string like 'deploy-a1b2c3d4'.
    """
    short_uuid = uuid.uuid4().hex[:8]
    return f"deploy-{short_uuid}"


def generate_command_id() -> str:
    """Generate a unique command ID.

    Returns:
        A command ID string like 'cmd-a1b2c3d4'.
    """
    short_uuid = uuid.uuid4().hex[:8]
    return f"cmd-{short_uuid}"


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware).

    Returns:
        Current UTC datetime.
    """
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime) -> str:
    """Format a datetime as an ISO 8601 string.

    Args:
        dt: Datetime to format.

    Returns:
        ISO 8601 formatted string.
    """
    return dt.isoformat()


def elapsed_seconds(start_time: float) -> float:
    """Calculate elapsed seconds since a start time.

    Args:
        start_time: Start time from time.time().

    Returns:
        Elapsed seconds as a float.
    """
    return time.time() - start_time
