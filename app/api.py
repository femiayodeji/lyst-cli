"""FastAPI web interface for lyst."""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any
from pathlib import Path
import os
import json

from app.config import load_config, save_config, reset_config, Config, LLMConfig, DBConfig
from app.llm import query, query_stream, generate_sql, QueryResult, cached_schema, cached_db_type, chat, chat_stream
from app.db import get_schema, get_db_type, run_query as execute_sql
from app.history import (
    load_history, save_history, clear_history, history_summary,
    list_sessions, get_session, create_session, delete_session,
    set_active_session, get_active_session, clear_all_sessions
)


# --- Pydantic Models ---

class LLMConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: str = ""
    base_url: str
    stream: bool = False


class DBConfigRequest(BaseModel):
    connection: str


class ConfigRequest(BaseModel):
    llm: LLMConfigRequest
    db: DBConfigRequest


class ConfigResponse(BaseModel):
    llm: dict
    db: dict


class QueryRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = []


class QueryResponse(BaseModel):
    sql: str
    columns: list[Any]
    rows: list[Any]
    summary: str
    history: list[dict]
    success: bool


class GenerateSqlRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = []


class GenerateSqlResponse(BaseModel):
    sql: str
    history: list[dict]


class ExecuteSqlRequest(BaseModel):
    sql: str


class ExecuteSqlResponse(BaseModel):
    columns: list[Any]
    rows: list[Any]
    row_count: int
    success: bool
    error: str | None = None


class SchemaResponse(BaseModel):
    db_schema: str
    db_type: str


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


class ChatResponse(BaseModel):
    response: str
    history: list[dict]


class HealthResponse(BaseModel):
    status: str
    config_loaded: bool
    api_key_set: bool


class HistoryResponse(BaseModel):
    messages: list[dict]
    summary: str


class SaveHistoryRequest(BaseModel):
    messages: list[dict[str, Any]]


class SessionInfo(BaseModel):
    id: str
    name: str
    message_count: int
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
    active_session_id: str | None


class SessionDetailResponse(BaseModel):
    id: str
    name: str
    messages: list[dict]
    created_at: str
    updated_at: str


class CreateSessionRequest(BaseModel):
    name: str | None = None


# --- FastAPI App ---

