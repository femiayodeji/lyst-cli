"""Tests for API endpoints."""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.api import app
from app.config import Config, LLMConfig, DBConfig


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
            {"id": "1", "name": "Session 1", "message_count": 0, "created_at": "2024-01-01", "updated_at": "2024-01-01"}
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
