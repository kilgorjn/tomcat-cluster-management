"""YAML configuration loader for TCM console and agent."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from shared.constants import DEFAULT_CONFIG_PATH, DEFAULT_CONFIG_ROOT

logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load the main TCM configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses CONFIG_PATH env var
                     or falls back to DEFAULT_CONFIG_PATH.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the config file is invalid YAML.
    """
    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH", DEFAULT_CONFIG_PATH)

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r") as f:
        config = yaml.safe_load(f) or {}

    return config


def get_role(config: Dict[str, Any]) -> str:
    """Extract the role (console or agent) from configuration.

    Args:
        config: Parsed configuration dictionary.

    Returns:
        Role string ('console' or 'agent').

    Raises:
        ValueError: If role is not specified or invalid.
    """
    role = config.get("role")
    if role not in ("console", "agent"):
        raise ValueError(f"Invalid or missing role in config: {role}")
    return role


def load_cluster_configs(config_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load all cluster configuration files from {config_root}/clusters/*.yaml.

    Args:
        config_root: Root configuration directory. Defaults to /etc/tcm.

    Returns:
        List of cluster configuration dictionaries.
    """
    if config_root is None:
        config_root = DEFAULT_CONFIG_ROOT

    clusters_dir = Path(config_root) / "clusters"
    clusters = []

    if not clusters_dir.exists():
        return clusters

    for yaml_file in sorted(clusters_dir.glob("*.yaml")):
        with open(yaml_file, "r") as f:
            cluster_config = yaml.safe_load(f)
            if cluster_config:
                clusters.append(cluster_config)

    return clusters


def load_application_configs(config_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load all application configuration files from {config_root}/applications/*.yaml.

    Args:
        config_root: Root configuration directory. Defaults to /etc/tcm.

    Returns:
        List of application configuration dictionaries.
    """
    if config_root is None:
        config_root = DEFAULT_CONFIG_ROOT

    apps_dir = Path(config_root) / "applications"
    applications = []

    if not apps_dir.exists():
        return applications

    for yaml_file in sorted(apps_dir.glob("*.yaml")):
        try:
            with open(yaml_file, "r") as f:
                app_config = yaml.safe_load(f)
                if app_config:
                    if "app_id" not in app_config:
                        logger.warning(
                            "Skipping malformed application config (missing app_id): %s",
                            yaml_file,
                        )
                        continue
                    applications.append(app_config)
        except (yaml.YAMLError, OSError) as exc:
            logger.warning("Failed to parse application config %s: %s", yaml_file, exc)

    return applications


def load_node_configs(config_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load all node configuration files from {config_root}/nodes/*.yaml.

    Args:
        config_root: Root configuration directory. Defaults to /etc/tcm.

    Returns:
        List of node configuration dictionaries.
    """
    if config_root is None:
        config_root = DEFAULT_CONFIG_ROOT

    nodes_dir = Path(config_root) / "nodes"
    nodes = []

    if not nodes_dir.exists():
        return nodes

    for yaml_file in sorted(nodes_dir.glob("*.yaml")):
        with open(yaml_file, "r") as f:
            node_config = yaml.safe_load(f)
            if node_config:
                nodes.append(node_config)

    return nodes


def save_yaml(data: Dict[str, Any], file_path: str) -> None:
    """Save data to a YAML file atomically via temp-file + os.replace.

    Writes to a sibling temp file, fsyncs, then replaces the target so a
    crash mid-write never leaves a truncated or corrupt file.

    Args:
        data: Dictionary to serialize.
        file_path: Destination file path.
    """
    import os
    import tempfile

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    content = yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, suffix=".yaml.tmp", delete=False
        ) as f:
            tmp_path = f.name
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise
