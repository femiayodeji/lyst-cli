import os
import json
from typing import Any, Generator

from litellm import completion
from litellm.exceptions import RateLimitError, APIConnectionError, APIError

from app.config import load_config
from app.db.schema import cached_schema, cached_db_type
from app.agent.tools import TOOLS, execute_tool
from app.agent.prompts import build_agent_prompt
from app.state import AppState


def _get_llm_config(state: AppState) -> tuple[str, str, str | None]:
    config = load_config(state.db_connection_override)
    llm = config.llm
    if not llm.model:
        raise ValueError("No LLM configured.")
    api_key = llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise ValueError("No API key configured.")
    model = llm.model
    if llm.provider and not model.startswith(f"{llm.provider}/"):
        model = f"{llm.provider}/{model}"
    return model, api_key, llm.base_url or None


def _call_llm(
    state: AppState,
    messages: list[dict],
    tools: list[dict] | None = None,
    stream: bool = False,
    tool_choice: str | dict | None = None,
) -> Any:
    model, api_key, base_url = _get_llm_config(state)
    kwargs: dict[str, Any] = {"model": model, "api_key": api_key, "messages": messages, "stream": stream}
    if base_url:
        kwargs["base_url"] = base_url
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"
    return completion(**kwargs)


def _process_tool_calls(assistant_message: Any) -> list[dict]:
    if not assistant_message.tool_calls:
        return []
    return [
        {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
        }
        for tc in assistant_message.tool_calls
    ]


def _extract_chunk_text(chunk: Any) -> str:
    try:
        choice = chunk.choices[0]
        delta = getattr(choice, "delta", None)
        if delta is None:
            return ""
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text_value = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                if text_value:
                    parts.append(str(text_value))
            return "".join(parts)
        return ""
    except Exception:
        return ""


def run_agent(
    message: str,
    history: list[dict],
    state: AppState,
    max_iterations: int = 5,
) -> Generator[dict, None, None]:
    """
    Transport-agnostic agent loop.

    Yields dicts with ``type`` and ``data`` keys representing agent events:
    status, tool_call, sql, result, message_chunk, message_complete,
    tool_calls, sql_results, history, error, done.
    """
    history = history.copy()
    history.append({"role": "user", "content": message})

    schema = cached_schema(state)
    db_type = cached_db_type(state)
    system_prompt = build_agent_prompt(schema, db_type)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history

    tool_calls_made: list[dict[str, Any]] = []
    sql_results: list[dict[str, Any]] = []

    try:
        for iteration in range(max_iterations):
            yield {"type": "status", "data": "Thinking..."}

            stream_response = _call_llm(state, messages, tools=TOOLS, stream=True)

            chunks: list[str] = []
            tool_calls_by_index: dict[int, dict] = {}
            generating = False

            for chunk in stream_response:
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue

                tc_list = getattr(delta, "tool_calls", None)
                if tc_list:
                    for tc_delta in tc_list:
                        idx = tc_delta.index
                        if idx not in tool_calls_by_index:
                            tool_calls_by_index[idx] = {"id": "", "name": "", "args_parts": []}
                        entry = tool_calls_by_index[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["args_parts"].append(tc_delta.function.arguments)

                text_chunk = _extract_chunk_text(chunk)
                if text_chunk:
                    chunks.append(text_chunk)
                    if not tool_calls_by_index:
                        if not generating:
                            yield {"type": "status", "data": "Generating response..."}
                            generating = True
                        yield {"type": "message_chunk", "data": text_chunk}

            # Build tool_infos from accumulated stream deltas
            tool_infos: list[dict] = []
            raw_tool_calls: list[dict] = []
            for idx in sorted(tool_calls_by_index):
                entry = tool_calls_by_index[idx]
                args_str = "".join(entry["args_parts"])
                tool_infos.append({
                    "id": entry["id"],
                    "name": entry["name"],
                    "arguments": json.loads(args_str) if args_str else {},
                })
                raw_tool_calls.append({
                    "id": entry["id"],
                    "type": "function",
                    "function": {"name": entry["name"], "arguments": args_str},
                })

            # No tool calls → finalize text response
            if not tool_infos:
                final_message = "".join(chunks).strip()
                history.append({"role": "assistant", "content": final_message})

                yield {"type": "message_complete", "data": final_message}
                yield {"type": "tool_calls", "data": tool_calls_made}
                yield {"type": "sql_results", "data": sql_results}
                yield {"type": "history", "data": history}
                yield {"type": "done", "data": {}}
                return

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": "".join(chunks),
                "tool_calls": raw_tool_calls,
            })

            # Execute each tool call
            for tc_info in tool_infos:
                yield {"type": "tool_call", "data": {"tool": tc_info["name"], "arguments": tc_info["arguments"]}}

                if tc_info["name"] == "execute_sql":
                    sql = tc_info["arguments"].get("sql", "")
                    yield {"type": "sql", "data": sql}
                    yield {"type": "status", "data": "Executing query..."}

                result = execute_tool(tc_info["name"], tc_info["arguments"], state)

                tool_calls_made.append({
                    "tool": tc_info["name"],
                    "arguments": tc_info["arguments"],
                    "result": result,
                })

                if tc_info["name"] == "execute_sql":
                    if result.get("success"):
                        sql_result = result["result"]
                        sql_results.append(sql_result)
                        yield {"type": "result", "data": {
                            "columns": sql_result["columns"],
                            "rows": sql_result["rows"],
                            "row_count": sql_result["row_count"],
                            "success": True,
                        }}
                    else:
                        yield {"type": "result", "data": {
                            "columns": [],
                            "rows": [],
                            "row_count": 0,
                            "success": False,
                            "error": result.get("error", "Unknown error"),
                        }}

                if tc_info["name"] == "visualize_data" and result.get("success"):
                    viz = result["result"]
                    yield {"type": "visualize", "data": {
                        "chart_type": viz["chart_type"],
                        "title": viz["title"],
                    }}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_info["id"],
                    "content": json.dumps(result, default=str),
                })

            yield {"type": "status", "data": "Analyzing results..."}

        yield {"type": "message_complete", "data": "Reached maximum iterations. Please try a simpler question."}
        yield {"type": "done", "data": {}}

    except RateLimitError:
        yield {"type": "error", "data": "Rate limit exceeded. Please wait and try again."}
        yield {"type": "done", "data": {}}
    except (APIConnectionError, APIError) as e:
        yield {"type": "error", "data": f"LLM API error: {str(e)}"}
        yield {"type": "done", "data": {}}
    except Exception as e:
        yield {"type": "error", "data": f"Unexpected error: {str(e)}"}
        yield {"type": "done", "data": {}}
