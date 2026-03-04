from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import threading
from dataclasses import dataclass
from math import sqrt
from typing import Any, Callable, TypeVar

from config import get_settings
from tools import get_tool_specs, run_tool

LOGGER = logging.getLogger(__name__)
SETTINGS = get_settings()
_T = TypeVar("_T")


# Architectural note:
# This helper keeps backward compatibility with the existing synchronous workflow
# while enabling async-native Groq calls underneath.
def _run_async_blocking(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    holder: dict[str, Any] = {}

    def runner() -> None:
        try:
            holder["result"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in holder:
        raise holder["error"]
    return holder.get("result")


def _safe_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_cycle(tasks: list[dict[str, Any]]) -> bool:
    graph = {str(task["id"]): set(str(dep) for dep in task.get("depends_on", [])) for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visited:
            return False
        if node in visiting:
            return True

        visiting.add(node)
        for dep in graph.get(node, set()):
            if dep in graph and dfs(dep):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(dfs(node) for node in graph)


def _normalize_dag_tasks(raw_tasks: Any, max_tasks: int = 8) -> list[dict[str, Any]]:
    if not isinstance(raw_tasks, list):
        return []

    capped = raw_tasks[: max(1, int(max_tasks))]
    normalized: list[dict[str, Any]] = []

    if capped and all(not isinstance(item, dict) for item in capped):
        previous_id: str | None = None
        for index, item in enumerate(capped, start=1):
            task_text = str(item).strip()
            if not task_text:
                continue
            task_id = f"t{index}"
            deps = [previous_id] if previous_id else []
            normalized.append({"id": task_id, "task": task_text, "depends_on": deps})
            previous_id = task_id
    else:
        for index, item in enumerate(capped, start=1):
            if not isinstance(item, dict):
                continue

            task_text = str(item.get("task", "")).strip() or str(item.get("description", "")).strip()
            if not task_text:
                continue

            task_id = str(item.get("id") or f"t{index}").strip() or f"t{index}"
            raw_deps = item.get("depends_on", [])

            if isinstance(raw_deps, str):
                deps = [raw_deps.strip()] if raw_deps.strip() else []
            elif isinstance(raw_deps, list):
                deps = [str(dep).strip() for dep in raw_deps if str(dep).strip()]
            else:
                deps = []

            normalized.append({"id": task_id, "task": task_text, "depends_on": deps})

    if not normalized:
        return []

    seen_ids: set[str] = set()
    for item in normalized:
        base_id = str(item["id"])
        candidate = base_id
        suffix = 2
        while candidate in seen_ids:
            candidate = f"{base_id}_{suffix}"
            suffix += 1
        item["id"] = candidate
        seen_ids.add(candidate)

    valid_ids = {str(item["id"]) for item in normalized}
    for item in normalized:
        task_id = str(item["id"])
        cleaned_deps: list[str] = []
        for dep in item.get("depends_on", []):
            dep_id = str(dep)
            if dep_id and dep_id in valid_ids and dep_id != task_id and dep_id not in cleaned_deps:
                cleaned_deps.append(dep_id)
        item["depends_on"] = cleaned_deps

    if _has_cycle(normalized):
        LOGGER.warning("Planner produced cyclic DAG; falling back to sequential dependency chain.")
        sequential: list[dict[str, Any]] = []
        previous_id: str | None = None
        for index, item in enumerate(normalized, start=1):
            task_id = f"t{index}"
            sequential.append(
                {
                    "id": task_id,
                    "task": str(item.get("task", "")).strip(),
                    "depends_on": [previous_id] if previous_id else [],
                }
            )
            previous_id = task_id
        return sequential

    return normalized


def _schema_type_from_hint(schema_hint: Any) -> str:
    hint = str(schema_hint).lower()
    if "integer" in hint or hint == "int":
        return "integer"
    if "float" in hint or "number" in hint:
        return "number"
    if "bool" in hint or "boolean" in hint:
        return "boolean"
    if "array" in hint or "list" in hint:
        return "array"
    if "object" in hint or "dict" in hint:
        return "object"
    return "string"


def _text_vector(text: str) -> dict[str, float]:
    tokens = re.findall(r"[a-zA-Z0-9_']+", text.lower())
    if not tokens:
        return {}

    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    norm = sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return {}

    return {token: value / norm for token, value in counts.items()}


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(token, 0.0) for token, weight in left.items())


def _truncate_text(value: Any, max_chars: int = 320) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _compact_tool_output(tool_output: Any) -> dict[str, Any]:
    if not isinstance(tool_output, dict):
        return {"summary": _truncate_text(tool_output, max_chars=160)}

    compact: dict[str, Any] = {}
    if "ok" in tool_output:
        compact["ok"] = bool(tool_output.get("ok"))

    for key in ("error", "response", "result", "expression", "path", "truncated"):
        if key in tool_output:
            value = tool_output.get(key)
            compact[key] = _truncate_text(value) if isinstance(value, str) else value

    stdout = tool_output.get("stdout")
    if isinstance(stdout, str) and stdout.strip():
        compact["stdout"] = _truncate_text(stdout)

    results = tool_output.get("results")
    if isinstance(results, list) and results:
        compact["results"] = [
            {
                "title": _truncate_text(item.get("title", ""), max_chars=120),
                "link": _truncate_text(item.get("link", ""), max_chars=180),
                "snippet": _truncate_text(item.get("snippet", ""), max_chars=180),
            }
            for item in results[:3]
            if isinstance(item, dict)
        ]

    return compact


def _compact_task_results(task_results: list[dict[str, Any]], max_items: int = 4) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in task_results[-max(1, int(max_items)) :]:
        if not isinstance(item, dict):
            continue

        route = item.get("route", {})
        route_tool = str(route.get("tool", "")) if isinstance(route, dict) else ""
        compacted.append(
            {
                "task": _truncate_text(item.get("task", ""), max_chars=180),
                "route": {"tool": route_tool},
                "tool_output": _compact_tool_output(item.get("tool_output", {})),
            }
        )
    return compacted


def _compact_memory_for_prompt(memory: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(memory, dict):
        return {}

    compact: dict[str, Any] = {}

    user_profile = memory.get("user_profile")
    if isinstance(user_profile, dict):
        compact["user_profile"] = {
            str(key): _truncate_text(value, max_chars=120)
            for key, value in user_profile.items()
        }

    chat_history = memory.get("chat_history")
    if isinstance(chat_history, list):
        compact["chat_history"] = [
            {
                "role": str(item.get("role", "")),
                "content": _truncate_text(item.get("content", ""), max_chars=220),
            }
            for item in chat_history[-8:]
            if isinstance(item, dict)
        ]

    retrieved = memory.get("retrieved_chat_context")
    if isinstance(retrieved, list):
        compact["retrieved_chat_context"] = [
            {
                "role": str(item.get("role", "")),
                "content": _truncate_text(item.get("content", ""), max_chars=220),
                "score": item.get("score", 0.0),
            }
            for item in retrieved[:4]
            if isinstance(item, dict)
        ]

    task_history = memory.get("task_history")
    if isinstance(task_history, list):
        compact["task_history"] = _compact_task_results(
            [item for item in task_history if isinstance(item, dict)],
            max_items=3,
        )

    return compact


def _is_conversational_prompt(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True

    task_intent_tokens = [
        "search",
        "find",
        "latest",
        "news",
        "weather",
        "price",
        "calculate",
        "compute",
        "solve",
        "python",
        "script",
        "code",
        "read file",
        "open file",
    ]
    if any(token in lowered for token in task_intent_tokens):
        return False

    if re.search(r"\d\s*[\+\-\*/\^%]\s*\d", lowered):
        return False

    conversational_tokens = [
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "wassup",
        "whats up",
        "what's up",
        "how are you",
        "what's my name",
        "what is my name",
        "do you remember my name",
        "thanks",
        "thank you",
    ]
    return any(token in lowered for token in conversational_tokens) or len(lowered.split()) <= 4


class GroqClient:
    """Async-native Groq client with retry + synchronous compatibility wrappers."""

    def __init__(
        self,
        api_key: str | None = None,
        max_retries: int | None = None,
        base_retry_delay_seconds: float | None = None,
        max_retry_delay_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key or SETTINGS.groq_api_key
        self.max_retries = max(0, int(max_retries if max_retries is not None else SETTINGS.groq_max_retries))
        self.base_retry_delay_seconds = max(
            0.1,
            float(
                base_retry_delay_seconds
                if base_retry_delay_seconds is not None
                else SETTINGS.groq_retry_base_delay_seconds
            ),
        )
        self.max_retry_delay_seconds = max(
            self.base_retry_delay_seconds,
            float(
                max_retry_delay_seconds
                if max_retry_delay_seconds is not None
                else SETTINGS.groq_retry_max_delay_seconds
            ),
        )
        self._client: Any | None = None

    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RuntimeError("Missing GROQ_API_KEY")

        try:
            from groq import AsyncGroq
        except ImportError as exc:
            raise RuntimeError("Missing Groq SDK. Install with: pip install groq") from exc

        self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> tuple[bool, str]:
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            if status_code == 429:
                return True, "rate_limited"
            if 500 <= status_code <= 599:
                return True, "provider_server_error"
            return False, f"http_{status_code}"

        message = str(exc).lower()
        retryable_terms = [
            "timed out",
            "timeout",
            "connection",
            "temporarily unavailable",
            "try again",
            "rate limit",
            "429",
        ]
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(term in message for term in retryable_terms):
            return True, "transient_network"

        return False, "non_retryable"

    async def _retryable_call(self, operation_name: str, call: Callable[[], Any]) -> Any:
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return await call()
            except Exception as exc:  # noqa: BLE001
                retryable, reason = self._is_retryable_exception(exc)
                if not retryable or attempt >= attempts:
                    status_code = getattr(exc, "status_code", None)
                    if status_code is not None:
                        raise RuntimeError(f"Groq API call failed ({status_code}): {exc}") from exc
                    raise RuntimeError(f"Groq API call failed: {exc}") from exc

                backoff = min(
                    self.max_retry_delay_seconds,
                    self.base_retry_delay_seconds * (2 ** (attempt - 1)),
                )
                jitter = random.uniform(0, min(0.25, backoff / 5))
                sleep_for = backoff + jitter
                LOGGER.warning(
                    "Groq %s retry %s/%s in %.2fs (%s)",
                    operation_name,
                    attempt,
                    attempts - 1,
                    sleep_for,
                    reason,
                )
                await asyncio.sleep(sleep_for)

    async def chat_async(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        if not self.api_key:
            raise RuntimeError("Missing GROQ_API_KEY")

        client = self._get_client()
        completion = await self._retryable_call(
            "chat",
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_completion_tokens=max_tokens,
                top_p=1,
                stream=False,
                stop=None,
            ),
        )

        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise RuntimeError("Groq response had no choices")

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "") if message is not None else ""
        text = str(content or "").strip()
        if not text:
            raise RuntimeError("Groq response content was empty")
        return text

    async def tool_call_async(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        tools: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> dict[str, Any] | None:
        if not self.api_key:
            raise RuntimeError("Missing GROQ_API_KEY")

        client = self._get_client()
        completion = await self._retryable_call(
            "tool_call",
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_completion_tokens=max_tokens,
                top_p=1,
                stream=False,
                stop=None,
            ),
        )

        choices = getattr(completion, "choices", None) or []
        if not choices:
            return None

        message = getattr(choices[0], "message", None)
        if message is None:
            return None

        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return None

        first_tool_call = tool_calls[0]
        function_obj = getattr(first_tool_call, "function", None)
        function_name = str(getattr(function_obj, "name", "") or "").strip()
        arguments_raw = str(getattr(function_obj, "arguments", "") or "")
        arguments = _safe_json_object(arguments_raw)

        if not function_name:
            return None

        return {
            "name": function_name,
            "arguments": arguments,
            "id": str(getattr(first_tool_call, "id", "") or ""),
        }

    # Sync compatibility wrappers used by the existing non-async workflow class.
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        return _run_async_blocking(
            self.chat_async(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

    def tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        tools: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> dict[str, Any] | None:
        return _run_async_blocking(
            self.tool_call_async(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )


class MemoryAgent:
    def __init__(self, recent_limit: int | None = None) -> None:
        self._recent_limit = max(10, int(recent_limit if recent_limit is not None else SETTINGS.memory_recent_chat_limit))
        self._state: dict[str, Any] = {
            "chat_history": [],
            "chat_archive": [],
        }

    def load_snapshot(self, snapshot: dict[str, Any] | None) -> None:
        if isinstance(snapshot, dict):
            self._state = dict(snapshot)
        else:
            self._state = {}

        if not isinstance(self._state.get("chat_history"), list):
            self._state["chat_history"] = []
        if not isinstance(self._state.get("chat_archive"), list):
            self._state["chat_archive"] = []

    def write(self, key: str, value: Any) -> None:
        self._state[key] = value

    def append(self, key: str, value: Any) -> None:
        current = self._state.get(key)
        if not isinstance(current, list):
            current = []
        current.append(value)
        self._state[key] = current

    def read(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def append_chat_message(self, role: str, content: str) -> None:
        entry = {"role": role, "content": content}

        chat_history = self.read("chat_history", [])
        if not isinstance(chat_history, list):
            chat_history = []
        chat_history.append(entry)
        if len(chat_history) > self._recent_limit:
            chat_history = chat_history[-self._recent_limit :]
        self.write("chat_history", chat_history)

        chat_archive = self.read("chat_archive", [])
        if not isinstance(chat_archive, list):
            chat_archive = []
        chat_archive.append({"role": role, "content": content, "vector": _text_vector(content)})
        self.write("chat_archive", chat_archive)

    def retrieve_chat_context(self, query: str, top_k: int = 5, min_score: float = 0.15) -> list[dict[str, Any]]:
        chat_archive = self.read("chat_archive", [])
        if not isinstance(chat_archive, list) or not chat_archive:
            return []

        query_vector = _text_vector(query)
        if not query_vector:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        normalized_query = query.strip().lower()

        for item in chat_archive:
            if not isinstance(item, dict):
                continue

            role = str(item.get("role", ""))
            content = str(item.get("content", ""))
            if role == "user" and content.strip().lower() == normalized_query:
                continue

            vector = item.get("vector", {})
            if not isinstance(vector, dict):
                continue
            score = _cosine_similarity(query_vector, {str(k): float(v) for k, v in vector.items()})
            if score >= min_score:
                scored.append((score, item))

        scored.sort(key=lambda value: value[0], reverse=True)
        if not scored:
            fallback = [
                item
                for item in chat_archive[-top_k:]
                if isinstance(item, dict)
                and not (
                    str(item.get("role", "")) == "user"
                    and str(item.get("content", "")).strip().lower() == normalized_query
                )
            ]
            return [
                {
                    "role": str(item.get("role", "")),
                    "content": str(item.get("content", "")),
                    "score": 0.0,
                }
                for item in fallback
            ]

        return [
            {
                "role": str(item.get("role", "")),
                "content": str(item.get("content", "")),
                "score": round(score, 4),
            }
            for score, item in scored[: max(1, int(top_k))]
        ]

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)


@dataclass
class PlannerAgent:
    groq: GroqClient
    model: str = SETTINGS.planner_model

    @staticmethod
    def _planning_function_schema() -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_plan",
                "description": "Submit an executable DAG plan for the user goal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "task": {"type": "string"},
                                    "depends_on": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["id", "task", "depends_on"],
                            },
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["tasks"],
                },
            },
        }

    @staticmethod
    def _replanning_function_schema() -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_replan",
                "description": "Submit an updated DAG for remaining tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "task": {"type": "string"},
                                    "depends_on": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["id", "task", "depends_on"],
                            },
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["tasks"],
                },
            },
        }

    async def plan_async(self, user_goal: str, memory: dict[str, Any] | None = None) -> dict[str, Any]:
        task_text = user_goal.strip() or "Respond to the user request"

        if _is_conversational_prompt(task_text):
            return {
                "tasks": [{"id": "t1", "task": task_text, "depends_on": []}],
                "reason": "Conversational fast-path planner output.",
            }

        if self.groq.available():
            try:
                tool_call = await self.groq.tool_call_async(
                    system_prompt=(
                        "You are the Planner Agent in a 5-agent workflow. Use function calling to submit a DAG plan. "
                        "Generate short, atomic tasks and valid dependencies."
                    ),
                    user_prompt=json.dumps(
                        {
                            "user_goal": user_goal,
                            "memory": _compact_memory_for_prompt(memory),
                            "max_tasks": 6,
                            "available_tools": get_tool_specs(),
                        },
                        ensure_ascii=False,
                    ),
                    model=self.model,
                    tools=[self._planning_function_schema()],
                    temperature=0.0,
                )
            except RuntimeError as exc:
                LOGGER.warning("Planner function-call failed; using fallback planner output: %s", exc)
                tool_call = None

            if tool_call and tool_call.get("name") == "submit_plan":
                args = tool_call.get("arguments", {})
                tasks = _normalize_dag_tasks(args.get("tasks", []), max_tasks=6)
                if tasks:
                    return {
                        "tasks": tasks,
                        "reason": str(args.get("reason", "Generated by native function calling.")),
                    }

        return {
            "tasks": [{"id": "t1", "task": task_text, "depends_on": []}],
            "reason": "Fallback planner output.",
        }

    async def replan_async(
        self,
        user_goal: str,
        completed_results: list[dict[str, Any]],
        remaining_tasks: list[dict[str, Any]],
        memory: dict[str, Any] | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        if not remaining_tasks:
            return {"tasks": [], "reason": "No remaining tasks to replan."}

        if not self.groq.available():
            return {"tasks": remaining_tasks, "reason": "Replanner fallback (Groq unavailable)."}

        try:
            tool_call = await self.groq.tool_call_async(
                system_prompt=(
                    "You are the Re-planner Agent. Use function calling to submit an updated DAG for remaining tasks only. "
                    "You may add, remove, or reorder tasks while keeping dependencies acyclic. "
                    "If evaluator feedback is provided, prioritize fixing that gap first."
                ),
                user_prompt=json.dumps(
                    {
                        "user_goal": user_goal,
                        "completed_results": _compact_task_results(completed_results, max_items=5),
                        "remaining_tasks": remaining_tasks,
                        "feedback": feedback or "",
                        "memory": _compact_memory_for_prompt(memory),
                        "available_tools": get_tool_specs(),
                    },
                    ensure_ascii=False,
                ),
                model=self.model,
                tools=[self._replanning_function_schema()],
                temperature=0.0,
            )
        except RuntimeError as exc:
            LOGGER.warning("Replanner function-call failed; using fallback remaining tasks: %s", exc)
            tool_call = None

        if tool_call and tool_call.get("name") == "submit_replan":
            args = tool_call.get("arguments", {})
            tasks = _normalize_dag_tasks(args.get("tasks", []), max_tasks=max(1, len(remaining_tasks) + 2))
            if tasks:
                return {
                    "tasks": tasks,
                    "reason": str(args.get("reason", "Re-planner adjusted the DAG.")),
                }

        return {
            "tasks": remaining_tasks,
            "reason": "Replanner fallback returned original remaining tasks.",
        }

    def plan(self, user_goal: str, memory: dict[str, Any] | None = None) -> dict[str, Any]:
        return _run_async_blocking(self.plan_async(user_goal=user_goal, memory=memory))

    def replan(
        self,
        user_goal: str,
        completed_results: list[dict[str, Any]],
        remaining_tasks: list[dict[str, Any]],
        memory: dict[str, Any] | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        return _run_async_blocking(
            self.replan_async(
                user_goal=user_goal,
                completed_results=completed_results,
                remaining_tasks=remaining_tasks,
                memory=memory,
                feedback=feedback,
            )
        )


@dataclass
class RouterAgent:
    groq: GroqClient
    model: str = SETTINGS.router_model

    @staticmethod
    def _build_tool_call_schema(tool_spec: dict[str, Any]) -> dict[str, Any]:
        input_schema = tool_spec.get("input_schema", {})
        properties: dict[str, Any] = {}
        required: list[str] = []

        if isinstance(input_schema, dict):
            for key, value in input_schema.items():
                properties[str(key)] = {"type": _schema_type_from_hint(value)}
                if "optional" not in str(value).lower():
                    required.append(str(key))

        return {
            "type": "function",
            "function": {
                "name": str(tool_spec.get("name", "")),
                "description": str(tool_spec.get("description", "")),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @staticmethod
    def _semantic_route(task: str) -> dict[str, Any]:
        """Lightweight semantic fallback classifier (token-vector similarity)."""
        prototypes = {
            "web_search": [
                "latest news and current events",
                "look up information online",
                "find real-time weather or prices",
            ],
            "calculator": [
                "solve arithmetic expression",
                "compute numeric result",
                "math calculation",
            ],
            "python_execute": [
                "run python code snippet",
                "write and execute script",
                "transform data with python",
            ],
            "file_reader": [
                "read local file content",
                "open project source file",
                "inspect markdown or json file",
            ],
            "llm_chat": [
                "general conversation",
                "explain concept",
                "answer question directly",
            ],
        }

        query_vec = _text_vector(task)
        best_tool = "llm_chat"
        best_score = -1.0

        for tool_name, examples in prototypes.items():
            example_vec = _text_vector(" ".join(examples))
            score = _cosine_similarity(query_vec, example_vec)
            if score > best_score:
                best_score = score
                best_tool = tool_name

        if best_tool == "web_search":
            return {
                "tool": "web_search",
                "tool_input": {"query": task, "max_results": 5},
                "reason": "Semantic router fallback selected web_search.",
            }
        if best_tool == "calculator":
            return {
                "tool": "calculator",
                "tool_input": {"expression": task.replace("^", "**")},
                "reason": "Semantic router fallback selected calculator.",
            }
        if best_tool == "python_execute":
            return {
                "tool": "python_execute",
                "tool_input": {"code": task},
                "reason": "Semantic router fallback selected python_execute.",
            }
        if best_tool == "file_reader":
            return {
                "tool": "file_reader",
                "tool_input": {"path": task},
                "reason": "Semantic router fallback selected file_reader.",
            }

        return {
            "tool": "llm_chat",
            "tool_input": {"prompt": task},
            "reason": "Semantic router fallback selected llm_chat.",
        }

    async def route_async(self, task: str, memory: dict[str, Any]) -> dict[str, Any]:
        if _is_conversational_prompt(task):
            return {
                "tool": "llm_chat",
                "tool_input": {"prompt": task},
                "reason": "Conversational fast-path route.",
            }

        tool_specs = get_tool_specs()
        tool_specs.append(
            {
                "name": "llm_chat",
                "description": "General conversation and natural-language response generation.",
                "input_schema": {"prompt": "string"},
            }
        )

        if self.groq.available():
            try:
                tool_call = await self.groq.tool_call_async(
                    system_prompt=(
                        "You are the Router Agent. Choose exactly one function call for the task. "
                        "Use the provided tool descriptions and memory context."
                    ),
                    user_prompt=json.dumps(
                        {
                            "task": task,
                            "memory": _compact_memory_for_prompt(memory),
                            "available_tools": tool_specs,
                        },
                        ensure_ascii=False,
                    ),
                    model=self.model,
                    tools=[self._build_tool_call_schema(spec) for spec in tool_specs],
                    temperature=0.0,
                )
            except RuntimeError as exc:
                LOGGER.warning("Router function-call failed; using semantic fallback: %s", exc)
                fallback = self._semantic_route(task)
                fallback["reason"] = f"Semantic router fallback after provider error: {exc}"
                return fallback

            valid_tools = {str(spec["name"]) for spec in tool_specs}
            if tool_call and str(tool_call.get("name", "")) in valid_tools:
                tool_name = str(tool_call["name"])
                tool_input = tool_call.get("arguments", {})
                if not isinstance(tool_input, dict):
                    tool_input = {}
                if tool_name == "llm_chat":
                    tool_input.setdefault("prompt", task)
                return {
                    "tool": tool_name,
                    "tool_input": tool_input,
                    "reason": "Tool selected by native function calling.",
                }

        return self._semantic_route(task)

    def route(self, task: str, memory: dict[str, Any]) -> dict[str, Any]:
        return _run_async_blocking(self.route_async(task=task, memory=memory))


@dataclass
class ExecutorAgent:
    groq: GroqClient
    model: str = SETTINGS.executor_model

    def _local_conversation_reply(self, prompt: str, memory: dict[str, Any] | None = None) -> str:
        memory_state = memory or {}
        user_profile = memory_state.get("user_profile", {}) if isinstance(memory_state, dict) else {}
        remembered_name = str(user_profile.get("name", "")).strip()
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return "I’m ready to help. Share your goal, and I’ll work through it step by step."

        if remembered_name:
            return (
                f"Understood, {remembered_name}. I can help with this request. "
                "Share any constraints or extra context, and I’ll proceed."
            )

        return "Understood. I can help with this request—share any constraints or extra context, and I’ll proceed."

    def _run_llm_chat(self, prompt: str, memory: dict[str, Any] | None = None) -> dict[str, Any]:
        memory_state = memory or {}
        user_profile = memory_state.get("user_profile", {}) if isinstance(memory_state, dict) else {}
        chat_history = memory_state.get("chat_history", []) if isinstance(memory_state, dict) else []
        retrieved_context = memory_state.get("retrieved_chat_context", []) if isinstance(memory_state, dict) else []
        if not isinstance(chat_history, list):
            chat_history = []
        if not isinstance(retrieved_context, list):
            retrieved_context = []

        lowered = prompt.lower().strip()
        remembered_name = str(user_profile.get("name", "")).strip()

        greeting_tokens = {
            "hi",
            "hello",
            "hey",
            "yo",
            "sup",
            "wassup",
            "what's up",
            "whats up",
        }
        if lowered in greeting_tokens:
            return {"ok": True, "response": "Hey back to you. How's it going?", "from_memory": True}

        if "how are you" in lowered:
            return {"ok": True, "response": "Doing well—thanks for asking. What should we work on?", "from_memory": True}

        intro_name_match = re.search(r"\bmy name is\s+([a-zA-Z][a-zA-Z\-\s']{0,40})", prompt, flags=re.IGNORECASE)
        if intro_name_match:
            introduced_name = intro_name_match.group(1).strip().split()[0]
            return {"ok": True, "response": f"Nice to meet you, {introduced_name}.", "from_memory": True}

        if re.search(r"\b(what('?s| is) my name|do you remember my name)\b", lowered) and remembered_name:
            return {"ok": True, "response": f"Your name is {remembered_name}.", "from_memory": True}

        if self.groq.available():
            try:
                response = self.groq.chat(
                    system_prompt=(
                        "You are a concise, helpful AI assistant. Use recent conversation and retrieved context when relevant. "
                        "If user profile includes a name and user asks for their name, answer directly."
                    ),
                    user_prompt=json.dumps(
                        {
                            "user_message": prompt,
                            "memory": {
                                "user_profile": user_profile,
                                "recent_chat_history": chat_history[-8:],
                                "retrieved_chat_context": retrieved_context[:6],
                            },
                        },
                        ensure_ascii=False,
                    ),
                    model=self.model,
                    temperature=0.3,
                )
                return {"ok": True, "response": response}
            except RuntimeError as exc:
                fallback = self._local_conversation_reply(prompt, memory=memory_state)
                return {"ok": True, "response": fallback, "fallback": True, "error": str(exc)}

        return {
            "ok": True,
            "response": self._local_conversation_reply(prompt, memory=memory_state),
            "fallback": True,
        }

    def _fallback_final_answer(self, task_results: list[dict[str, Any]]) -> str:
        if not task_results:
            return "I could not produce a result for your request."

        for item in reversed(task_results):
            route = item.get("route", {})
            tool_name = str(route.get("tool", ""))
            tool_output = item.get("tool_output", {})

            if tool_name == "llm_chat" and isinstance(tool_output, dict) and tool_output.get("ok"):
                response = str(tool_output.get("response", "")).strip()
                if response:
                    return response

            if tool_name == "calculator" and isinstance(tool_output, dict) and tool_output.get("ok"):
                return f"The result is {tool_output.get('result')}."

            if tool_name == "web_search" and isinstance(tool_output, dict) and tool_output.get("ok"):
                results = tool_output.get("results", [])
                if isinstance(results, list) and results:
                    lines = ["Here are the top results I found:"]
                    for index, result in enumerate(results[:5], start=1):
                        title = result.get("title", "Untitled")
                        lines.append(f"{index}. {title}")
                    return "\n".join(lines)
                return "I searched the web but did not find clear results."

            if tool_name == "python_execute" and isinstance(tool_output, dict) and tool_output.get("ok"):
                stdout = str(tool_output.get("stdout", "")).strip()
                if stdout:
                    return stdout
                return "Python code ran successfully."

            if tool_name == "file_reader" and isinstance(tool_output, dict) and tool_output.get("ok"):
                content = str(tool_output.get("content", "")).strip()
                if content:
                    preview = content[:500]
                    return preview if len(content) <= 500 else f"{preview}..."

        last_output = task_results[-1].get("tool_output", {})
        if isinstance(last_output, dict) and last_output.get("error"):
            return f"I could not complete the request: {last_output.get('error')}"
        return "I completed the workflow, but I could not generate a clear final answer."

    def execute(
        self,
        task: str,
        route: dict[str, Any],
        file_root: str = ".",
        memory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool = str(route.get("tool", "")).strip()
        tool_input = route.get("tool_input", {})

        if not isinstance(tool_input, dict):
            tool_input = {}

        if tool == "llm_chat":
            output = self._run_llm_chat(prompt=str(tool_input.get("prompt", task)), memory=memory)
        else:
            output = run_tool(tool, tool_input=tool_input, file_root=file_root)

        return {
            "task": task,
            "route": route,
            "tool_output": output,
        }

    def synthesize_final_answer(self, user_goal: str, task_results: list[dict[str, Any]], memory: dict[str, Any]) -> str:
        if task_results:
            last = task_results[-1]
            last_route = last.get("route", {})
            last_tool = str(last_route.get("tool", ""))
            last_output = last.get("tool_output", {})

            if last_tool == "llm_chat" and isinstance(last_output, dict) and last_output.get("ok"):
                response = str(last_output.get("response", "")).strip()
                if response:
                    return response

            if last_tool == "calculator" and isinstance(last_output, dict) and last_output.get("ok"):
                return f"The result is {last_output.get('result')}."

        if self.groq.available():
            try:
                system_prompt = (
                    "You are the final answer writer. Return only the direct answer to the user. "
                    "Do not mention planning, tools, routes, memory, or internal reasoning. "
                    "If multiple results exist, summarize them briefly in user-friendly language."
                )
                user_prompt = json.dumps(
                    {
                        "user_goal": user_goal,
                        "task_results": task_results,
                        "memory": memory,
                    },
                    ensure_ascii=False,
                )
                return self.groq.chat(system_prompt, user_prompt, model=self.model, temperature=0.2)
            except RuntimeError:
                pass

        return self._fallback_final_answer(task_results)


@dataclass
class EvaluatorAgent:
    groq: GroqClient
    model: str = SETTINGS.evaluator_model

    @staticmethod
    def _evaluation_function_schema() -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_evaluation",
                "description": "Submit pass/fail evaluation for final response quality.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["pass", "retry"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["status", "reason"],
                },
            },
        }

    async def evaluate_async(
        self,
        user_goal: str,
        plan: list[Any],
        task_results: list[dict[str, Any]],
        final_answer: str,
    ) -> dict[str, Any]:
        if _is_conversational_prompt(user_goal) and final_answer.strip():
            return {"status": "pass", "reason": "Conversational response accepted without evaluator model call."}

        if self.groq.available():
            try:
                tool_call = await self.groq.tool_call_async(
                    system_prompt=(
                        "You are the Evaluator Agent. Evaluate whether the final answer satisfies the user goal. "
                        "Use function calling to return status=pass or status=retry with a concise reason."
                    ),
                    user_prompt=json.dumps(
                        {
                            "user_goal": user_goal,
                            "plan": plan,
                            "task_results": _compact_task_results(task_results, max_items=5),
                            "final_answer": _truncate_text(final_answer, max_chars=420),
                            "available_tools": get_tool_specs(),
                        },
                        ensure_ascii=False,
                    ),
                    model=self.model,
                    tools=[self._evaluation_function_schema()],
                    temperature=0.0,
                )
            except RuntimeError as exc:
                LOGGER.warning("Evaluator function-call failed; using fallback evaluator: %s", exc)
                tool_call = None

            if tool_call and tool_call.get("name") == "submit_evaluation":
                args = tool_call.get("arguments", {})
                status = str(args.get("status", "")).strip().lower()
                if status in {"pass", "retry"}:
                    return {
                        "status": status,
                        "reason": str(args.get("reason", "")).strip(),
                    }

        if final_answer.strip():
            return {"status": "pass", "reason": "Fallback evaluator accepted non-empty answer."}
        return {"status": "retry", "reason": "Final answer is empty."}

    def evaluate(
        self,
        user_goal: str,
        plan: list[Any],
        task_results: list[dict[str, Any]],
        final_answer: str,
    ) -> dict[str, Any]:
        return _run_async_blocking(
            self.evaluate_async(
                user_goal=user_goal,
                plan=plan,
                task_results=task_results,
                final_answer=final_answer,
            )
        )
