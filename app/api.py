from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any
from pathlib import Path

from app.config import load_config, set_db_connection, reset_db_connection
from app.prompts import cached_schema, cached_db_type, clear_schema_cache
from app.db import get_schema, get_db_type, clear_engine_cache
from app.agent import run_stream as agent_run_stream
from app.history import (
    save_history, clear_history,
    list_sessions, get_session, create_session, delete_session,
    set_active_session, get_active_session
)


class AgentRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


class DBConfigRequest(BaseModel):
    connection: str

class SaveHistoryRequest(BaseModel):
    messages: list[dict[str, Any]]


app = FastAPI(
    title="lyst",
    description="Query your database using natural language",
    version="0.2.0",
)


@app.get("/health")
def health():
    config = load_config()
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY", "")
    return {
        "status": "ok",
        "configured": bool(config.llm.model and config.db.connection),
        "api_key_set": bool(api_key),
    }


@app.get("/config")
def get_config():
    config = load_config()
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


@app.put("/config/db")
def update_db_config(request: DBConfigRequest):
    if not request.connection.strip():
        reset_db_connection()
        clear_schema_cache()
        clear_engine_cache()
        return {"message": "Database connection reset to .env default"}

    set_db_connection(request.connection)
    clear_schema_cache()
    clear_engine_cache()
    return {"message": "Database connection updated"}


@app.get("/schema")
def get_database_schema():
    try:
        return {"db_schema": get_schema(), "db_type": get_db_type()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {e}")


@app.post("/schema/load")
def load_schema(force: bool = Query(False, description="Clear cache and reload from the database")):
    try:
        if force:
            clear_schema_cache()
        schema = cached_schema()
        db_type = cached_db_type()
        return {
            "message": "Schema loaded",
            "db_type": db_type,
            "tables_count": schema.count("Table:"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schema: {e}")

@app.post("/agent/stream")
def agent_stream_endpoint(request: AgentRequest):
    _validate_config()
    
    return StreamingResponse(
        agent_run_stream(request.message, request.history.copy()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

@app.get("/sessions")
def list_sessions_endpoint():
    sessions = list_sessions()
    active = get_active_session()

    return {
        "sessions": [
            {
                "id": s["id"],
                "name": s["name"],
                "message_count": s["message_count"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
            }
            for s in sessions
        ],
        "active_session_id": active.id if active else None,
    }


@app.post("/sessions")
def create_session_endpoint():
    session = create_session()
    set_active_session(session.id)
    return {
        "id": session.id,
        "name": session.name,
        "message_count": 0,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@app.get("/sessions/{session_id}")
def get_session_endpoint(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "name": session.name,
        "messages": session.messages,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@app.delete("/sessions/{session_id}")
def delete_session_endpoint(session_id: str):
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@app.put("/sessions/{session_id}/activate")
def activate_session_endpoint(session_id: str):
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    set_active_session(session_id)
    return {"message": "Session activated"}

@app.put("/history")
def save_history_endpoint(request: SaveHistoryRequest):
    save_history(request.messages)
    return {"message": "History saved"}


@app.delete("/history")
def clear_history_endpoint():
    clear_history()
    return {"message": "History cleared"}



@app.get("/")
def serve_index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")



def _validate_config():
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured")
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="No API key configured")
