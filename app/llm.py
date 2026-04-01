import os
import re
from dataclasses import dataclass
from litellm import completion
from litellm.exceptions import RateLimitError, APIConnectionError, APIError
from app.config import load_config
from app.db import run_query, get_schema, get_db_type
from typing import Any, List, Dict, Generator
from functools import lru_cache
import sqlalchemy
import json


def extract_sql(response: str) -> str:
    """
    Extract SQL query from LLM response.
    Expects SQL wrapped in ```sql ... ``` code blocks.
    """
    if not response or not response.strip():
        return response
    
    text = response.strip()
    
    # Extract from ```sql ... ``` code block
    sql_block_pattern = r'```sql\s*\n([\s\S]*?)\n?```'
    match = re.search(sql_block_pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback: try generic code block
    generic_block_pattern = r'```\s*\n([\s\S]*?)\n?```'
    match = re.search(generic_block_pattern, text)
    if match:
        return match.group(1).strip()
    
    # If no code block but starts with SQL keyword, return as-is
    if re.match(r'^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP)\b', text, re.IGNORECASE):
        return text
    
    # Return original - might be an error message or "cannot answer"
    return text


@dataclass
class QueryResult:
    sql: str
    columns: List[Any]
    rows: List[Any]
    summary: str
    history: List[dict]
    success: bool




# Use LRU cache for schema and db_type
@lru_cache(maxsize=1)
def cached_schema():
    return get_schema()

@lru_cache(maxsize=1)
def cached_db_type():
    return get_db_type()

def build_system_prompt() -> str:
    schema = cached_schema()
    db_type = cached_db_type()
    schema_warning = "" if schema.strip() else "WARNING: The schema could not be introspected."

    return f"""You are a SQL expert. Generate valid SQL queries from natural language questions.

Database engine: {db_type}
{schema_warning}

Schema:
{schema}

RULES:
1. Generate SQL valid for {db_type} - you know this dialect's syntax, quoting rules, and functions
2. Use ONLY tables and columns from the schema above
3. Handle identifier quoting correctly for {db_type} (e.g., mixed-case names, reserved words)
4. Always wrap your SQL in a code block like this:

```sql
SELECT * FROM users
```

5. If you cannot answer, explain why (no code block)
6. For follow-ups, consider the conversation history
"""


def build_summary_prompt() -> str:
    return """You are a data analyst assistant. Given the SQL query that was executed and its results, provide a brief, conversational summary of the findings.

Rules:
- Be concise but informative (2-4 sentences)
- Highlight key insights or patterns in the data
- Use natural language, not technical jargon
- If there are no results, explain what that might mean
- Don't repeat the SQL or raw data, just summarize the meaning"""


def build_chat_prompt() -> str:
    """Build system prompt for quick chat - restricted to project functionality."""
    schema = cached_schema()
    db_type = cached_db_type()
    
    return f"""You are lyst, an AI assistant specialized in database querying and data analysis. Your purpose is to help users interact with their database using natural language.

The database engine is: {db_type}

Available database schema:
{schema}

You can help users with:
- Understanding how to phrase questions for SQL generation
- Explaining database concepts, SQL syntax, and query optimization
- Describing what tables and columns are available in their schema
- Suggesting questions they might ask about their data
- Explaining query results and data patterns
- Troubleshooting query errors
- Best practices for data analysis

You should NOT:
- Discuss topics unrelated to databases, SQL, or data analysis
- Provide information outside the scope of this data querying tool
- Generate or execute SQL queries (use the Query mode for that)
- Discuss general knowledge topics, current events, or other domains

If asked about unrelated topics, politely redirect the conversation to database and data analysis topics.

Keep responses concise and helpful. Use the schema information to give specific, relevant answers about the user's database."""


@dataclass
class ChatResult:
    response: str
    history: List[dict]



def get_llm_response(history: List[Dict[str, Any]], system_prompt: str = "") -> str:
    config = load_config()
    llm = config.llm

    if not llm.model:
        raise ValueError("No LLM configured. Run: lyst config set --model <model>")

    api_key = llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise ValueError("LYST_LLM_API_KEY is not set. Configure it in config or set the environment variable.")

    if system_prompt is None:
        system_prompt = build_system_prompt()

    messages = [{"role": "system", "content": system_prompt}] + history

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


@dataclass
class GenerateSqlResult:
    sql: str
    history: List[dict]


def generate_sql(question: str, history: List[Dict[str, Any]]) -> GenerateSqlResult:
    """
    Generate SQL from a natural language question without executing it.
    """
    system_prompt = build_system_prompt()
    history = history.copy()
    history.append({"role": "user", "content": question})

    raw_response = get_llm_response(history, system_prompt=system_prompt)
    sql = extract_sql(raw_response)
    history.append({"role": "assistant", "content": sql})

    return GenerateSqlResult(sql=sql, history=history)


def query(question: str, history: List[Dict[str, Any]], allow_correction: bool = True) -> QueryResult:
    """
    allow_correction: If True, will call LLM for correction on SQL error. If False, returns error immediately.
    """
    system_prompt = build_system_prompt()
    history.append({"role": "user", "content": question})

    # First LLM call: get SQL
    raw_response = get_llm_response(history, system_prompt=system_prompt)
    sql = extract_sql(raw_response)
    history.append({"role": "assistant", "content": sql})

    try:
        columns, rows = run_query(sql)
        summary = f"Query succeeded. Returned {len(rows)} row(s) and columns: {columns}."
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

        if allow_correction:
            raw_correction = get_llm_response(history, system_prompt=system_prompt)
            correction = extract_sql(raw_correction)
            history.append({"role": "assistant", "content": correction})
            return QueryResult(
                sql=correction,
                columns=[],
                rows=[],
                summary="Query failed. LLM suggested a correction above.",
                history=history,
                success=False
            )
        else:
            return QueryResult(
                sql=sql,
                columns=[],
                rows=[],
                summary=error_msg,
                history=history,
                success=False
            )


def get_llm_response_stream(history: List[Dict[str, Any]], system_prompt: str = "") -> Generator[str, None, None]:
    """Streaming version of get_llm_response."""
    config = load_config()
    llm = config.llm

    if not llm.model:
        raise ValueError("No LLM configured. Run: lyst config set --model <model>")

    api_key = llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise ValueError("LYST_LLM_API_KEY is not set. Configure it in config or set the environment variable.")

    if system_prompt is None:
        system_prompt = build_system_prompt()

    messages = [{"role": "system", "content": system_prompt}] + history

    response = completion(
        model=llm.model,
        base_url=llm.base_url or None,
        api_key=api_key,
        messages=messages,
        stream=True
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


def query_stream(question: str, history: List[Dict[str, Any]]) -> Generator[str, None, None]:
    """
    Streaming query - yields SSE events for three sections:
    1. SQL generation (sql_chunk, sql_complete)
    2. Query execution (result)
    3. Chat summary (chat_chunk, chat_complete)
    """
    system_prompt = build_system_prompt()
    summary_prompt = build_summary_prompt()
    history = history.copy()
    history.append({"role": "user", "content": question})

    # Phase 1: Stream SQL generation
    yield f"data: {json.dumps({'type': 'status', 'content': 'Generating SQL...'})}\n\n"
    
    try:
        sql_parts = []
        for chunk in get_llm_response_stream(history, system_prompt=system_prompt):
            sql_parts.append(chunk)
            yield f"data: {json.dumps({'type': 'sql_chunk', 'content': chunk})}\n\n"
        
        raw_sql = "".join(sql_parts)
        sql = extract_sql(raw_sql)
        history.append({"role": "assistant", "content": sql})
        yield f"data: {json.dumps({'type': 'sql_complete', 'content': sql})}\n\n"
    except RateLimitError as e:
        error_msg = "Rate limit exceeded. Please wait a moment and try again."
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return
    except (APIConnectionError, APIError) as e:
        error_msg = f"LLM API error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Phase 2: Execute SQL
    yield f"data: {json.dumps({'type': 'status', 'content': 'Executing query...'})}\n\n"
    
    try:
        columns, rows = run_query(sql)
        # Convert rows to serializable format
        serializable_rows = [list(row) if hasattr(row, '__iter__') and not isinstance(row, (str, dict)) else row for row in rows]
        
        result_data = {
            'type': 'result',
            'columns': columns,
            'rows': serializable_rows,
            'row_count': len(rows),
            'success': True
        }
        yield f"data: {json.dumps(result_data, default=str)}\n\n"
        
        # Phase 3: Generate chat summary
        yield f"data: {json.dumps({'type': 'status', 'content': 'Generating summary...'})}\n\n"
        
        # Build context for summary
        result_preview = f"Columns: {columns}\nRows returned: {len(rows)}"
        if rows and len(rows) <= 10:
            result_preview += f"\nData: {serializable_rows}"
        elif rows:
            result_preview += f"\nFirst 5 rows: {serializable_rows[:5]}"
        
        summary_history = [
            {"role": "user", "content": f"Question: {question}\n\nSQL executed:\n{sql}\n\nResults:\n{result_preview}"}
        ]
        
        chat_parts = []
        for chunk in get_llm_response_stream(summary_history, system_prompt=summary_prompt):
            chat_parts.append(chunk)
            yield f"data: {json.dumps({'type': 'chat_chunk', 'content': chunk})}\n\n"
        
        chat_summary = "".join(chat_parts)
        yield f"data: {json.dumps({'type': 'chat_complete', 'content': chat_summary})}\n\n"
        
        history.append({"role": "assistant", "content": f"Summary: {chat_summary}"})
        
    except Exception as e:
        error_msg = f"SQL execution error: {str(e)}"
        yield f"data: {json.dumps({'type': 'result', 'columns': [], 'rows': [], 'row_count': 0, 'success': False, 'error': error_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'chat_complete', 'content': f'The query failed with an error: {str(e)}. I will try to correct it.'})}\n\n"
        
        history.append({"role": "user", "content": error_msg})
        
        # Try correction
        yield f"data: {json.dumps({'type': 'status', 'content': 'Attempting correction...'})}\n\n"
        
        correction_parts = []
        for chunk in get_llm_response_stream(history, system_prompt=system_prompt):
            correction_parts.append(chunk)
            yield f"data: {json.dumps({'type': 'sql_chunk', 'content': chunk})}\n\n"
        
        raw_correction = "".join(correction_parts)
        correction = extract_sql(raw_correction)
        history.append({"role": "assistant", "content": correction})
        yield f"data: {json.dumps({'type': 'sql_complete', 'content': correction})}\n\n"
        
        # Try executing corrected SQL
        try:
            columns, rows = run_query(correction)
            serializable_rows = [list(row) if hasattr(row, '__iter__') and not isinstance(row, (str, dict)) else row for row in rows]
            
            result_data = {
                'type': 'result',
                'columns': columns,
                'rows': serializable_rows,
                'row_count': len(rows),
                'success': True
            }
            yield f"data: {json.dumps(result_data, default=str)}\n\n"
            
            # Generate summary for corrected query
            result_preview = f"Columns: {columns}\nRows returned: {len(rows)}"
            if rows and len(rows) <= 10:
                result_preview += f"\nData: {serializable_rows}"
            elif rows:
                result_preview += f"\nFirst 5 rows: {serializable_rows[:5]}"
            
            summary_history = [
                {"role": "user", "content": f"Question: {question}\n\nSQL executed (after correction):\n{correction}\n\nResults:\n{result_preview}"}
            ]
            
            chat_parts = []
            for chunk in get_llm_response_stream(summary_history, system_prompt=summary_prompt):
                chat_parts.append(chunk)
                yield f"data: {json.dumps({'type': 'chat_chunk', 'content': chunk})}\n\n"
            
            chat_summary = "".join(chat_parts)
            yield f"data: {json.dumps({'type': 'chat_complete', 'content': chat_summary})}\n\n"
            
        except Exception as e2:
            yield f"data: {json.dumps({'type': 'result', 'columns': [], 'rows': [], 'row_count': 0, 'success': False, 'error': str(e2)})}\n\n"
            yield f"data: {json.dumps({'type': 'chat_complete', 'content': f'The corrected query also failed: {str(e2)}. Please try rephrasing your question.'})}\n\n"
    
    yield f"data: {json.dumps({'type': 'history', 'content': history})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


def chat(message: str, history: List[Dict[str, Any]]) -> ChatResult:
    """
    Quick chat about the project functionality without SQL execution.
    """
    system_prompt = build_chat_prompt()
    history = history.copy()
    history.append({"role": "user", "content": message})

    response = get_llm_response(history, system_prompt=system_prompt)
    history.append({"role": "assistant", "content": response})

    return ChatResult(response=response, history=history)


def chat_stream(message: str, history: List[Dict[str, Any]]) -> Generator[str, None, None]:
    """
    Streaming chat - yields SSE events for chat responses.
    """
    system_prompt = build_chat_prompt()
    history = history.copy()
    history.append({"role": "user", "content": message})

    yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking...'})}\n\n"
    
    try:
        response_parts = []
        for chunk in get_llm_response_stream(history, system_prompt=system_prompt):
            response_parts.append(chunk)
            yield f"data: {json.dumps({'type': 'chat_chunk', 'content': chunk})}\n\n"
        
        response = "".join(response_parts)
        history.append({"role": "assistant", "content": response})
        yield f"data: {json.dumps({'type': 'chat_complete', 'content': response})}\n\n"
        yield f"data: {json.dumps({'type': 'history', 'content': history})}\n\n"
    except RateLimitError as e:
        error_msg = "Rate limit exceeded. Please wait a moment and try again."
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
    except (APIConnectionError, APIError) as e:
        error_msg = f"LLM API error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
    
    yield f"data: {json.dumps({'type': 'done'})}\n\n"