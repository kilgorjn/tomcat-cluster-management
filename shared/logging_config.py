"""Structured logging configuration for TCM."""

import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields
        for key in ("node_id", "cluster_id", "app_id", "deployment_id", "event"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        return json.dumps(log_entry)


def setup_logging(
    role: str,
    log_dir: Optional[str] = None,
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure logging for the TCM application.

    Args:
        role: 'console' or 'agent' - determines log file name.
        log_dir: Directory for log files. Defaults to /var/log/tcm.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: 'json' for structured logging, 'text' for plain text.
    """
    if log_dir is None:
        log_dir = os.environ.get("TCM_LOG_DIR", "/var/log/tcm")

    level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Choose formatter
    if log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    log_path = Path(log_dir)
    if log_path.exists() and os.access(str(log_path), os.W_OK):
        log_file = log_path / f"tcm-{role}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file),
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=5,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
