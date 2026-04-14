from app.db.engine import get_schema, get_db_type
from app.state import AppState


def cached_schema(state: AppState) -> str:
    return state.get_cached_schema(lambda: get_schema(state))


def cached_db_type(state: AppState) -> str:
    return state.get_cached_db_type(lambda: get_db_type(state))
