from __future__ import annotations

"""FastAPI surface for running the agentic workflow."""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .workflow import run_agent_goal


class RunAgentRequest(BaseModel):
    """Request payload for launching one agent run."""

    goal: str = Field(..., min_length=3)
    max_iterations: int = Field(default=8, ge=1, le=20)
    file_root: str = Field(default=".")


app = FastAPI(title="Agentic AI Workflow - Phase 1", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return a basic health status for liveness checks."""

    return {"status": "ok"}


@app.post("/run-agent")
def run_agent(payload: RunAgentRequest) -> dict:
    """Execute the workflow for a goal and return final state summary."""

    return run_agent_goal(
        goal=payload.goal,
        max_iterations=payload.max_iterations,
        file_root=payload.file_root,
    )
