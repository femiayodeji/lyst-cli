import os
import json
from dataclasses import dataclass
from typing import Any, Generator

from litellm import completion
from litellm.exceptions import RateLimitError, APIConnectionError, APIError

from app.config import load_config
from app.tools import TOOLS, execute_tool
from app.prompts import build_agent_prompt


@dataclass
class AgentResponse:
    message: str
    tool_calls: list[dict]
    sql_results: list[dict]
    history: list[dict]


def _get_llm_config() -> tuple[str, str, str | None]:
    config = load_config()
    llm = config.llm
    if not llm.model:
        raise ValueError("No LLM configured.")
    api_key = llm.api_key or os.environ.get("LYST_LLM_API_KEY")
    if not api_key:
        raise ValueError("No API key configured.")
    return llm.model, api_key, llm.base_url or None


def _call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
    stream: bool = False,
    tool_choice: str | dict | None = None,
) -> Any:
    model, api_key, base_url = _get_llm_config()
    kwargs = {"model": model, "api_key": api_key, "messages": messages, "stream": stream}
    if base_url:
        kwargs["base_url"] = base_url
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"
    return completion(**kwargs)


def _looks_like_data_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    indicators = [
        "how many",
        "count",
        "total",
        "sum",
        "average",
        "avg",
        "report",
        "list",
        "show",
        "monthly",
        "year",
        "today",
        "this month",
        "this year",
        "last month",
        "last year",
        "users",
        "subscriptions",
    ]
    return any(token in text for token in indicators)


def _process_tool_calls(assistant_message: Any) -> list[dict]:
    if not assistant_message.tool_calls:
        return []
    return [
        {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {}
        }
        for tc in assistant_message.tool_calls
    ]


def run(message: str, history: list[dict] | None = None, max_iterations: int = 5) -> AgentResponse:
    history = (history or []).copy()
    history.append({"role": "user", "content": message})
    
    system_prompt = build_agent_prompt()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history
    
    tool_calls_made: list[dict[str, Any]] = []
    sql_results: list[dict[str, Any]] = []
    iterations = 0
    force_execute_sql = _looks_like_data_request(message)
    
    while iterations < max_iterations:
        llm_tools = TOOLS
        tool_choice = None
        if force_execute_sql and iterations == 0:
            llm_tools = [TOOLS[0]]
            tool_choice = {"type": "function", "function": {"name": "execute_sql"}}
        response = _call_llm(messages, tools=llm_tools, tool_choice=tool_choice)
        assistant_message = response.choices[0].message
        
        # Check for tool calls
        tool_infos = _process_tool_calls(assistant_message)
        
        if not tool_infos:
            # No tools needed - we have the final response
            final_message = assistant_message.content or ""
            history.append({"role": "assistant", "content": final_message})
            
            return AgentResponse(
                message=final_message,
                tool_calls=tool_calls_made,
                sql_results=sql_results,
                history=history
            )
        
        # Process tool calls
        # Add assistant message with tool_calls to messages
        messages.append({
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in assistant_message.tool_calls
            ]
        })
        
        for tc_info in tool_infos:
            # Execute the tool
            result = execute_tool(tc_info["name"], tc_info["arguments"])
            
            tool_calls_made.append({
                "tool": tc_info["name"],
                "arguments": tc_info["arguments"],
                "result": result
            })
            
            # Track SQL results
            if tc_info["name"] == "execute_sql" and result.get("success"):
                sql_results.append(result["result"])
            
            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc_info["id"],
                "content": json.dumps(result, default=str)
            })
        
        iterations += 1
    
    # Hit max iterations
    history.append({
        "role": "assistant", 
        "content": "I've made several attempts but couldn't fully answer. Please try rephrasing."
    })
    
    return AgentResponse(
        message="I've reached the maximum number of tool calls. Please try a simpler question.",
        tool_calls=tool_calls_made,
        sql_results=sql_results,
        history=history
    )


