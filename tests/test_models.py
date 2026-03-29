"""Tests for TCM Pydantic data models."""

import sys
import os
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from console.models.application import Application
from console.models.cluster import Cluster, ClusterPolicy, DeploymentConfig
from console.models.node import Node, TomcatInstance
from console.models.deployment import DeploymentStatus, DeployRequest, PolicyUpdateRequest


class TestClusterPolicy:
    def test_default_values(self):
        policy = ClusterPolicy()
        assert policy.mode == "AUTO"
        assert policy.min_instances == 1
        assert policy.max_instances == 10
        assert policy.policy_check_interval == 30

    def test_custom_values(self):
        policy = ClusterPolicy(
            mode="MANUAL", min_instances=5, max_instances=20, policy_check_interval=60
        )
        assert policy.mode == "MANUAL"
        assert policy.min_instances == 5
        assert policy.max_instances == 20
        assert policy.policy_check_interval == 60

    def test_serialization(self):
        policy = ClusterPolicy(mode="AUTO", min_instances=3, max_instances=8)
        data = policy.model_dump()
        assert data["mode"] == "AUTO"
        assert data["min_instances"] == 3
        assert data["max_instances"] == 8

    def test_deserialization(self):
        data = {"mode": "MANUAL", "min_instances": 2, "max_instances": 15}
        policy = ClusterPolicy(**data)
        assert policy.mode == "MANUAL"
        assert policy.min_instances == 2


class TestDeploymentConfig:
    def test_default_values(self):
        config = DeploymentConfig()
        assert config.graceful_stop_timeout == 30
        assert config.startup_timeout == 60
        assert config.health_check_endpoint == "/health"
        assert config.health_check_timeout == 10

    def test_custom_values(self):
        config = DeploymentConfig(
            graceful_stop_timeout=45,
            startup_timeout=90,
            health_check_endpoint="/api/health",
            health_check_timeout=15,
        )
        assert config.graceful_stop_timeout == 45
        assert config.health_check_endpoint == "/api/health"


class TestCluster:
    def test_minimal_cluster(self):
        cluster = Cluster(
            cluster_id="cluster-1",
            app_id="app-a",
        )
        assert cluster.cluster_id == "cluster-1"
        assert cluster.app_id == "app-a"
        assert cluster.nodes == []
        assert cluster.policy.mode == "AUTO"

    def test_full_cluster(self):
        cluster = Cluster(
            cluster_id="cluster-1",
            app_id="app-a",
            nodes=["node-1", "node-2", "node-3"],
            policy=ClusterPolicy(mode="AUTO", min_instances=2, max_instances=5),
            deployment=DeploymentConfig(startup_timeout=120),
        )
        assert len(cluster.nodes) == 3
        assert cluster.policy.min_instances == 2
        assert cluster.deployment.startup_timeout == 120

    def test_serialization_roundtrip(self):
        cluster = Cluster(
            cluster_id="test-cluster",
            app_id="test-app",
            nodes=["node-1"],
        )
        data = cluster.model_dump()
        restored = Cluster(**data)
        assert restored.cluster_id == cluster.cluster_id
        assert restored.app_id == cluster.app_id
        assert restored.nodes == cluster.nodes


class TestApplication:
    def test_construction(self):
        app = Application(
            app_id="app-a",
            name="BrokerageMobileWeb",
            war_filename="BrokerageMobileWeb.war",
            context_path="/BMW",
        )
        assert app.app_id == "app-a"
        assert app.name == "BrokerageMobileWeb"
        assert app.war_filename == "BrokerageMobileWeb.war"
        assert app.context_path == "/BMW"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            Application()  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            Application(app_id="app-a")  # type: ignore[call-arg]

    def test_serialization_roundtrip(self):
        app = Application(
            app_id="app-b",
            name="RetailBanking",
            war_filename="RetailBanking.war",
            context_path="/RB",
        )
        data = app.model_dump()
        restored = Application(**data)
        assert restored.app_id == app.app_id
        assert restored.name == app.name
        assert restored.war_filename == app.war_filename
        assert restored.context_path == app.context_path


