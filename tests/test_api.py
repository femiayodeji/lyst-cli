"""Tests for API endpoints."""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.state import AppState, Session
from app.config import Config, LLMConfig, DBConfig


def _override_state() -> AppState:
    """Return (or create) a test AppState attached to the app."""
    if not hasattr(app.state, "app_state"):
        app.state.app_state = AppState()
    return app.state.app_state


class TestConfigEndpoints(unittest.TestCase):
    """Tests for /config endpoints."""

    def setUp(self):
        app.state.app_state = AppState()
        self.client = TestClient(app)

    @patch("app.routes.config.load_config")
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
        app.state.app_state = AppState()
        self.client = TestClient(app)

    @patch("app.routes.schema.get_schema")
    @patch("app.routes.schema.get_db_type")
    def test_get_schema_success(self, mock_db_type, mock_schema):
        """Get schema returns schema info."""
        mock_schema.return_value = "Table: users\n  - id (INTEGER)"
        mock_db_type.return_value = "postgresql"
        
        response = self.client.get("/schema")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["db_type"], "postgresql")
        self.assertIn("users", data["db_schema"])

    @patch("app.routes.schema.get_schema")
    def test_get_schema_error(self, mock_schema):
        """Get schema returns error on failure."""
        mock_schema.side_effect = ValueError("No database configured")
        
        response = self.client.get("/schema")
        self.assertEqual(response.status_code, 400)


class TestSessionEndpoints(unittest.TestCase):
    """Tests for /sessions endpoints."""

    def setUp(self):
        app.state.app_state = AppState()
        self.client = TestClient(app)

    def test_list_sessions(self):
        """List sessions returns all sessions."""
        state = app.state.app_state
        state.sessions["1"] = Session(
            id="1", name="Session 1", messages=[],
            created_at="2024-01-01", updated_at="2024-01-01",
        )
        state.active_session_id = "1"

        response = self.client.get("/sessions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["active_session_id"], "1")

    def test_create_session(self):
        """Create session returns new session."""
        response = self.client.post("/sessions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("name", data)


class TestSQLGuard(unittest.TestCase):
    """Tests for SQL safety validation."""

    def test_select_allowed(self):
        from app.agent.tools import validate_sql
        self.assertIsNone(validate_sql("SELECT * FROM users"))

    def test_drop_rejected(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("DROP TABLE users"))

    def test_delete_rejected(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("DELETE FROM users WHERE id = 1"))

    def test_insert_rejected(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("INSERT INTO users (name) VALUES ('test')"))

    def test_update_rejected(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("UPDATE users SET name = 'x' WHERE id = 1"))

    def test_truncate_rejected(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("TRUNCATE TABLE users"))

    def test_alter_rejected(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("ALTER TABLE users ADD COLUMN age INT"))

    def test_case_insensitive(self):
        from app.agent.tools import validate_sql
        self.assertIsNotNone(validate_sql("drop table users"))
        self.assertIsNotNone(validate_sql("Delete From users"))


if __name__ == "__main__":
    unittest.main()