def run_stream(message: str, history: list[dict] | None = None, max_iterations: int = 5) -> Generator[str, None, None]:
    """
    Streaming version of the agent.
    
    Yields Server-Sent Events (SSE) formatted strings with:
    - type: "status" - Progress updates
    - type: "tool_call" - Tool being called
    - type: "sql" - SQL query being executed
    - type: "result" - Query results
    - type: "message_chunk" - Streaming response text
    - type: "message_complete" - Final response
    - type: "error" - Error occurred
    - type: "done" - Stream complete
    """
    
    def emit(event_type: str, data: Any) -> str:
        return f"data: {json.dumps({'type': event_type, 'data': data}, default=str)}\n\n"

    def _extract_chunk_text(chunk: Any) -> str:
        """Extract provider-agnostic text from a streaming chunk."""
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
                    text_value = None
                    if isinstance(item, dict):
                        text_value = item.get("text")
                    else:
                        text_value = getattr(item, "text", None)
                    if text_value:
                        parts.append(str(text_value))
                return "".join(parts)
            return ""
        except Exception:
            return ""
    
    history = (history or []).copy()
    history.append({"role": "user", "content": message})
    
    system_prompt = build_agent_prompt()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}] + history
    
    tool_calls_made: list[dict[str, Any]] = []
    sql_results: list[dict[str, Any]] = []
    iterations = 0
    force_execute_sql = _looks_like_data_request(message)
    
    try:
        while iterations < max_iterations:
            yield emit("status", "Thinking...")
            
            llm_tools = TOOLS
            tool_choice = None
            if force_execute_sql and iterations == 0:
                llm_tools = [TOOLS[0]]
                tool_choice = {"type": "function", "function": {"name": "execute_sql"}}
            response = _call_llm(messages, tools=llm_tools, tool_choice=tool_choice)
            assistant_message = response.choices[0].message
            
            tool_infos = _process_tool_calls(assistant_message)
            
            if not tool_infos:
                # Final response: stream tokens from LLM so the UI updates live.
                yield emit("status", "Generating response...")

                chunks: list[str] = []
                stream_response = _call_llm(messages, stream=True)
                for chunk in stream_response:
                    text_chunk = _extract_chunk_text(chunk)
                    if text_chunk:
                        chunks.append(text_chunk)
                        yield emit("message_chunk", text_chunk)

                final_message = "".join(chunks).strip() or (assistant_message.content or "")
                history.append({"role": "assistant", "content": final_message})
                
                yield emit("message_complete", final_message)
                yield emit("tool_calls", tool_calls_made)
                yield emit("sql_results", sql_results)
                yield emit("history", history)
                yield emit("done", {})
                return
            
            # Process tool calls
            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })
            
            for tc_info in tool_infos:
                yield emit("tool_call", {"tool": tc_info["name"], "arguments": tc_info["arguments"]})
                
                if tc_info["name"] == "execute_sql":
                    sql = tc_info["arguments"].get("sql", "")
                    yield emit("sql", sql)
                    yield emit("status", "Executing query...")
                
                # Execute tool
                result = execute_tool(tc_info["name"], tc_info["arguments"])
                
                tool_calls_made.append({
                    "tool": tc_info["name"],
                    "arguments": tc_info["arguments"],
                    "result": result
                })
                
                # Emit results
                if tc_info["name"] == "execute_sql":
                    if result.get("success"):
                        sql_result = result["result"]
                        sql_results.append(sql_result)
                        yield emit("result", {
                            "columns": sql_result["columns"],
                            "rows": sql_result["rows"],
                            "row_count": sql_result["row_count"],
                            "success": True
                        })
                    else:
                        yield emit("result", {
                            "columns": [],
                            "rows": [],
                            "row_count": 0,
                            "success": False,
                            "error": result.get("error", "Unknown error")
                        })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_info["id"],
                    "content": json.dumps(result, default=str)
                })
            
            iterations += 1
            yield emit("status", "Analyzing results...")
        
        # Max iterations
        yield emit("message_complete", "Reached maximum iterations. Please try a simpler question.")
        yield emit("done", {})
        
    except RateLimitError:
        yield emit("error", "Rate limit exceeded. Please wait and try again.")
        yield emit("done", {})
    except (APIConnectionError, APIError) as e:
        yield emit("error", f"LLM API error: {str(e)}")
        yield emit("done", {})
    except Exception as e:
        yield emit("error", f"Unexpected error: {str(e)}")
        yield emit("done", {})
