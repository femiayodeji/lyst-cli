from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class Session:
    id: str
    name: str
    messages: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


_sessions: dict[str, Session] = {}
_active_session_id: str | None = None
_session_counter: int = 0


def _generate_session_id() -> str:
    global _session_counter
    _session_counter += 1
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_session_counter}"


def create_session(name: str | None = None) -> Session:
    global _active_session_id
    session_id = _generate_session_id()
    session_name = name or f"Session {len(_sessions) + 1}"
    session = Session(id=session_id, name=session_name)
    _sessions[session_id] = session
    _active_session_id = session_id
    return session


def get_active_session() -> Session | None:
    if _active_session_id is None:
        return None
    return _sessions.get(_active_session_id)


def get_or_create_active_session() -> Session:
    session = get_active_session()
    if session is None:
        session = create_session()
    return session


def set_active_session(session_id: str) -> Session | None:
    global _active_session_id
    if session_id in _sessions:
        _active_session_id = session_id
        return _sessions[session_id]
    return None


def list_sessions() -> list[dict]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "message_count": len(s.messages),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in sorted(_sessions.values(), key=lambda x: x.created_at, reverse=True)
    ]


def get_session(session_id: str) -> Session | None:
    return _sessions.get(session_id)


def delete_session(session_id: str) -> bool:
    global _active_session_id
    if session_id in _sessions:
        del _sessions[session_id]
        if _active_session_id == session_id:
            _active_session_id = None
        return True
    return False


def save_history(messages: list[dict]) -> None:
    session = get_or_create_active_session()
    session.messages = messages
    session.updated_at = datetime.now().isoformat()


def clear_history() -> None:
    session = get_active_session()
    if session:
        session.messages = []
        session.updated_at = datetime.now().isoformat()


def clear_all_sessions() -> None:
    global _sessions, _active_session_id, _session_counter
    _sessions = {}
    _active_session_id = None
    _session_counter = 0