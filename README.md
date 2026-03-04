# Agentic AI Workflow (LangGraph + Groq)

A production-style agentic workflow with:
- **Planner Agent** (task decomposition)
- **Router Agent** (tool selection)
- **Executor Agent** (tool execution + chat)
- **Memory Agent** (session memory)
- **Evaluator Agent** (final quality check)

Includes a FastAPI backend, streaming chat endpoint, and a web chat UI showing live graph execution traces.

## Features

- Groq SDK integration (`groq` Python package)
- LangGraph `StateGraph` orchestration with cyclic control flow
- Tooling: `web_search`, `calculator`, `python_execute`, `file_reader`
- General conversation + tool-driven tasks
- Built-in checkpointed memory via LangGraph `MemorySaver` (threaded by `session_id`)
- Dynamic replanning when evaluator returns `retry`
- SSE streaming for real-time plan/route/execution/evaluation events

## Project Structure

- `agent_nodes.py` — all 5 agents + Groq client
- `tools.py` — tool implementations and dispatch
- `workflow.py` — LangGraph state machine (`planner → router → executor → evaluator → finalize`)
- `api_server.py` — FastAPI app (`/chat`, `/chat/stream`, `/health`, `/health/groq`)
- `chat_ui.html` — frontend chat interface
- `run_api.sh` — startup script (loads `.env`, auto-port handling)

## Prerequisites

- Python 3.11+ (tested in venv)
- Groq API key
- SerpAPI key (for web search tool)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn groq
pip install langgraph langchain langchain-core
```

Create `.env` in repo root:

```env
GROQ_API_KEY=your_groq_key
SERPAPI_API_KEY=your_serpapi_key

APP_HOST=127.0.0.1
APP_PORT=8003

PLANNER_MODEL=llama-3.3-70b-versatile
ROUTER_MODEL=llama-3.1-8b-instant
EXECUTOR_MODEL=llama-3.1-8b-instant
EVALUATOR_MODEL=llama-3.3-70b-versatile
```

## Run

```bash
./run_api.sh
```

Open:
- UI: `http://127.0.0.1:8003/`
- Health: `http://127.0.0.1:8003/health`
- Groq diagnostic: `http://127.0.0.1:8003/health/groq`

## API

### POST `/chat`

Request:

```json
{
  "message": "my name is cyril",
  "max_iterations": 6,
  "file_root": ".",
  "session_id": "optional-session-id"
}
```

Response includes:
- `final_answer`
- `plan`
- `task_results`
- `memory`
- `session_id`

### GET `/chat/stream`

Query params:
- `message`
- `max_iterations`
- `file_root`
- `session_id` (optional but recommended for memory continuity)

Returns SSE events: `session`, `plan`, `replan`, `route`, `execution`, `evaluation`, `final`, `error`.

## Session Memory

- Memory is checkpointed in LangGraph per `session_id` (`thread_id`)
- Frontend stores `session_id` in browser local storage
- Name recall example:
  1. `my name is cyril`
  2. `what's my name?` → `Your name is cyril.`

## Quick Test

```bash
curl -sS -X POST http://127.0.0.1:8003/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello","max_iterations":6,"file_root":"."}'
```

```bash
curl -N -sS "http://127.0.0.1:8003/chat/stream?message=calculate%2023-43&max_iterations=8&file_root=." | head -n 20
```
