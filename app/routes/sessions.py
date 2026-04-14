from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from app.history import (
    save_history, clear_history,
    list_sessions, get_session, create_session, delete_session,
    set_active_session, get_active_session,
)
from app.state import AppState, get_state

router = APIRouter()


class SaveHistoryRequest(BaseModel):
    messages: list[dict[str, Any]]


@router.get("/sessions")
def list_sessions_endpoint(state: AppState = Depends(get_state)):
    sessions = list_sessions(state)
    active = get_active_session(state)
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


@router.post("/sessions")
def create_session_endpoint(state: AppState = Depends(get_state)):
    session = create_session(state)
    set_active_session(state, session.id)
    return {
        "id": session.id,
        "name": session.name,
        "message_count": 0,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.get("/sessions/{session_id}")
def get_session_endpoint(session_id: str, state: AppState = Depends(get_state)):
    session = get_session(state, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id,
        "name": session.name,
        "messages": session.messages,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.delete("/sessions/{session_id}")
def delete_session_endpoint(session_id: str, state: AppState = Depends(get_state)):
    if not delete_session(state, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@router.put("/sessions/{session_id}/activate")
def activate_session_endpoint(session_id: str, state: AppState = Depends(get_state)):
    if not get_session(state, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    set_active_session(state, session_id)
    return {"message": "Session activated"}


@router.put("/history")
def save_history_endpoint(request: SaveHistoryRequest, state: AppState = Depends(get_state)):
    save_history(state, request.messages)
    return {"message": "History saved"}


@router.delete("/history")
def clear_history_endpoint(state: AppState = Depends(get_state)):
    clear_history(state)
    return {"message": "History cleared"}
