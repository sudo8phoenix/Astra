from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from config import get_settings, setup_logging
from workflow import AgenticWorkflow, WorkflowConfig

setup_logging()
LOGGER = logging.getLogger(__name__)
SETTINGS = get_settings()


def _classify_groq_http_status(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "model_or_endpoint_not_found"
    if status_code == 429:
        return "rate_limited"
    if 500 <= status_code <= 599:
        return "provider_server_error"
    return "http_error"


async def run_groq_diagnostic(model: str | None = None) -> dict[str, Any]:
    api_key = (SETTINGS.groq_api_key or "").strip()
    selected_model = model or SETTINGS.router_model

    if not api_key:
        return {
            "ok": False,
            "status": "missing_api_key",
            "model": selected_model,
            "message": "GROQ_API_KEY is not set.",
        }

    try:
        from groq import AsyncGroq
    except ImportError:
        return {
            "ok": False,
            "status": "sdk_not_installed",
            "model": selected_model,
            "message": "Groq SDK is not installed. Install with: pip install groq",
        }

    client = AsyncGroq(api_key=api_key)

    try:
        completion = await client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": "You are a healthcheck endpoint."},
                {"role": "user", "content": "Reply with OK."},
            ],
            temperature=0,
            max_completion_tokens=8,
            top_p=1,
            stream=False,
            stop=None,
        )
        choices = getattr(completion, "choices", None) or []
        content = ""
        if choices:
            message = getattr(choices[0], "message", None)
            content = str(getattr(message, "content", "") or "")

        return {
            "ok": True,
            "status": "ok",
            "model": selected_model,
            "provider_http_status": 200,
            "response_preview": content[:120],
        }
    except Exception as exc:  # noqa: BLE001
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            return {
                "ok": False,
                "status": _classify_groq_http_status(int(status_code)),
                "model": selected_model,
                "provider_http_status": int(status_code),
                "message": str(exc),
            }

        error_text = str(exc)
        lowered = error_text.lower()
        if "timed out" in lowered or "timeout" in lowered:
            status = "timeout"
        elif "network" in lowered or "connection" in lowered:
            status = "network_error"
        else:
            status = "unexpected_error"

        return {
            "ok": False,
            "status": status,
            "model": selected_model,
            "message": error_text,
        }

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title=SETTINGS.app_name, version=SETTINGS.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    max_iterations: int = Field(default=SETTINGS.max_iterations_default, ge=1, le=50)
    file_root: str = Field(default=SETTINGS.default_file_root)
    session_id: str | None = Field(default=None)


@app.get("/", response_class=HTMLResponse)
async def chat_ui() -> HTMLResponse:
    ui_path = BASE_DIR / "chat_ui.html"
    if not ui_path.exists():
        return HTMLResponse("<h1>chat_ui.html not found</h1>", status_code=404)

    content = await asyncio.to_thread(ui_path.read_text, encoding="utf-8", errors="replace")
    return HTMLResponse(content)


@app.get("/chat-ui", response_class=HTMLResponse)
async def chat_ui_alias() -> HTMLResponse:
    return await chat_ui()


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "groq_key_present": bool(SETTINGS.groq_api_key),
        "serpapi_key_present": bool(SETTINGS.serpapi_api_key),
    }


@app.get("/health/groq")
async def health_groq(model: str | None = None) -> JSONResponse:
    diagnostic = await run_groq_diagnostic(model=model)
    status_code = 200 if diagnostic.get("ok") else 503
    return JSONResponse(content=diagnostic, status_code=status_code)


@app.post("/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    session_id = request.session_id or str(uuid4())

    workflow = AgenticWorkflow(
        WorkflowConfig(max_iterations=request.max_iterations, file_root=request.file_root)
    )
    result = await asyncio.to_thread(workflow.run, request.message, session_id=session_id)

    if isinstance(result, dict):
        result["session_id"] = session_id

    return JSONResponse(content=result)


@app.get("/chat/stream")
async def chat_stream(
    message: str,
    max_iterations: int = SETTINGS.max_iterations_default,
    file_root: str = SETTINGS.default_file_root,
    session_id: str | None = None,
) -> StreamingResponse:
    async def event_stream():
        active_session_id = session_id or str(uuid4())
        yield f"data: {json.dumps({'type': 'session', 'session_id': active_session_id}, ensure_ascii=False)}\n\n"

        workflow = AgenticWorkflow(WorkflowConfig(max_iterations=max_iterations, file_root=file_root))

        def collect_events() -> list[dict[str, Any]]:
            return [event for event in workflow.run_stream(message, session_id=active_session_id)]

        try:
            events = await asyncio.to_thread(collect_events)
            for event in events:
                if event.get("type") == "final":
                    result = event.get("result")
                    if isinstance(result, dict):
                        result["session_id"] = active_session_id
                        event = {"type": "final", "result": result}

                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Stream execution failed")
            payload = json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
