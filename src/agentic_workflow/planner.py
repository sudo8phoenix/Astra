from __future__ import annotations

"""Deterministic planning logic for Phase 2 tool selection."""

import re
from typing import Any


def planner(goal: str, memory: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the next structured action based on goal text and prior memory."""
    if not memory:
        lowered = goal.lower()

        if any(keyword in lowered for keyword in ["calculate", "calc", "sum", "multiply", "divide"]):
            expression = _extract_expression(goal)
            return {
                "step": "Compute arithmetic expression",
                "tool": "calculator",
                "input": {"expression": expression},
            }

        if any(keyword in lowered for keyword in ["run python", "python code", "execute python", "run code"]):
            return {
                "step": "Execute provided python code",
                "tool": "python_execute",
                "input": {"code": _extract_code(goal)},
            }

        if any(keyword in lowered for keyword in ["read file", "open file", ".md", ".txt", ".py"]):
            return {
                "step": "Read file content",
                "tool": "file_reader",
                "input": {"path": _extract_path(goal)},
            }

        return {
            "step": "Gather context from the web",
            "tool": "web_search",
            "input": {"query": goal},
        }

    return {
        "step": "Summarize the collected outputs and finish",
        "tool": "finish",
        "input": {"mode": "summarize_memory"},
    }


def _extract_expression(goal: str) -> str:
    """Extract a simple arithmetic expression from the user goal text."""

    candidate = goal
    for prefix in ["calculate", "calc", "what is", "evaluate"]:
        if candidate.lower().startswith(prefix):
            candidate = candidate[len(prefix):]
            break
    candidate = candidate.strip().strip(":")
    return candidate or "0"


def _extract_code(goal: str) -> str:
    """Extract Python code from a fenced code block in the goal if present."""

    if "```" in goal:
        segments = goal.split("```")
        if len(segments) >= 3:
            code_block = segments[1]
            if code_block.startswith("python"):
                code_block = code_block[len("python"):]
            return code_block.strip()
    return "print('No code block provided by user goal')"


def _extract_path(goal: str) -> str:
    """Extract a likely file path from goal text, with a safe default fallback."""

    match = re.search(r"([\w\- ./]+\.(md|txt|py|json|csv))", goal, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "Markdown files/plan.md"
