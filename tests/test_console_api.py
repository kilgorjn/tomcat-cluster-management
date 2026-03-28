"""Tests for TCM Console REST API endpoints."""

import sys
import os
import tempfile
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from console.models.cluster import Cluster, ClusterPolicy, DeploymentConfig
from console.services.node_manager import NodeManager
from console.services.policy_service import PolicyService
from console.services.deployment_service import DeploymentService
from console.api import clusters, deployments, nodes, monitoring


def _build_test_app() -> FastAPI:
    """Build a standalone FastAPI app with test data injected via lifespan."""

    sample_clusters = {
        "cluster-1": Cluster(
            cluster_id="cluster-1",
            app_id="app-a",
            app_path="/opt/tomcats/app-a",
            nodes=["node-1", "node-2"],
            policy=ClusterPolicy(mode="AUTO", min_instances=2, max_instances=5),
            deployment=DeploymentConfig(),
            current_version="v1.0.0",
        ),
        "cluster-2": Cluster(
            cluster_id="cluster-2",
            app_id="app-b",
            app_path="/opt/tomcats/app-b",
            nodes=["node-1"],
            policy=ClusterPolicy(mode="MANUAL", min_instances=1, max_instances=3),
            deployment=DeploymentConfig(),
            current_version="v2.0.0",
        ),
    }

    node_manager = NodeManager(node_timeout=5)
    node_manager.load_nodes([
        {
            "node_id": "node-1",
            "hostname": "node-1.internal",
            "ip_address": "192.168.1.10",
            "agent_port": 9001,
            "tomcats": [
                {
                    "app_id": "app-a",
                    "instance_port": 9001,
                    "ajp_port": 8009,
                    "status": "running",
                    "version": "v1.0.0",
                },
                {
                    "app_id": "app-b",
                    "instance_port": 9002,
                    "ajp_port": 8010,
                    "status": "stopped",
                    "version": "v2.0.0",
                },
            ],
        },
        {
            "node_id": "node-2",
            "hostname": "node-2.internal",
            "ip_address": "192.168.1.11",
            "agent_port": 9001,
            "tomcats": [
                {
                    "app_id": "app-a",
                    "instance_port": 9001,
                    "ajp_port": 8009,
                    "status": "running",
                    "version": "v1.0.0",
                },
            ],
        },
    ])

    policy_service = PolicyService()
    policy_service.load_clusters(sample_clusters)

    deployment_service = DeploymentService(node_manager=node_manager)

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Inject test services into routers."""
        tmpdir = tempfile.mkdtemp(prefix="tcm-test-")
        config_root = tmpdir
        os.makedirs(os.path.join(config_root, "clusters"), exist_ok=True)

        clusters.router.clusters = sample_clusters  # type: ignore[attr-defined]
        clusters.router.node_manager = node_manager  # type: ignore[attr-defined]
        clusters.router.policy_service = policy_service  # type: ignore[attr-defined]
        clusters.router.config_root = config_root  # type: ignore[attr-defined]

        deployments.router.clusters = sample_clusters  # type: ignore[attr-defined]
        deployments.router.deployment_service = deployment_service  # type: ignore[attr-defined]

        nodes.router.node_manager = node_manager  # type: ignore[attr-defined]

        monitoring.router.clusters = sample_clusters  # type: ignore[attr-defined]
        monitoring.router.node_manager = node_manager  # type: ignore[attr-defined]
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.include_router(clusters.router)
    app.include_router(deployments.router)
    app.include_router(nodes.router)
    app.include_router(monitoring.router)
    return app


@pytest.fixture
def client():
    """Create a test client with injected test data."""
    app = _build_test_app()
    with TestClient(app) as tc:
        yield tc


class TestClusterEndpoints:
    def test_list_clusters(self, client):
        response = client.get("/clusters")
        assert response.status_code == 200
        data = response.json()
        assert "clusters" in data
        assert len(data["clusters"]) == 2
        cluster_ids = {c["cluster_id"] for c in data["clusters"]}
        assert "cluster-1" in cluster_ids
        assert "cluster-2" in cluster_ids

    def test_get_cluster(self, client):
        response = client.get("/clusters/cluster-1")
        assert response.status_code == 200
        data = response.json()
        assert data["cluster_id"] == "cluster-1"
        assert data["app_id"] == "app-a"
        assert data["current_version"] == "v1.0.0"
        assert len(data["nodes"]) == 2

    def test_get_cluster_not_found(self, client):
        response = client.get("/clusters/nonexistent")
        assert response.status_code == 404

    def test_update_policy(self, client):
        response = client.post(
            "/clusters/cluster-1/policy",
            json={"mode": "MANUAL"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["policy"]["mode"] == "MANUAL"

    def test_update_policy_with_min_max(self, client):
        response = client.post(
            "/clusters/cluster-1/policy",
            json={"mode": "AUTO", "min_instances": 3, "max_instances": 8},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["policy"]["min_instances"] == 3
        assert data["policy"]["max_instances"] == 8

    def test_update_policy_invalid_mode(self, client):
        response = client.post(
            "/clusters/cluster-1/policy",
            json={"mode": "INVALID"},
        )
        assert response.status_code == 400

    def test_update_policy_cluster_not_found(self, client):
        response = client.post(
            "/clusters/nonexistent/policy",
            json={"mode": "AUTO"},
        )
        assert response.status_code == 404

    def test_cluster_status(self, client):
        response = client.get("/clusters/cluster-1/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "stopped" in data
        assert "unhealthy" in data
        assert "policy_mode" in data

    def test_cluster_status_not_found(self, client):
        response = client.get("/clusters/nonexistent/status")
        assert response.status_code == 404


class TestNodeEndpoints:
    def test_list_nodes(self, client):
        response = client.get("/nodes")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert len(data["nodes"]) == 2

    def test_get_node_status(self, client):
        """Node status returns cached state when agent is unreachable."""
        response = client.get("/nodes/node-1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "node-1"

    def test_get_node_not_found(self, client):
        response = client.get("/nodes/nonexistent/status")
        assert response.status_code == 404


class TestMonitoringEndpoints:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_system_status(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_clusters" in data
        assert "total_nodes" in data
        assert "total_tomcats" in data
        assert "running_tomcats" in data
        assert data["total_clusters"] == 2
        assert data["total_nodes"] == 2


class TestDeploymentEndpoints:
    def test_deploy_cluster_not_found(self, client):
        response = client.post(
            "/clusters/nonexistent/deploy",
            json={"war_path": "/tmp/app.war", "version": "v1.0.0"},
        )
        assert response.status_code == 404

    def test_deploy_war_not_found(self, client):
        response = client.post(
            "/clusters/cluster-1/deploy",
            json={"war_path": "/nonexistent/app.war", "version": "v1.0.0"},
        )
        assert response.status_code == 400

    def test_get_deployment_not_found(self, client):
        response = client.get("/clusters/cluster-1/deployments/deploy-nonexistent")
        assert response.status_code == 404

    def test_rollback_no_previous(self, client):
        response = client.post("/clusters/cluster-1/rollback")
        assert response.status_code == 409

    def test_rollback_cluster_not_found(self, client):
        response = client.post("/clusters/nonexistent/rollback")
        assert response.status_code == 404
