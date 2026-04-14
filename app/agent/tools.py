import re
from typing import Any, Callable

from app.state import AppState

TOOLS: list[dict] = []
_handlers: dict[str, Callable] = {}

_DANGEROUS_SQL = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|INSERT|UPDATE|ALTER|CREATE|GRANT|REVOKE|EXEC|EXECUTE|MERGE|REPLACE\s+INTO)\b",
    re.IGNORECASE,
)

_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([\w.\"]+)",
    re.IGNORECASE,
)


def _extract_schema_hint(sql: str, state: AppState) -> str:
    """Return the cached schema excerpt for tables referenced in *sql*."""
    from app.db.schema import cached_schema
    matches = _TABLE_REF.findall(sql)
    if not matches:
        return ""
    table_names = {m.strip('"').lower() for m in matches}
    schema_text = cached_schema(state)
    relevant: list[str] = []
    current_block: list[str] = []
    current_table: str | None = None
    for line in schema_text.splitlines():
        if line.startswith("Table: "):
            if current_table and current_table in table_names:
                relevant.extend(current_block)
            current_table = line.split("Table: ", 1)[1].strip().lower()
            current_block = [line]
        elif current_table is not None:
            current_block.append(line)
    if current_table and current_table in table_names:
        relevant.extend(current_block)
    return "\n".join(relevant).strip()


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
        error_msg = str(e)
        if name == "execute_sql":
            sql = arguments.get("sql", "")
            hint = _extract_schema_hint(sql, state)
            if hint:
                error_msg += f"\n\nRelevant schema for the tables referenced in your query:\n{hint}"
        return {"success": False, "error": error_msg}


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


@tool(
    name="visualize_data",
    description=(
        "Recommend a chart visualization for the most recent SQL query results. "
        "Call this AFTER execute_sql when the data is suitable for a chart. "
        "The UI will render the chart automatically using your recommendation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "pie", "doughnut"],
                "description": (
                    "The chart type that best represents the data. "
                    "Use 'bar' for comparisons, 'line' for time-series/trends, "
                    "'pie' or 'doughnut' for proportions with few categories (<=8)."
                ),
            },
            "title": {
                "type": "string",
                "description": "A short, descriptive chart title (e.g. 'Orders by Country', 'Monthly Revenue Trend').",
            },
        },
        "required": ["chart_type", "title"],
    },
)
def _visualize_data(state: AppState, chart_type: str = "bar", title: str = "") -> dict[str, Any]:
    return {
        "success": True,
        "result": {
            "chart_type": chart_type,
            "title": title,
        },
    }
