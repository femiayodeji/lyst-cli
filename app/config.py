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


def load_config(db_connection_override: str | None = None) -> Config:
    return Config(
        llm=LLMConfig(
            provider=os.environ.get("LYST_LLM_PROVIDER", "gemini"),
            model=os.environ.get("LYST_LLM_MODEL", "gemini/gemini-2.0-flash"),
            api_key=os.environ.get("LYST_LLM_API_KEY", ""),
            base_url=os.environ.get("LYST_LLM_BASE_URL", ""),
            stream=os.environ.get("LYST_STREAM", "true").lower() == "true",
        ),
        db=DBConfig(
            connection=db_connection_override or os.environ.get("LYST_DB_CONNECTION", ""),
        ),
    )


