import json
from typing import Generator

from app.agent.loop import run_agent
from app.state import AppState


def run_stream(
    message: str,
    history: list[dict],
    state: AppState,
    max_iterations: int = 5,
) -> Generator[str, None, None]:
    """Wraps :func:`run_agent` events in Server-Sent Events format."""
    for event in run_agent(message, history, state, max_iterations):
        yield f"data: {json.dumps(event, default=str)}\n\n"
