import re
from typing import Any, Callable

from app.state import AppState

TOOLS: list[dict] = []
_handlers: dict[str, Callable] = {}

_DANGEROUS_SQL = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|INSERT|UPDATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE|MERGE|REPLACE\s+INTO)\b",
    re.IGNORECASE,
)


def tool(name: str, description: str, parameters: dict):
    def decorator(fn: Callable) -> Callable:
        _handlers[name] = fn
        TOOLS.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })
        return fn
    return decorator


def execute_tool(name: str, arguments: dict[str, Any], state: AppState) -> dict[str, Any]:
    handler = _handlers.get(name)
    if not handler:
        return {"success": False, "error": f"Unknown tool: {name}"}
    try:
        return handler(state=state, **arguments)
    except Exception as e:
        return {"success": False, "error": str(e)}


def validate_sql(sql: str) -> str | None:
    if _DANGEROUS_SQL.search(sql):
        return "Query rejected: only read-only (SELECT) queries are allowed. Data modification is not permitted."
    return None


# ---- Tool definitions ----

@tool(
    name="execute_sql",
    description=(
        "Execute a read-only SQL SELECT query against the database and return the results. "
        "Only SELECT statements are allowed — any data-modifying SQL will be rejected."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A SELECT query to execute. Must be valid SQL for the database engine.",
            },
            "explanation": {
                "type": "string",
                "description": "Brief explanation of what this query does and why it answers the user's question.",
            },
        },
        "required": ["sql", "explanation"],
    },
)
def _execute_sql(state: AppState, sql: str = "", explanation: str = "") -> dict[str, Any]:
    error = validate_sql(sql)
    if error:
        return {"success": False, "error": error}
    from app.db.engine import run_query
    columns, rows = run_query(sql, state)
    return {
        "success": True,
        "result": {
            "sql": sql,
            "explanation": explanation,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        },
    }


@tool(
    name="get_database_schema",
    description="Get the database schema including all tables, columns, and foreign key relationships.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def _get_database_schema(state: AppState) -> dict[str, Any]:
    from app.db.engine import get_schema
    schema = get_schema(state)
    return {"success": True, "result": {"schema": schema}}


@tool(
    name="get_database_info",
    description="Get information about the database engine type (e.g., PostgreSQL, MySQL, SQLite).",
    parameters={"type": "object", "properties": {}, "required": []},
)
def _get_database_info(state: AppState) -> dict[str, Any]:
    from app.db.engine import get_db_type
    db_type = get_db_type(state)
    return {"success": True, "result": {"database_type": db_type}}