class TestTomcatInstance:
    def test_default_values(self):
        tc = TomcatInstance(
            app_id="app-a", instance_port=9001, ajp_port=8009
        )
        assert tc.app_id == "app-a"
        assert tc.instance_port == 9001
        assert tc.ajp_port == 8009
        assert tc.status == "stopped"
        assert tc.pid is None
        assert tc.health_status == "unknown"

    def test_running_instance(self):
        now = datetime.now(timezone.utc)
        tc = TomcatInstance(
            app_id="app-a",
            instance_port=9001,
            ajp_port=8009,
            status="running",
            pid=12345,
            health_status="healthy",
            last_health_check=now,
        )
        assert tc.status == "running"
        assert tc.pid == 12345
        assert tc.health_status == "healthy"

    def test_serialization(self):
        tc = TomcatInstance(
            app_id="app-b",
            instance_port=9002,
            ajp_port=8010,
            status="running",
            pid=5678,
        )
        data = tc.model_dump()
        assert data["app_id"] == "app-b"
        assert data["pid"] == 5678


class TestNode:
    def test_minimal_node(self):
        node = Node(
            node_id="node-1",
            hostname="tomcat-node-1.internal",
            ip_address="192.168.1.10",
        )
        assert node.node_id == "node-1"
        assert node.agent_port == 9001
        assert node.agent_status == "unknown"
        assert node.tomcats == {}

    def test_node_with_tomcats(self):
        tc = TomcatInstance(
            app_id="app-a", instance_port=9001, ajp_port=8009, status="running"
        )
        node = Node(
            node_id="node-1",
            hostname="tomcat-node-1.internal",
            ip_address="192.168.1.10",
            tomcats={"app-a": tc},
        )
        assert "app-a" in node.tomcats
        assert node.tomcats["app-a"].status == "running"

    def test_serialization(self):
        node = Node(
            node_id="node-2",
            hostname="node-2.internal",
            ip_address="10.0.0.2",
            agent_port=9002,
        )
        data = node.model_dump()
        assert data["node_id"] == "node-2"
        assert data["agent_port"] == 9002


class TestDeploymentStatus:
    def test_creation(self):
        now = datetime.now(timezone.utc)
        ds = DeploymentStatus(
            deployment_id="deploy-abc123",
            cluster_id="cluster-1",
            version="v1.2.3",
            nodes_total=10,
            started_at=now,
        )
        assert ds.deployment_id == "deploy-abc123"
        assert ds.status == "in_progress"
        assert ds.nodes_completed == 0
        assert ds.errors == []
        assert ds.completed_at is None

    def test_completed_deployment(self):
        now = datetime.now(timezone.utc)
        ds = DeploymentStatus(
            deployment_id="deploy-xyz789",
            cluster_id="cluster-2",
            version="v2.0.0",
            status="completed",
            nodes_completed=5,
            nodes_total=5,
            started_at=now,
            completed_at=now,
        )
        assert ds.status == "completed"
        assert ds.nodes_completed == ds.nodes_total

    def test_failed_deployment(self):
        now = datetime.now(timezone.utc)
        ds = DeploymentStatus(
            deployment_id="deploy-fail",
            cluster_id="cluster-1",
            version="v1.3.0",
            status="failed",
            nodes_completed=3,
            nodes_total=5,
            errors=["node-4: Agent unreachable", "node-5: Disk full"],
            started_at=now,
        )
        assert ds.status == "failed"
        assert len(ds.errors) == 2

    def test_serialization(self):
        now = datetime.now(timezone.utc)
        ds = DeploymentStatus(
            deployment_id="deploy-ser",
            cluster_id="cluster-1",
            version="v1.0.0",
            started_at=now,
        )
        data = ds.model_dump()
        assert data["deployment_id"] == "deploy-ser"
        assert data["status"] == "in_progress"


class TestDeployRequest:
    def test_creation(self):
        req = DeployRequest(
            war_path="/opt/tcm/staging/cluster-1/app-a/app.war",
            version="v1.2.3",
        )
        assert req.war_path.endswith("app.war")
        assert req.version == "v1.2.3"

    def test_validation_requires_fields(self):
        with pytest.raises(ValidationError):
            DeployRequest()  # type: ignore[call-arg]


class TestPolicyUpdateRequest:
    def test_creation(self):
        req = PolicyUpdateRequest(mode="MANUAL")
        assert req.mode == "MANUAL"
        assert req.min_instances is None
        assert req.max_instances is None

    def test_with_all_fields(self):
        req = PolicyUpdateRequest(
            mode="AUTO", min_instances=3, max_instances=15
        )
        assert req.mode == "AUTO"
        assert req.min_instances == 3
        assert req.max_instances == 15
