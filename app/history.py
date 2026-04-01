from datetime import datetime
from dataclasses import dataclass, field


MAX_HISTORY_EXCHANGES = 10


@dataclass
class Session:
    """A single conversation session."""
    id: str
    name: str
    messages: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# In-memory session storage
_sessions: dict[str, Session] = {}
_active_session_id: str | None = None
_session_counter: int = 0


def _generate_session_id() -> str:
    """Generate a unique session ID."""
    global _session_counter
    _session_counter += 1
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_session_counter}"


def create_session(name: str | None = None) -> Session:
    """Create a new session and make it active."""
    global _active_session_id
    session_id = _generate_session_id()
    session_name = name or f"Session {len(_sessions) + 1}"
    session = Session(id=session_id, name=session_name)
    _sessions[session_id] = session
    _active_session_id = session_id
    return session


def get_active_session() -> Session | None:
    """Get the currently active session."""
    if _active_session_id is None:
        return None
    return _sessions.get(_active_session_id)


def get_or_create_active_session() -> Session:
    """Get active session or create one if none exists."""
    session = get_active_session()
    if session is None:
        session = create_session()
    return session


def set_active_session(session_id: str) -> Session | None:
    """Set a session as active by ID."""
    global _active_session_id
    if session_id in _sessions:
        _active_session_id = session_id
        return _sessions[session_id]
    return None


def list_sessions() -> list[dict]:
    """List all sessions with metadata."""
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
    """Get a session by ID."""
    return _sessions.get(session_id)


def delete_session(session_id: str) -> bool:
    """Delete a session by ID."""
    global _active_session_id
    if session_id in _sessions:
        del _sessions[session_id]
        if _active_session_id == session_id:
            _active_session_id = None
        return True
    return False


def load_history() -> list[dict]:
    """Load messages from active session."""
    session = get_active_session()
    return session.messages if session else []


def save_history(messages: list[dict]) -> None:
    """Save messages to active session."""
    session = get_or_create_active_session()
    session.messages = messages
    session.updated_at = datetime.now().isoformat()


def append_exchange(history: list[dict], user_input: str, assistant_response: str) -> list[dict]:
    """Append a Q&A exchange to history with truncation."""
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": assistant_response})

    max_messages = MAX_HISTORY_EXCHANGES * 2
    if len(history) > max_messages:
        history = history[-max_messages:]

    return history


def clear_history() -> None:
    """Clear messages in active session."""
    session = get_active_session()
    if session:
        session.messages = []
        session.updated_at = datetime.now().isoformat()


def clear_all_sessions() -> None:
    """Clear all sessions."""
    global _sessions, _active_session_id, _session_counter
    _sessions = {}
    _active_session_id = None
    _session_counter = 0


def history_summary() -> str:
    """Get summary of active session."""
    session = get_active_session()
    if not session or not session.messages:
        return "No active session."
    exchanges = len(session.messages) // 2
    return f"{exchanges} exchange(s) in session '{session.name}'"