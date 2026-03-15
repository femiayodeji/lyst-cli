import os
from dataclasses import dataclass
from litellm import completion
from .config import load_config
from .db import get_schema, get_db_type, run_query
from typing import Any, List, Dict


@dataclass
class QueryResult:
    sql: str
    columns: List[Any]
    rows: List[Any]
    summary: str
    history: List[dict]
    success: bool


def build_system_prompt() -> str:
    schema = get_schema()
    db_type = get_db_type()
    return f"""You are a SQL expert assistant. Your job is to help users query their database using plain English.

You have access to the following database schema:
{schema}

Rules:
- Generate only valid SQL for the connected database type: {db_type}
- Return only the raw SQL query, no explanation, no markdown, no backticks
- Use only tables and columns that exist in the schema above
- When the user asks a follow-up question, take into account previous queries and results in the conversation
- If the question is ambiguous, make a reasonable assumption and generate the SQL
- If the question cannot be answered with the available schema, say so clearly instead of generating SQL

Query results will be provided back to you after execution. Use them to give a brief, clear summary of the findings in plain English."""


def get_llm_response(history: List[Dict[str, Any]]) -> str:
    config = load_config()
    llm = config.llm

    if not llm.model:
        raise ValueError("No LLM configured. Run: lyst config set --model <model>")

    api_key = os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise ValueError("LYST_LLM_API_KEY environment variable is not set.")

    messages = [{"role": "system", "content": build_system_prompt()}] + history

    response = completion(
        model=llm.model,
        base_url=llm.base_url or None,
        api_key=api_key,
        messages=messages,
        stream=llm.stream
    )

    if llm.stream:
        result = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            print(delta, end="", flush=True)
            result += delta
        print()
        return result

    try:
        return response.choices[0].message.content or ""
    except Exception:
        try:
            return response["choices"][0]["message"]["content"] or ""
        except Exception:
            return str(response)


def query(question: str, history: List[Dict[str, Any]]) -> QueryResult:
    history.append({"role": "user", "content": question})

    sql = get_llm_response(history)
    history.append({"role": "assistant", "content": sql})

    try:
        columns, rows = run_query(sql)
        result_text = f"Query result — columns: {columns}, rows: {rows[:20]}"
        history.append({"role": "user", "content": result_text})

        summary = get_llm_response(history)
        history.append({"role": "assistant", "content": summary})

        return QueryResult(
            sql=sql,
            columns=columns,
            rows=rows,
            summary=summary,
            history=history,
            success=True
        )

    except Exception as e:
        error_msg = f"SQL execution error: {str(e)}"
        history.append({"role": "user", "content": error_msg})

        correction = get_llm_response(history)
        history.append({"role": "assistant", "content": correction})

        return QueryResult(
            sql=correction,
            columns=[],
            rows=[],
            summary="Query failed. LLM suggested a correction above.",
            history=history,
            success=False
        )