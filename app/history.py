from datetime import datetime

from app.state import AppState, Session


def create_session(state: AppState, name: str | None = None) -> Session:
    session_id = state.next_session_id()
    session_name = name or f"Session {len(state.sessions) + 1}"
    session = Session(id=session_id, name=session_name)
    state.sessions[session_id] = session
    state.active_session_id = session_id
    return session


def get_active_session(state: AppState) -> Session | None:
    if state.active_session_id is None:
        return None
    return state.sessions.get(state.active_session_id)


def get_or_create_active_session(state: AppState) -> Session:
    session = get_active_session(state)
    if session is None:
        session = create_session(state)
    return session


def set_active_session(state: AppState, session_id: str) -> Session | None:
    if session_id in state.sessions:
        state.active_session_id = session_id
        return state.sessions[session_id]
    return None


def list_sessions(state: AppState) -> list[dict]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "message_count": len(s.messages),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in sorted(state.sessions.values(), key=lambda x: x.created_at, reverse=True)
    ]


def get_session(state: AppState, session_id: str) -> Session | None:
    return state.sessions.get(session_id)


def delete_session(state: AppState, session_id: str) -> bool:
    if session_id in state.sessions:
        del state.sessions[session_id]
        if state.active_session_id == session_id:
            state.active_session_id = None
        return True
    return False


def save_history(state: AppState, messages: list[dict]) -> None:
    session = get_or_create_active_session(state)
    session.messages = messages
    session.updated_at = datetime.now().isoformat()


def clear_history(state: AppState) -> None:
    session = get_active_session(state)
    if session:
        session.messages = []
        session.updated_at = datetime.now().isoformat()


def clear_all_sessions(state: AppState) -> None:
    state.sessions.clear()
    state.active_session_id = None
    state._session_counter = 0