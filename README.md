# Agentic AI Workflow System

Phase 2 implementation of the autonomous loop with a real tool layer.

## Implemented in Phase 2
- Basic LangGraph workflow (`planner -> executor -> verifier -> loop/end`)
- Planner node
- Executor node
- Verifier node
- Agent memory state management
- Tool layer:
  - web search
  - python execution
  - file reader
  - calculator

## Files
- `src/agentic_workflow/state.py`
- `src/agentic_workflow/planner.py`
- `src/agentic_workflow/executor.py`
- `src/agentic_workflow/verifier.py`
- `src/agentic_workflow/tools.py`
- `src/agentic_workflow/workflow.py`
- `src/agentic_workflow/api.py`

## Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.agentic_workflow.main:app --reload
```

## API
- `GET /health`
- `POST /run-agent`

Example payload:
```json
{
  "goal": "Analyze this startup idea and suggest initial competitors",
  "max_iterations": 8,
  "file_root": "."
}
```

## Notes
- This includes the Phase 2 tool layer with structured tool outputs.
- Planner is deterministic and keyword-based for now.
- LLM planner integration remains Phase 3.
