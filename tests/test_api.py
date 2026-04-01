"""Tests for API endpoints."""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.api import app
from app.config import Config, LLMConfig, DBConfig


class TestHealthEndpoint(unittest.TestCase):
    """Tests for /health endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_health_returns_ok_when_configured(self, mock_load_config):
        """Health check returns ok with full configuration."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                api_key="",
                base_url="https://api.anthropic.com",
                stream=False,
            ),
            db=DBConfig(connection="postgresql://user:pass@localhost/db"),
        )
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["configured"])
        self.assertTrue(data["api_key_set"])

    @patch("app.api.load_config")
    @patch.dict("os.environ", {}, clear=True)
    def test_health_shows_unconfigured(self, mock_load_config):
        """Health check indicates not configured."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        import os
        os.environ.pop("LYST_LLM_API_KEY", None)
        
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["configured"])
        self.assertFalse(data["api_key_set"])


class TestConfigEndpoints(unittest.TestCase):
    """Tests for /config endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_get_config_returns_current_config(self, mock_load_config):
        """Get config returns current configuration."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                api_key="",
                base_url="https://api.anthropic.com",
                stream=True,
            ),
            db=DBConfig(connection="postgresql://user:pass@localhost/db"),
        )
        response = self.client.get("/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["llm"]["provider"], "anthropic")
        self.assertEqual(data["llm"]["api_key"], "set")
        self.assertTrue(data["llm"]["stream"])
        self.assertIn("connection", data["db"])

class TestSchemaEndpoints(unittest.TestCase):
    """Tests for /schema endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.get_schema")
    @patch("app.api.get_db_type")
    def test_get_schema_success(self, mock_db_type, mock_schema):
        """Get schema returns schema info."""
        mock_schema.return_value = "Table: users\n  - id (INTEGER)"
        mock_db_type.return_value = "postgresql"
        
        response = self.client.get("/schema")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["db_type"], "postgresql")
        self.assertIn("users", data["db_schema"])

    @patch("app.api.get_schema")
    def test_get_schema_error(self, mock_schema):
        """Get schema returns error on failure."""
        mock_schema.side_effect = ValueError("No database configured")
        
        response = self.client.get("/schema")
        self.assertEqual(response.status_code, 400)


class TestAgentEndpoints(unittest.TestCase):
    """Tests for /agent endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_config")
    @patch.dict("os.environ", {}, clear=True)
    def test_agent_requires_config(self, mock_load_config):
        """Agent endpoint fails without configuration."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        import os
        os.environ.pop("LYST_LLM_API_KEY", None)
        
        response = self.client.post("/agent", json={"message": "hello"})
        self.assertEqual(response.status_code, 400)

    @patch("app.api.agent_run")
    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_agent_returns_response(self, mock_load_config, mock_agent):
        """Agent endpoint returns response."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="anthropic", model="claude", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_agent.return_value = MagicMock(
            message="You have 100 users.",
            tool_calls=[],
            sql_results=[],
            history=[{"role": "user", "content": "count users"}],
        )
        
        response = self.client.post("/agent", json={"message": "How many users?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("tool_calls", data)
        self.assertIn("sql_results", data)
        self.assertIn("history", data)


class TestExecuteSqlEndpoint(unittest.TestCase):
    """Tests for /execute-sql endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_config")
    def test_execute_sql_requires_db(self, mock_load_config):
        """Execute SQL fails without database configured."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        
        response = self.client.post("/execute-sql", json={"sql": "SELECT 1"})
        self.assertEqual(response.status_code, 400)

    @patch("app.api.execute_sql")
    @patch("app.api.load_config")
    def test_execute_sql_success(self, mock_load_config, mock_execute):
        """Execute SQL returns results."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_execute.return_value = (["id", "name"], [[1, "Alice"], [2, "Bob"]])
        
        response = self.client.post("/execute-sql", json={"sql": "SELECT * FROM users"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["row_count"], 2)
        self.assertEqual(data["columns"], ["id", "name"])

    @patch("app.api.execute_sql")
    @patch("app.api.load_config")
    def test_execute_sql_error(self, mock_load_config, mock_execute):
        """Execute SQL returns error on failure."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_execute.side_effect = Exception("Table not found")
        
        response = self.client.post("/execute-sql", json={"sql": "SELECT * FROM nonexistent"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"])


class TestSessionEndpoints(unittest.TestCase):
    """Tests for /sessions endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.list_sessions")
    @patch("app.api.get_active_session")
    def test_list_sessions(self, mock_active, mock_list):
        """List sessions returns all sessions."""
        from app.history import Session
        mock_list.return_value = [
            {"id": "1", "name": "Session 1", "messages": [], "created_at": "2024-01-01", "updated_at": "2024-01-01"}
        ]
        mock_active.return_value = Session(
            id="1", name="Session 1", messages=[],
            created_at="2024-01-01", updated_at="2024-01-01"
        )
        
        response = self.client.get("/sessions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["active_session_id"], "1")

    @patch("app.api.create_session")
    @patch("app.api.set_active_session")
    def test_create_session(self, mock_set, mock_create):
        """Create session returns new session."""
        from app.history import Session
        mock_create.return_value = Session(
            id="new", name="New Session", messages=[],
            created_at="2024-01-01", updated_at="2024-01-01"
        )
        
        response = self.client.post("/sessions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "new")


if __name__ == "__main__":
    unittest.main()
