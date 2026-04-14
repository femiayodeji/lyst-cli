import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any

from app.config import load_config
from app.agent.stream import run_stream
from app.state import AppState, get_state

router = APIRouter()


class AgentRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


@router.post("/agent/stream")
def agent_stream_endpoint(request: AgentRequest, state: AppState = Depends(get_state)):
    _validate_config(state)
    return StreamingResponse(
        run_stream(request.message, request.history.copy(), state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _validate_config(state: AppState) -> None:
    config = load_config(state.db_connection_override)
    if not config.llm.model:
        raise HTTPException(status_code=400, detail="No LLM configured")
    if not config.db.connection:
        raise HTTPException(status_code=400, detail="No database configured")
    api_key = config.llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="No API key configured")
