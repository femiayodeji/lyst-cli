from dataclasses import dataclass
import os


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    stream: bool = False


@dataclass
class DBConfig:
    connection: str


@dataclass
class Config:
    llm: LLMConfig
    db: DBConfig


_db_connection_override: str | None = None


def load_config() -> Config:
    return Config(
        llm=LLMConfig(
            provider=os.environ.get("LYST_LLM_PROVIDER", "gemini"),
            model=os.environ.get("LYST_LLM_MODEL", "gemini/gemini-2.0-flash"),
            api_key=os.environ.get("LYST_LLM_API_KEY", ""),
            base_url=os.environ.get("LYST_LLM_BASE_URL", ""),
            stream=os.environ.get("LYST_STREAM", "true").lower() == "true",
        ),
        db=DBConfig(
            connection=_db_connection_override or os.environ.get("LYST_DB_CONNECTION", ""),
        ),
    )


def set_db_connection(connection: str) -> None:
    global _db_connection_override
    _db_connection_override = connection if connection.strip() else None


def reset_db_connection() -> None:
    global _db_connection_override
    _db_connection_override = None


