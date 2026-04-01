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
        self.assertTrue(data["config_loaded"])
        self.assertTrue(data["api_key_set"])

    @patch("app.api.load_config")
    @patch.dict("os.environ", {}, clear=True)
    def test_health_shows_missing_api_key(self, mock_load_config):
        """Health check indicates missing API key."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        # Clear environment variable
        import os
        os.environ.pop("LYST_LLM_API_KEY", None)
        
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["config_loaded"])
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
        self.assertEqual(data["llm"]["api_key"], "set")  # Masked
        self.assertTrue(data["llm"]["stream"])
        self.assertIn("connection", data["db"])

    @patch("app.api.save_config")
    @patch("app.api.cached_schema")
    @patch("app.api.cached_db_type")
    def test_put_config_saves_configuration(self, mock_db_type, mock_schema, mock_save):
        """Put config saves new configuration."""
        response = self.client.put(
            "/config",
            json={
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                    "stream": False,
                },
                "db": {"connection": "sqlite:///test.db"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())
        mock_save.assert_called_once()

    @patch("app.api.load_config")
    @patch("app.api.save_config")
    def test_put_llm_config_updates_llm_only(self, mock_save, mock_load):
        """Put LLM config updates only LLM settings."""
        mock_load.return_value = Config(
            llm=LLMConfig(provider="old", model="old", api_key="", base_url="", stream=False),
            db=DBConfig(connection="existing-db"),
        )
        response = self.client.put(
            "/config/llm",
            json={
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "api_key": "new-key",
                "base_url": "https://api.anthropic.com",
                "stream": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        mock_save.assert_called_once()

    @patch("app.api.load_config")
    @patch("app.api.save_config")
    @patch("app.api.cached_schema")
    @patch("app.api.cached_db_type")
    def test_put_db_config_updates_db_only(self, mock_db_type, mock_schema, mock_save, mock_load):
        """Put DB config updates only database settings."""
        mock_load.return_value = Config(
            llm=LLMConfig(provider="existing", model="existing", api_key="", base_url="", stream=False),
            db=DBConfig(connection="old-connection"),
        )
        response = self.client.put(
            "/config/db",
            json={"connection": "postgresql://new:pass@localhost/newdb"},
        )
        self.assertEqual(response.status_code, 200)
        mock_save.assert_called_once()


class TestChatEndpoints(unittest.TestCase):
    """Tests for /chat endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_config")
    @patch.dict("os.environ", {}, clear=True)
    def test_chat_requires_api_key(self, mock_load_config):
        """Chat endpoint fails without API key."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="anthropic", model="claude", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        # Clear any env variable
        import os
        os.environ.pop("LYST_LLM_API_KEY", None)
        
        response = self.client.post("/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("LYST_LLM_API_KEY", response.json()["detail"])

    @patch("app.api.load_config")
    def test_chat_requires_llm_configured(self, mock_load_config):
        """Chat endpoint fails without LLM configuration."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        response = self.client.post("/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("LLM", response.json()["detail"])

    @patch("app.api.chat")
    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_chat_returns_response(self, mock_load_config, mock_chat):
        """Chat endpoint returns LLM response."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="anthropic", model="claude", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_chat.return_value = MagicMock(
            response="You have 5 tables in your database.",
            history=[{"role": "user", "content": "How many tables?"}],
        )
        response = self.client.post("/chat", json={"message": "How many tables?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("response", data)
        self.assertIn("history", data)


class TestQueryEndpoints(unittest.TestCase):
    """Tests for /query endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_config")
    def test_query_requires_llm_configured(self, mock_load_config):
        """Query endpoint fails without LLM configuration."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection="sqlite:///test.db"),
        )
        response = self.client.post("/query", json={"question": "Show all users"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("LLM", response.json()["detail"])

    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_query_requires_db_configured(self, mock_load_config):
        """Query endpoint fails without DB configuration."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="anthropic", model="claude", api_key="", base_url="", stream=False),
            db=DBConfig(connection=""),
        )
        response = self.client.post("/query", json={"question": "Show all users"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("database", response.json()["detail"])

    @patch("app.api.query")
    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_query_returns_results(self, mock_load_config, mock_query):
        """Query endpoint returns SQL and results."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="anthropic", model="claude", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_query.return_value = MagicMock(
            sql="SELECT * FROM users",
            columns=["id", "name", "email"],
            rows=[[1, "Alice", "alice@example.com"]],
            summary="Found 1 user.",
            history=[],
            success=True,
        )
        response = self.client.post("/query", json={"question": "Show all users"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sql"], "SELECT * FROM users")
        self.assertEqual(len(data["columns"]), 3)
        self.assertTrue(data["success"])


class TestSchemaEndpoint(unittest.TestCase):
    """Tests for /schema endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.get_db_type")
    @patch("app.api.get_schema")
    def test_schema_returns_schema_and_type(self, mock_get_schema, mock_get_db_type):
        """Schema endpoint returns database schema and type."""
        mock_get_schema.return_value = "Table: users\n  id: INTEGER\n  name: VARCHAR"
        mock_get_db_type.return_value = "postgresql"
        
        response = self.client.get("/schema")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("users", data["db_schema"])
        self.assertEqual(data["db_type"], "postgresql")

    @patch("app.api.get_schema")
    def test_schema_handles_no_connection(self, mock_get_schema):
        """Schema endpoint returns error when no DB configured."""
        mock_get_schema.side_effect = ValueError("No database connection configured")
        
        response = self.client.get("/schema")
        self.assertEqual(response.status_code, 400)


class TestGenerateSqlEndpoint(unittest.TestCase):
    """Tests for /generate-sql endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.generate_sql")
    @patch("app.api.load_config")
    @patch.dict("os.environ", {"LYST_LLM_API_KEY": "test-key"})
    def test_generate_sql_returns_sql(self, mock_load_config, mock_generate):
        """Generate SQL endpoint returns SQL without executing."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="anthropic", model="claude", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_generate.return_value = MagicMock(
            sql="SELECT COUNT(*) FROM orders",
            history=[],
        )
        response = self.client.post(
            "/generate-sql",
            json={"question": "How many orders are there?"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sql"], "SELECT COUNT(*) FROM orders")


class TestExecuteSqlEndpoint(unittest.TestCase):
    """Tests for /execute-sql endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.execute_sql")
    @patch("app.api.load_config")
    def test_execute_sql_runs_query(self, mock_load_config, mock_execute):
        """Execute SQL endpoint runs the query and returns results."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_execute.return_value = (["count"], [[42]])
        
        response = self.client.post(
            "/execute-sql",
            json={"sql": "SELECT COUNT(*) as count FROM orders"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["row_count"], 1)
        self.assertEqual(data["rows"][0][0], 42)

    @patch("app.api.execute_sql")
    @patch("app.api.load_config")
    def test_execute_sql_handles_error(self, mock_load_config, mock_execute):
        """Execute SQL endpoint handles query errors gracefully."""
        mock_load_config.return_value = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection="postgresql://test"),
        )
        mock_execute.side_effect = Exception("Table not found")
        
        response = self.client.post(
            "/execute-sql",
            json={"sql": "SELECT * FROM nonexistent"},
        )
        self.assertEqual(response.status_code, 200)  # Returns 200 with error in body
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Table not found", data["error"])


class TestHistoryEndpoints(unittest.TestCase):
    """Tests for /history endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.load_history")
    @patch("app.api.history_summary")
    def test_get_history_returns_messages(self, mock_summary, mock_load):
        """Get history returns persisted messages."""
        mock_load.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        mock_summary.return_value = "1 exchange(s) in current session."
        
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["messages"]), 2)
        self.assertIn("exchange", data["summary"])

    @patch("app.api.save_history")
    def test_put_history_saves_messages(self, mock_save):
        """Put history saves messages to disk."""
        messages = [
            {"role": "user", "content": "Test question"},
            {"role": "assistant", "content": "Test answer"},
        ]
        response = self.client.put(
            "/history",
            json={"messages": messages},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        mock_save.assert_called_once_with(messages)

    @patch("app.api.clear_history")
    def test_delete_history_clears_messages(self, mock_clear):
        """Delete history clears all messages."""
        response = self.client.delete("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cleared", response.json()["message"])
        mock_clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
