from __future__ import annotations

from typing import Any, Literal, TypedDict


class ToolResult(TypedDict):
    """Standard tool response contract used by executor and memory."""

    status: Literal["success", "error"]
    output: str
    metadata: dict[str, Any]


class AgentState(TypedDict):
    """Shared mutable state passed between LangGraph workflow nodes."""

    goal: str
    plan: dict[str, Any]
    tool_result: ToolResult | None
    memory: list[dict[str, Any]]
    status: Literal["running", "complete", "failed"]
    iteration: int
    max_iterations: int
    goal_achieved: bool
    final_answer: str
    file_root: str
