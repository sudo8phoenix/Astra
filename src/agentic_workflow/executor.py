from __future__ import annotations

"""Plan execution node logic and tool dispatch for Phase 2."""

from typing import Any

from .state import ToolResult
from .tools import calculator_tool, file_reader_tool, python_execute_tool, web_search_tool


def execute_plan(plan: dict[str, Any], goal: str, memory: list[dict[str, Any]], file_root: str) -> ToolResult:
    """Execute a planner action by dispatching to the selected tool.

    Falls back to a memory summarization step when the planner emits the
    synthetic `finish` tool with `summarize_memory` mode.
    """
    tool_name = str(plan.get("tool", ""))
    plan_input = plan.get("input", {})
    if not isinstance(plan_input, dict):
        plan_input = {}

    if tool_name == "calculator":
        return calculator_tool(expression=str(plan_input.get("expression", "0")))

    if tool_name == "python_execute":
        return python_execute_tool(code=str(plan_input.get("code", "print('No code provided')")))

    if tool_name == "file_reader":
        return file_reader_tool(path=str(plan_input.get("path", "")), file_root=file_root)

    if tool_name == "web_search":
        return web_search_tool(query=str(plan_input.get("query", goal)))

    if tool_name == "finish" and plan_input.get("mode") == "summarize_memory":
        summary = " | ".join(
            str(item.get("result", {}).get("output", ""))
            for item in memory
            if isinstance(item, dict) and item.get("result")
        ).strip()
        return {
            "status": "success",
            "output": summary or f"Goal analyzed by Phase 2 loop: {goal}",
            "metadata": {
                "executed_tool": "finish",
                "phase": "phase-2-tool-layer",
            },
        }

    return {
        "status": "error",
        "output": f"Unknown or unsupported tool in plan: {tool_name}",
        "metadata": {"executed_tool": tool_name, "phase": "phase-2-tool-layer"},
    }
