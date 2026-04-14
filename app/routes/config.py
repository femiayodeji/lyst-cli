import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config import load_config
from app.db.engine import get_schema, get_db_type
from app.db.schema import cached_schema, cached_db_type
from app.state import AppState, get_state

router = APIRouter()


class DBConfigRequest(BaseModel):
    connection: str


@router.get("/health")
def health(state: AppState = Depends(get_state)):
    config = load_config(state.db_connection_override)
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY", "")
    return {
        "status": "ok",
        "configured": bool(config.llm.model and config.db.connection),
        "api_key_set": bool(api_key),
    }


@router.get("/config")
def get_config(state: AppState = Depends(get_state)):
    config = load_config(state.db_connection_override)
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY", "")
    return {
        "llm": {
            "provider": config.llm.provider,
            "model": config.llm.model,
            "base_url": config.llm.base_url,
            "stream": config.llm.stream,
            "api_key": "set" if api_key else "not_set",
        },
        "db": {"connection": config.db.connection},
    }


@router.put("/config/db")
def update_db_config(request: DBConfigRequest, state: AppState = Depends(get_state)):
    if not request.connection.strip():
        state.reset_db_connection()
        state.clear_schema_cache()
        state.clear_engine_cache()
        return {"message": "Database connection reset to .env default"}

    state.set_db_connection(request.connection)
    state.clear_schema_cache()
    state.clear_engine_cache()
    return {"message": "Database connection updated"}
