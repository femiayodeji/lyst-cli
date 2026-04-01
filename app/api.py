from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any
from pathlib import Path

from app.config import load_config, set_db_connection, reset_db_connection
from app.prompts import cached_schema, cached_db_type, clear_schema_cache
from app.db import get_schema, get_db_type, run_query as execute_sql
from app.agent import run as agent_run, run_stream as agent_run_stream
from app.history import (
    load_history, save_history, clear_history, history_summary,
    list_sessions, get_session, create_session, delete_session,
    set_active_session, get_active_session
)


class AgentRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


class DBConfigRequest(BaseModel):
    connection: str


class AgentResponse(BaseModel):
    message: str
    tool_calls: list[dict]
    sql_results: list[dict]
    history: list[dict]


class ExecuteSqlRequest(BaseModel):
    sql: str


class ExecuteSqlResponse(BaseModel):
    columns: list[Any]
    rows: list[Any]
    row_count: int
    success: bool
    error: str | None = None


class SaveHistoryRequest(BaseModel):
    messages: list[dict[str, Any]]


app = FastAPI(
    title="lyst",
    description="Query your database using natural language",
    version="0.2.0",
)


@app.get("/health")
def health():
    """Health check."""
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
    """Update database connection (session-only override)."""
    if not request.connection.strip():
        reset_db_connection()
        clear_schema_cache()
        return {"message": "Database connection reset to .env default"}

    set_db_connection(request.connection)
    clear_schema_cache()
    return {"message": "Database connection updated"}


@app.get("/schema")
def get_database_schema():
    """Get database schema."""
    try:
        return {"db_schema": get_schema(), "db_type": get_db_type()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {e}")


@app.post("/schema/load")
def load_schema():
    try:
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


# ═══════════════════════════════════════════════════════════════════════════
# Agent Endpoints (Main Interface)
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/agent", response_model=AgentResponse)
def agent_endpoint(request: AgentRequest):
    """
    Send a message to the agent.
    
    The agent automatically decides when to query the database vs just chat.
    Maintains conversation context through history.
    """
    _validate_config()
    
    try:
        result = agent_run(
            message=request.message,
            history=request.history.copy(),
        )
        return AgentResponse(
            message=result.message,
            tool_calls=result.tool_calls,
            sql_results=result.sql_results,
            history=result.history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/stream")
def agent_stream_endpoint(request: AgentRequest):
    """
    Streaming agent endpoint.
    
    Returns Server-Sent Events with real-time updates:
    - status: Progress messages
    - tool_call: Tool being invoked
    - sql: SQL query being executed
    - result: Query results
    - message_complete: Final response
    - done: Stream finished
    """
    _validate_config()
    
    return StreamingResponse(
        agent_run_stream(request.message, request.history.copy()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# SQL Execution (Direct)
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/execute-sql", response_model=ExecuteSqlResponse)
def execute_sql_endpoint(request: ExecuteSqlRequest):
    """Execute raw SQL directly."""
    config = load_config()
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured")
    
    try:
        columns, rows = execute_sql(request.sql)
        return ExecuteSqlResponse(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            success=True,
        )
    except Exception as e:
        return ExecuteSqlResponse(
            columns=[],
            rows=[],
            row_count=0,
            success=False,
            error=str(e),
        )


# ═══════════════════════════════════════════════════════════════════════════
# Session & History Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/sessions")
def list_sessions_endpoint():
    """List all sessions."""
    sessions = list_sessions()
    active = get_active_session()
    return {
        "sessions": [
            {
                "id": s["id"],
                "name": s["name"],
                "message_count": len(s["messages"]),
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
            }
            for s in sessions
        ],
        "active_session_id": active.id if active else None,
    }


@app.post("/sessions")
def create_session_endpoint():
    """Create a new session."""
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
    """Get session details."""
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
    """Delete a session."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@app.put("/sessions/{session_id}/activate")
def activate_session_endpoint(session_id: str):
    """Set active session."""
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    set_active_session(session_id)
    return {"message": "Session activated"}


@app.get("/history")
def get_history_endpoint():
    """Get current history."""
    return {"messages": load_history(), "summary": history_summary()}


@app.put("/history")
def save_history_endpoint(request: SaveHistoryRequest):
    """Save history."""
    save_history(request.messages)
    return {"message": "History saved"}


@app.delete("/history")
def clear_history_endpoint():
    """Clear history."""
    clear_history()
    return {"message": "History cleared"}


# ═══════════════════════════════════════════════════════════════════════════
# Static Files
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
def serve_index():
    """Serve the main UI."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _validate_config():
    """Validate that LLM and DB are configured."""
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured")
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="No API key configured")
