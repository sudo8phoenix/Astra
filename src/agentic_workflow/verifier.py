from __future__ import annotations

"""Completion verification logic for the agent loop."""

from typing import Any


def verify_goal(goal: str, memory: list[dict[str, Any]], iteration: int, max_iterations: int) -> dict[str, Any]:
    """Decide whether the loop should continue, complete, or fail."""
    if iteration >= max_iterations:
        return {
            "goal_achieved": False,
            "status": "failed",
            "final_answer": "Stopped after reaching max iterations.",
        }

    if memory:
        last_plan = memory[-1].get("plan", {})
        if isinstance(last_plan, dict) and last_plan.get("tool") == "finish":
            last_output = str(memory[-1].get("result", {}).get("output", "")).strip()
            return {
                "goal_achieved": True,
                "status": "complete",
                "final_answer": last_output or f"Completed reasoning loop for goal: {goal}",
            }

    if len(memory) >= 2 and str(memory[-1].get("result", {}).get("status", "")) == "error":
        last_output = str(memory[-1].get("result", {}).get("output", "")).strip()
        answer = last_output or f"Failed to complete reasoning loop for goal: {goal}"
        return {
            "goal_achieved": False,
            "status": "failed",
            "final_answer": answer,
        }

    return {
        "goal_achieved": False,
        "status": "running",
        "final_answer": "",
    }
