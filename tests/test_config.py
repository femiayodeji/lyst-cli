import unittest
import os
from unittest.mock import patch

from app.config import load_config, save_config, reset_config, Config, LLMConfig, DBConfig


class TestConfig(unittest.TestCase):
    """Tests for config module using in-memory storage."""

    def setUp(self):
        """Reset in-memory config before each test."""
        reset_config()

    def tearDown(self):
        """Clean up after each test."""
        reset_config()

    def test_load_config_returns_env_defaults(self):
        """Load config returns environment defaults when no override set."""
        with patch.dict(os.environ, {
            "LYST_LLM_PROVIDER": "test_provider",
            "LYST_LLM_MODEL": "test_model",
            "LYST_LLM_API_KEY": "test_key",
            "LYST_LLM_BASE_URL": "http://test.com",
            "LYST_DB_CONNECTION": "sqlite:///test.db",
            "LYST_STREAM": "true",
        }):
            config = load_config()
            self.assertEqual(config.llm.provider, "test_provider")
            self.assertEqual(config.llm.model, "test_model")
            self.assertEqual(config.db.connection, "sqlite:///test.db")

    def test_config_save_and_load(self):
        """Save config stores in memory and load retrieves it."""
        config = Config(
            llm=LLMConfig(provider="test_provider", model="test_model", api_key="test_api_key", base_url="http://test-url.com", stream=True),
            db=DBConfig(connection="sqlite:///test.db")
        )
        save_config(config)
        loaded_config = load_config()
        self.assertEqual(config, loaded_config)

    @patch.dict("os.environ", {
        "LYST_LLM_PROVIDER": "anthropic",
        "LYST_LLM_MODEL": "anthropic/claude-sonnet-4-20250514",
        "LYST_LLM_BASE_URL": "",
        "LYST_LLM_API_KEY": "",
        "LYST_DB_CONNECTION": "",
        "LYST_STREAM": "true"
    }, clear=True)
    def test_reset_config_clears_override(self):
        """Reset config clears in-memory override."""
        config = Config(
            llm=LLMConfig(provider="custom", model="custom_model", api_key="", base_url="", stream=False),
            db=DBConfig(connection="custom_db")
        )
        save_config(config)
        self.assertEqual(load_config().llm.provider, "custom")
        
        reset_config()
        # After reset, should return env defaults
        loaded = load_config()
        self.assertEqual(loaded.llm.provider, "anthropic")

    def test_config_missing_db(self):
        """Config with empty db connection."""
        config = Config(
            llm=LLMConfig(provider="test_provider", model="test_model", api_key="test_api_key", base_url="http://test-url.com", stream=True),
            db=DBConfig(connection="")
        )
        save_config(config)
        self.assertEqual(load_config().db.connection, "")

    def test_config_missing_llm(self):
        """Config with empty LLM settings."""
        config = Config(
            llm=LLMConfig(provider="", model="", api_key="", base_url="", stream=False),
            db=DBConfig(connection="sqlite:///test.db")
        )
        save_config(config)
        loaded_config = load_config()
        self.assertEqual(loaded_config.llm.provider, "")
        self.assertEqual(loaded_config.llm.model, "")
        self.assertFalse(loaded_config.llm.stream)


if __name__ == "__main__":
    unittest.main()
