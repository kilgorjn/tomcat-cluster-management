"""Tests for TCM Agent REST API endpoints."""

import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_tomcat_root():
    """Create a temporary tomcat root with a sample instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create app-a instance directory structure
        app_dir = os.path.join(tmpdir, "app-a")
        os.makedirs(os.path.join(app_dir, "webapps"))
        os.makedirs(os.path.join(app_dir, "conf"))
        os.makedirs(os.path.join(app_dir, "logs"))
        os.makedirs(os.path.join(app_dir, "work"))
        yield tmpdir


@pytest.fixture
def mock_pid_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def client(mock_tomcat_root, mock_pid_dir):
    """Create a test client with mocked config."""
    mock_config = {
        "role": "agent",
        "agent": {
            "node_id": "test-node",
            "tomcat_root": mock_tomcat_root,
            "log_dir": "/tmp/tcm-test-logs",
        },
        "tomcat": {
            "graceful_stop_timeout": 5,
            "startup_timeout": 10,
            "health_check_timeout": 3,
        },
        "process_management": {
            "pid_dir": mock_pid_dir,
        },
        "logging": {"level": "DEBUG", "format": "text"},
    }

    with patch("agent.app.load_config", return_value=mock_config), \
         patch("agent.app.setup_logging"):
        from agent.app import app
        with TestClient(app) as tc:
            yield tc


class TestAgentStatusEndpoints:
    def test_node_status(self, client):
        response = client.get("/nodes/test-node/status")
        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "test-node"
        assert "tomcats" in data
        # app-a should be discovered from the temp directory
        assert "app-a" in data["tomcats"]

    def test_tomcat_status(self, client):
        response = client.get("/nodes/test-node/tomcats/app-a/status")
        assert response.status_code == 200
        data = response.json()
        assert data["app_id"] == "app-a"
        assert data["status"] == "stopped"  # No PID file exists
        assert data["pid"] is None

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["node_id"] == "test-node"


class TestAgentControlEndpoints:
    @patch("agent.process_manager.ProcessManager.start_tomcat", return_value=True)
    @patch("agent.process_manager.ProcessManager.get_tomcat_pid", return_value=12345)
    @patch("agent.process_manager.ProcessManager.get_tomcat_status", return_value="running")
    def test_start_tomcat(self, mock_status, mock_pid, mock_start, client):
        response = client.post("/nodes/test-node/tomcats/app-a/start")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["app_id"] == "app-a"

    @patch("agent.process_manager.ProcessManager.stop_tomcat", return_value=True)
    @patch("agent.process_manager.ProcessManager.get_tomcat_pid", return_value=None)
    @patch("agent.process_manager.ProcessManager.get_tomcat_status", return_value="stopped")
    def test_stop_tomcat(self, mock_status, mock_pid, mock_stop, client):
        response = client.post("/nodes/test-node/tomcats/app-a/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

    @patch("agent.process_manager.ProcessManager.start_tomcat", return_value=False)
    @patch("agent.process_manager.ProcessManager.get_tomcat_pid", return_value=None)
    @patch("agent.process_manager.ProcessManager.get_tomcat_status", return_value="stopped")
    def test_start_tomcat_failure(self, mock_status, mock_pid, mock_start, client):
        response = client.post("/nodes/test-node/tomcats/app-a/start")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


class TestServerXmlParsing:
    """Tests for server.xml port discovery logic."""

    def _write_server_xml(self, tomcat_root: str, app_id: str, content: str) -> None:
        conf_dir = os.path.join(tomcat_root, app_id, "conf")
        os.makedirs(conf_dir, exist_ok=True)
        with open(os.path.join(conf_dir, "server.xml"), "w") as f:
            f.write(content)

    def _make_controller(self, tomcat_root: str) -> "TomcatController":
        from agent.tomcat_controller import TomcatController
        return TomcatController(
            tomcat_root=tomcat_root,
            pid_dir=tempfile.mkdtemp(),
        )

    def test_standard_http_connector(self):
        """Standard server.xml with a single HTTP connector."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_server_xml(tmpdir, "app-a", '<?xml version="1.0" encoding="UTF-8"?>\n<Server port="8005" shutdown="SHUTDOWN">\n  <Service name="Catalina">\n    <Connector port="8080" protocol="HTTP/1.1" connectionTimeout="20000" />\n    <Connector port="8009" protocol="AJP/1.3" />\n  </Service>\n</Server>')
            ctrl = self._make_controller(tmpdir)
            port = ctrl._discover_port_from_server_xml("app-a")
            assert port == 8080

    def test_multiple_http_connectors_returns_first(self):
        """Multiple HTTP connectors — should return the first one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_server_xml(tmpdir, "app-a", '<?xml version="1.0" encoding="UTF-8"?>\n<Server port="8005" shutdown="SHUTDOWN">\n  <Service name="Catalina">\n    <Connector port="8080" protocol="HTTP/1.1" />\n    <Connector port="8443" protocol="HTTP/1.1" scheme="https" />\n  </Service>\n</Server>')
            ctrl = self._make_controller(tmpdir)
            port = ctrl._discover_port_from_server_xml("app-a")
            assert port == 8080

    def test_https_connector_skipped(self):
        """HTTPS-only connector with non-HTTP protocol is skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_server_xml(tmpdir, "app-a", '<?xml version="1.0" encoding="UTF-8"?>\n<Server port="8005" shutdown="SHUTDOWN">\n  <Service name="Catalina">\n    <Connector port="8009" protocol="AJP/1.3" />\n  </Service>\n</Server>')
            ctrl = self._make_controller(tmpdir)
            port = ctrl._discover_port_from_server_xml("app-a")
            assert port is None

    def test_missing_protocol_defaults_to_http(self):
        """Connector without protocol attribute defaults to HTTP."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_server_xml(tmpdir, "app-a", '<?xml version="1.0" encoding="UTF-8"?>\n<Server port="8005" shutdown="SHUTDOWN">\n  <Service name="Catalina">\n    <Connector port="9090" />\n  </Service>\n</Server>')
            ctrl = self._make_controller(tmpdir)
            port = ctrl._discover_port_from_server_xml("app-a")
            assert port == 9090

    def test_missing_server_xml(self):
        """No server.xml file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._make_controller(tmpdir)
            port = ctrl._discover_port_from_server_xml("nonexistent")
            assert port is None

    def test_malformed_xml(self):
        """Malformed XML returns None without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_server_xml(tmpdir, "app-a", "<not valid xml")
            ctrl = self._make_controller(tmpdir)
            port = ctrl._discover_port_from_server_xml("app-a")
            assert port is None

    def test_discover_instances_populates_ports(self):
        """discover_instances() populates port map from server.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create instance dirs with server.xml
            self._write_server_xml(tmpdir, "app-a", '<?xml version="1.0" encoding="UTF-8"?>\n<Server port="8005" shutdown="SHUTDOWN">\n  <Service name="Catalina">\n    <Connector port="8080" protocol="HTTP/1.1" />\n  </Service>\n</Server>')
            # Also create webapps so it counts as a valid instance
            os.makedirs(os.path.join(tmpdir, "app-a", "webapps"), exist_ok=True)
            ctrl = self._make_controller(tmpdir)
            instances = ctrl.discover_instances()
            assert "app-a" in instances
            assert ctrl.get_instance_port("app-a") == 8080


class TestAgentDeployEndpoint:
    @patch("agent.process_manager.ProcessManager.stop_tomcat", return_value=True)
    @patch("agent.process_manager.ProcessManager.start_tomcat", return_value=True)
    @patch("agent.process_manager.ProcessManager.get_tomcat_pid", return_value=99999)
    @patch("agent.process_manager.ProcessManager.get_tomcat_status", return_value="stopped")
    def test_deploy_war(self, mock_status, mock_pid, mock_start, mock_stop, client):
        war_content = b"PK\x03\x04" + b"\x00" * 100  # Minimal ZIP/WAR header
        response = client.post(
            "/nodes/test-node/tomcats/app-a/deploy",
            content=war_content,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Deploy-Version": "v2.0.0",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["app_id"] == "app-a"
        assert data["version"] == "v2.0.0"

    def test_deploy_empty_war(self, client):
        response = client.post(
            "/nodes/test-node/tomcats/app-a/deploy",
            content=b"",
            headers={
                "Content-Type": "application/octet-stream",
                "X-Deploy-Version": "v2.0.0",
            },
        )
        assert response.status_code == 400