app = FastAPI(
    title="lyst API",
    description="Query your database using plain English. Ask a question, get SQL + results + a summary.",
    version="0.1.0",
)


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Check API health and configuration status."""
    config = load_config()
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY", "")
    return HealthResponse(
        status="ok",
        config_loaded=bool(config.llm.model and config.db.connection),
        api_key_set=bool(api_key),
    )


@app.get("/config", response_model=ConfigResponse)
def get_config():
    """Get current configuration."""
    config = load_config()
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY", "")
    api_key_status = "set" if api_key else "not_set"
    return ConfigResponse(
        llm={
            "provider": config.llm.provider,
            "model": config.llm.model,
            "base_url": config.llm.base_url,
            "stream": config.llm.stream,
            "api_key": api_key_status,
        },
        db={
            "connection": config.db.connection,
        },
    )


@app.put("/config")
def update_config(request: ConfigRequest):
    """Update full configuration (LLM + DB)."""
    config = Config(
        llm=LLMConfig(
            provider=request.llm.provider,
            model=request.llm.model,
            api_key=request.llm.api_key,
            base_url=request.llm.base_url,
            stream=request.llm.stream,
        ),
        db=DBConfig(connection=request.db.connection),
    )
    save_config(config)
    # Clear cached schema/db_type when config changes
    cached_schema.cache_clear()
    cached_db_type.cache_clear()
    return {"message": "Configuration saved"}


@app.put("/config/llm")
def update_llm_config(request: LLMConfigRequest):
    """Update LLM configuration only."""
    config = load_config()
    config.llm = LLMConfig(
        provider=request.provider,
        model=request.model,
        api_key=request.api_key,
        base_url=request.base_url,
        stream=request.stream,
    )
    save_config(config)
    return {"message": "LLM configuration saved"}


@app.put("/config/db")
def update_db_config(request: DBConfigRequest):
    """Update database configuration only."""
    config = load_config()
    config.db = DBConfig(connection=request.connection)
    save_config(config)
    # Clear cached schema/db_type when DB config changes
    cached_schema.cache_clear()
    cached_db_type.cache_clear()
    return {"message": "Database configuration saved"}


@app.post("/config/reset")
def reset_config_endpoint():
    """Reset configuration to environment defaults."""
    reset_config()
    cached_schema.cache_clear()
    cached_db_type.cache_clear()
    return {"message": "Configuration reset to defaults"}


@app.get("/schema", response_model=SchemaResponse)
def get_database_schema():
    """Get the database schema."""
    try:
        schema = get_schema()
        db_type = get_db_type()
        return SchemaResponse(db_schema=schema, db_type=db_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {str(e)}")


@app.post("/schema/load")
def load_schema_cache():
    """Preload and cache the database schema. Call this from the frontend on init."""
    try:
        # Clear existing cache first
        cached_schema.cache_clear()
        cached_db_type.cache_clear()
        # Load fresh
        schema = cached_schema()
        db_type = cached_db_type()
        return {
            "message": "Schema loaded successfully",
            "db_type": db_type,
            "tables_count": schema.count("Table:"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schema: {str(e)}")


@app.post("/generate-sql", response_model=GenerateSqlResponse)
def generate_sql_endpoint(request: GenerateSqlRequest):
    """
    Generate SQL from a natural language question without executing it.
    
    Use this to get the SQL first, then call /execute-sql to run it.
    """
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured. Update config first.")
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured. Update config first.")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="LYST_LLM_API_KEY is not set.")

    try:
        result = generate_sql(
            question=request.question,
            history=request.history.copy(),
        )
        return GenerateSqlResponse(
            sql=result.sql,
            history=result.history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL generation failed: {str(e)}")


@app.post("/execute-sql", response_model=ExecuteSqlResponse)
def execute_sql_endpoint(request: ExecuteSqlRequest):
    """
    Execute raw SQL against the database.
    
    Use this after /generate-sql to run the generated query.
    """
    config = load_config()
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured. Update config first.")

    try:
        columns, rows = execute_sql(request.sql)
        return ExecuteSqlResponse(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            success=True,
            error=None,
        )
    except Exception as e:
        return ExecuteSqlResponse(
            columns=[],
            rows=[],
            row_count=0,
            success=False,
            error=str(e),
        )


@app.post("/query", response_model=QueryResponse)
def run_query(request: QueryRequest):
    """
    Ask a question in plain English and get SQL + results.
    
    Pass previous history to maintain conversation context for follow-up questions.
    """
    # Validate configuration
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured. Update config first.")
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured. Update config first.")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="LYST_LLM_API_KEY is not set. Configure it in config or set the environment variable.")

    try:
        result: QueryResult = query(
            question=request.question,
            history=request.history.copy(),
            allow_correction=True,
        )
        return QueryResponse(
            sql=result.sql,
            columns=result.columns,
            rows=result.rows,
            summary=result.summary,
            history=result.history,
            success=result.success,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.post("/query/stream")
def run_query_stream(request: QueryRequest):
    """
    Streaming query endpoint - returns Server-Sent Events.
    """
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured. Update config first.")
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured. Update config first.")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="LYST_LLM_API_KEY is not set. Configure it in config or set the environment variable.")

    return StreamingResponse(
        query_stream(request.question, request.history.copy()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Quick chat about the project functionality without SQL execution.
    
    Use this for questions about the database schema, SQL concepts,
    how to use the tool, or data analysis guidance.
    """
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured. Update config first.")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="LYST_LLM_API_KEY is not set.")

    try:
        result = chat(
            message=request.message,
            history=request.history.copy(),
        )
        return ChatResponse(
            response=result.response,
            history=result.history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint - returns Server-Sent Events.
    
    Use this for questions about the database schema, SQL concepts,
    how to use the tool, or data analysis guidance.
    """
    config = load_config()
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured. Update config first.")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="LYST_LLM_API_KEY is not set.")

    return StreamingResponse(
        chat_stream(request.message, request.history.copy()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# --- History & Session Endpoints ---

@app.get("/history", response_model=HistoryResponse)
def get_history():
    """Get conversation history from active session."""
    messages = load_history()
    summary = history_summary()
    return HistoryResponse(messages=messages, summary=summary)


@app.put("/history")
def save_history_endpoint(request: SaveHistoryRequest):
    """Save conversation history to active session."""
    save_history(request.messages)
    return {"message": "History saved", "count": len(request.messages)}


@app.delete("/history")
def delete_history():
    """Clear conversation history in active session."""
    clear_history()
    return {"message": "History cleared"}


@app.get("/sessions", response_model=SessionListResponse)
def get_sessions():
    """List all conversation sessions."""
    sessions = list_sessions()
    active = get_active_session()
    return SessionListResponse(
        sessions=[SessionInfo(**s) for s in sessions],
        active_session_id=active.id if active else None,
    )


@app.post("/sessions", response_model=SessionDetailResponse)
def create_new_session(request: CreateSessionRequest):
    """Create a new conversation session and make it active."""
    session = create_session(request.name)
    return SessionDetailResponse(
        id=session.id,
        name=session.name,
        messages=session.messages,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@app.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(session_id: str):
    """Get a specific session by ID."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse(
        id=session.id,
        name=session.name,
        messages=session.messages,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@app.put("/sessions/{session_id}/activate")
def activate_session(session_id: str):
    """Set a session as the active session."""
    session = set_active_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session activated", "session_id": session.id}


@app.delete("/sessions/{session_id}")
def remove_session(session_id: str):
    """Delete a session."""
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@app.delete("/sessions")
def clear_sessions():
    """Delete all sessions."""
    clear_all_sessions()
    return {"message": "All sessions cleared"}


# --- Frontend ---

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
def frontend():
    """Serve the frontend."""
    html_path = STATIC_DIR / "index.html"
    return FileResponse(html_path, media_type="text/html")

# --- Entry point for running with uvicorn ---

def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run("app.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run_server()
