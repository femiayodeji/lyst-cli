from typing import Any
from app.db import run_query as db_run_query, get_schema as db_get_schema, get_db_type

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Execute a SQL query against the database and return the results. Use this when you need to retrieve or modify data. Only call this with valid SQL that matches the database schema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to execute. Must be valid SQL for the database engine."
                    },
                    "explanation": {
                        "type": "string", 
                        "description": "Brief explanation of what this query does and why it answers the user's question."
                    }
                },
                "required": ["sql", "explanation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "Get the database schema including all tables, columns, and foreign key relationships. Use this when you need to understand the database structure before writing a query, or when the user asks about available tables/columns.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_database_info",
            "description": "Get information about the database engine type (e.g., PostgreSQL, MySQL, SQLite). Use this when you need to know dialect-specific syntax.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if tool_name == "execute_sql":
            sql = arguments.get("sql", "")
            explanation = arguments.get("explanation", "")
            columns, rows = db_run_query(sql)
            return {
                "success": True,
                "result": {
                    "sql": sql,
                    "explanation": explanation,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                }
            }
        
        elif tool_name == "get_database_schema":
            schema = db_get_schema()
            return {
                "success": True,
                "result": {
                    "schema": schema
                }
            }
        
        elif tool_name == "get_database_info":
            db_type = get_db_type()
            return {
                "success": True,
                "result": {
                    "database_type": db_type
                }
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
