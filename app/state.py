import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from fastapi import Request
from sqlalchemy.engine import Engine


@dataclass
class Session:
    id: str
    name: str
    messages: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AppState:
    SCHEMA_TTL = 300.0  # seconds

    def __init__(self) -> None:
        # DB
        self.db_connection_override: str | None = None
        self.engines: dict[str, Engine] = {}

        # Schema cache
        self._schema_lock = threading.Lock()
        self._schema_value: str | None = None
        self._schema_ts: float = 0.0
        self._db_type_value: str | None = None
        self._db_type_ts: float = 0.0

        # Sessions
        self.sessions: dict[str, Session] = {}
        self.active_session_id: str | None = None
        self._session_counter: int = 0

    # ---- DB connection ----

    def set_db_connection(self, connection: str) -> None:
        self.db_connection_override = connection.strip() or None

    def reset_db_connection(self) -> None:
        self.db_connection_override = None

    def clear_engine_cache(self) -> None:
        self.engines.clear()

    # ---- Schema cache ----

    def get_cached_schema(self, loader: Callable[[], str]) -> str:
        with self._schema_lock:
            if self._schema_value is not None and (time.monotonic() - self._schema_ts) < self.SCHEMA_TTL:
                return self._schema_value
            value = loader()
            self._schema_value = value
            self._schema_ts = time.monotonic()
            return value

    def get_cached_db_type(self, loader: Callable[[], str]) -> str:
        with self._schema_lock:
            if self._db_type_value is not None and (time.monotonic() - self._db_type_ts) < self.SCHEMA_TTL:
                return self._db_type_value
            value = loader()
            self._db_type_value = value
            self._db_type_ts = time.monotonic()
            return value

    def clear_schema_cache(self) -> None:
        with self._schema_lock:
            self._schema_value = None
            self._schema_ts = 0.0
            self._db_type_value = None
            self._db_type_ts = 0.0

    # ---- Sessions ----

    def next_session_id(self) -> str:
        self._session_counter += 1
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._session_counter}"


def get_state(request: Request) -> AppState:
    return request.app.state.app_state
