from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
from uuid import uuid4

from agent_nodes import (
    EvaluatorAgent,
    ExecutorAgent,
    GroqClient,
    MemoryAgent,
    PlannerAgent,
    RouterAgent,
)
from config import get_settings, setup_logging

LOGGER = logging.getLogger(__name__)
SETTINGS = get_settings()

try:
    from langchain_core.runnables import RunnableLambda
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - validated at runtime
    RunnableLambda = None  # type: ignore[assignment]
    MemorySaver = None  # type: ignore[assignment]
    END = None  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]
    _LANGGRAPH_IMPORT_ERROR = exc


_CHECKPOINTER = MemorySaver() if MemorySaver is not None else None


class AgentState(TypedDict, total=False):
    session_id: str
    user_goal: str
    conversation_history: list[dict[str, str]]
    memory: dict[str, Any]
    plan_graph: list[dict[str, Any]]
    pending_tasks: list[dict[str, Any]]
    completed_task_ids: list[str]
    task_results: list[dict[str, Any]]
    current_task: dict[str, Any]
    current_route: dict[str, Any]
    current_execution: dict[str, Any]
    iterations: int
    max_iterations: int
    max_python_retries: int
    python_retry_count: int
    replan_requested: bool
    evaluator_feedback: str
    continue_execution: bool
    ready_to_finalize: bool
    retry_same_task: bool
    should_finish: bool
    final_answer: str
    evaluation: dict[str, Any]
    errors: list[dict[str, Any]]
    events: list[dict[str, Any]]


@dataclass
class WorkflowConfig:
    max_iterations: int = SETTINGS.max_iterations_default
    file_root: str = SETTINGS.default_file_root
    planner_model: str = SETTINGS.planner_model
    router_model: str = SETTINGS.router_model
    executor_model: str = SETTINGS.executor_model
    evaluator_model: str = SETTINGS.evaluator_model
    max_python_retries: int = 2


def _as_task_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


class AgenticWorkflow:
    def __init__(self, config: WorkflowConfig) -> None:
        if _LANGGRAPH_IMPORT_ERROR is not None or _CHECKPOINTER is None:
            raise RuntimeError(
                "LangGraph/LangChain packages are required for orchestration. "
                "Install with: pip install langgraph langchain langchain-core"
            ) from _LANGGRAPH_IMPORT_ERROR

        self.config = config
        self.checkpointer = _CHECKPOINTER

        groq = GroqClient()
        self.planner = PlannerAgent(groq=groq, model=config.planner_model)
        self.router = RouterAgent(groq=groq, model=config.router_model)
        self.executor = ExecutorAgent(groq=groq, model=config.executor_model)
        self.evaluator = EvaluatorAgent(groq=groq, model=config.evaluator_model)

        self.graph = self._build_graph()

    @staticmethod
    def _extract_user_profile_updates(message: str) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        name_match = re.search(r"\bmy name is\s+([a-zA-Z][a-zA-Z\-\s']{0,40})", message, flags=re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip().split()[0]
            updates["name"] = name
        return updates

    @staticmethod
    def _memory_agent(snapshot: dict[str, Any] | None) -> MemoryAgent:
        memory = MemoryAgent()
        memory.load_snapshot(snapshot if isinstance(snapshot, dict) else {})
        return memory

    @staticmethod
    def _select_ready_task(pending_tasks: list[dict[str, Any]], completed_ids: set[str]) -> dict[str, Any] | None:
        for task in pending_tasks:
            deps = set(str(dep) for dep in task.get("depends_on", []))
            if deps.issubset(completed_ids):
                return task
        return None

    def _build_graph(self):
        builder = StateGraph(AgentState)

        builder.add_node("planner", RunnableLambda(self._node_planner))
        builder.add_node("router", RunnableLambda(self._node_router))
        builder.add_node("executor", RunnableLambda(self._node_executor))
        builder.add_node("evaluator", RunnableLambda(self._node_evaluator))
        builder.add_node("finalize", RunnableLambda(self._node_finalize))

        builder.set_entry_point("planner")
        builder.add_edge("planner", "router")
        builder.add_edge("router", "executor")
        builder.add_conditional_edges(
            "executor",
            self._after_executor,
            {
                "router": "router",
                "evaluator": "evaluator",
            },
        )
        builder.add_conditional_edges(
            "evaluator",
            self._after_evaluator,
            {
                "planner": "planner",
                "router": "router",
                "finalize": "finalize",
            },
        )
        builder.add_edge("finalize", END)

        return builder.compile(checkpointer=self.checkpointer)

    def _node_planner(self, state: AgentState) -> AgentState:
        user_goal = str(state.get("user_goal", "")).strip()
        memory_agent = self._memory_agent(state.get("memory"))

        completed_ids = [str(item) for item in state.get("completed_task_ids", [])]
        completed_set = set(completed_ids)
        existing_pending = _as_task_list(state.get("pending_tasks", []))
        task_results = list(state.get("task_results", []))
        replan_requested = bool(state.get("replan_requested"))

        events: list[dict[str, Any]] = []
        plan_graph: list[dict[str, Any]] = []
        pending_tasks: list[dict[str, Any]] = []

        if replan_requested:
            evaluator_feedback = str(state.get("evaluator_feedback", "")).strip()
            remaining_tasks = existing_pending
            if not remaining_tasks:
                feedback_task = evaluator_feedback or f"Address unresolved issues for: {user_goal}"
                remaining_tasks = [{"id": f"retry_{int(state.get('iterations', 0)) + 1}", "task": feedback_task, "depends_on": []}]

            replan_payload = self.planner.replan(
                user_goal=user_goal,
                completed_results=task_results,
                remaining_tasks=remaining_tasks,
                memory=memory_agent.snapshot(),
                feedback=evaluator_feedback,
            )
            replanned = _as_task_list(replan_payload.get("tasks", []) if isinstance(replan_payload, dict) else [])
            filtered = [
                task
                for task in replanned
                if str(task.get("id", "")).strip()
                and str(task.get("task", "")).strip()
                and str(task.get("id", "")).strip() not in completed_set
            ]

            pending_tasks = filtered if filtered else remaining_tasks
            plan_graph = pending_tasks
            events.append(
                {
                    "type": "replan",
                    "reason": str(replan_payload.get("reason", "Dynamic replan requested."))
                    if isinstance(replan_payload, dict)
                    else "Dynamic replan requested.",
                    "plan": [str(task.get("task", "")) for task in pending_tasks],
                    "plan_graph": pending_tasks,
                }
            )
        else:
            plan_payload = self.planner.plan(user_goal=user_goal, memory=memory_agent.snapshot())
            proposed_plan = _as_task_list(plan_payload.get("tasks", []) if isinstance(plan_payload, dict) else [])
            proposed_plan = [
                task
                for task in proposed_plan
                if str(task.get("id", "")).strip() and str(task.get("task", "")).strip()
            ]

            if not proposed_plan:
                proposed_plan = [{"id": "t1", "task": user_goal or "Respond to the user request", "depends_on": []}]

            pending_tasks = proposed_plan
            plan_graph = proposed_plan
            completed_ids = []
            task_results = []
            events.append(
                {
                    "type": "plan",
                    "plan": [str(task.get("task", "")) for task in plan_graph],
                    "plan_graph": plan_graph,
                }
            )

        if not pending_tasks:
            return {
                "events": events,
                "plan_graph": plan_graph,
                "pending_tasks": pending_tasks,
                "task_results": task_results,
                "completed_task_ids": completed_ids,
                "replan_requested": False,
                "continue_execution": False,
                "ready_to_finalize": True,
                "should_finish": True,
                "errors": list(state.get("errors", [])) + [{"agent": "planner", "error": "No tasks available after planning."}],
            }

        return {
            "events": events,
            "plan_graph": plan_graph,
            "pending_tasks": pending_tasks,
            "task_results": task_results,
            "completed_task_ids": completed_ids,
            "replan_requested": False,
            "continue_execution": False,
            "ready_to_finalize": False,
            "retry_same_task": False,
            "should_finish": False,
            "memory": memory_agent.snapshot(),
        }

    def _node_router(self, state: AgentState) -> AgentState:
        pending_tasks = _as_task_list(state.get("pending_tasks", []))
        completed_set = {str(item) for item in state.get("completed_task_ids", [])}
        iterations = int(state.get("iterations", 0))
        max_iterations = int(state.get("max_iterations", self.config.max_iterations))
        errors = list(state.get("errors", []))

        if bool(state.get("should_finish")):
            return {"events": []}

        if iterations >= max_iterations:
            return {
                "events": [
                    {
                        "type": "plan",
                        "step": "Execution limit reached",
                        "reason": f"Stopped after {max_iterations} iterations.",
                    }
                ],
                "continue_execution": False,
                "ready_to_finalize": True,
                "should_finish": True,
            }

        if not pending_tasks:
            return {
                "events": [],
                "continue_execution": False,
                "ready_to_finalize": True,
                "should_finish": True,
            }

        current_task = self._select_ready_task(pending_tasks, completed_set)
        if current_task is None:
            errors.append({"agent": "router", "error": "Deadlock detected: no dependency-satisfied tasks."})
            return {
                "events": [
                    {
                        "type": "plan",
                        "step": "Deadlock detected",
                        "reason": "No dependency-satisfied tasks remain.",
                    }
                ],
                "errors": errors,
                "continue_execution": False,
                "ready_to_finalize": True,
                "should_finish": True,
            }

        task_text = str(current_task.get("task", "")).strip()
        memory_agent = self._memory_agent(state.get("memory"))
        route = self.router.route(task=task_text, memory=memory_agent.snapshot())

        return {
            "current_task": current_task,
            "current_route": route,
            "events": [
                {
                    "type": "route",
                    "task_index": iterations + 1,
                    "task_id": str(current_task.get("id", "")),
                    "task": task_text,
                    "route": route,
                }
            ],
        }

    def _node_executor(self, state: AgentState) -> AgentState:
        current_task = state.get("current_task")
        current_route = state.get("current_route")
        pending_tasks = _as_task_list(state.get("pending_tasks", []))
        completed_ids = [str(item) for item in state.get("completed_task_ids", [])]
        task_results = list(state.get("task_results", []))
        errors = list(state.get("errors", []))

        if not isinstance(current_task, dict) or not isinstance(current_route, dict):
            errors.append({"agent": "executor", "error": "Missing task or route."})
            return {
                "events": [{"type": "error", "error": "Executor received invalid state."}],
                "errors": errors,
                "retry_same_task": False,
                "continue_execution": False,
                "ready_to_finalize": True,
                "should_finish": True,
            }

        task_text = str(current_task.get("task", "")).strip()
        task_id = str(current_task.get("id", "")).strip()
        iterations = int(state.get("iterations", 0)) + 1
        max_python_retries = int(state.get("max_python_retries", self.config.max_python_retries))
        python_retry_count = int(state.get("python_retry_count", 0))

        memory_agent = self._memory_agent(state.get("memory"))
        execution = self.executor.execute(
            task=task_text,
            route=current_route,
            file_root=self.config.file_root,
            memory=memory_agent.snapshot(),
        )

        route_tool = str(current_route.get("tool", "")).strip()
        tool_output = execution.get("tool_output", {})
        tool_ok = not (isinstance(tool_output, dict) and tool_output.get("ok") is False)
        python_failed = route_tool == "python_execute" and not tool_ok

        task_results.append(execution)
        memory_agent.append("task_history", execution)
        memory_agent.write(f"task_{iterations}", execution)

        events: list[dict[str, Any]] = [
            {
                "type": "execution",
                "task_index": iterations,
                "task_id": task_id,
                "execution": execution,
            }
        ]

        if not tool_ok:
            errors.append(
                {
                    "agent": "executor",
                    "task_id": task_id,
                    "tool": route_tool,
                    "error": tool_output.get("error", "Unknown execution failure") if isinstance(tool_output, dict) else "Unknown execution failure",
                }
            )

        if python_failed and python_retry_count < max_python_retries:
            errors.append(
                {
                    "agent": "executor",
                    "task_id": task_id,
                    "tool": "python_execute",
                    "error": f"Python execution failed. Retrying route ({python_retry_count + 1}/{max_python_retries}).",
                }
            )
            memory_agent.append(
                "execution_errors",
                {
                    "task_id": task_id,
                    "task": task_text,
                    "tool": route_tool,
                    "tool_output": tool_output,
                },
            )
            return {
                "events": events,
                "current_execution": execution,
                "task_results": task_results,
                "iterations": iterations,
                "errors": errors,
                "python_retry_count": python_retry_count + 1,
                "retry_same_task": True,
                "memory": memory_agent.snapshot(),
                "continue_execution": False,
                "ready_to_finalize": False,
                "should_finish": False,
            }

        remaining = [task for task in pending_tasks if str(task.get("id", "")).strip() != task_id]
        if task_id and task_id not in completed_ids:
            completed_ids.append(task_id)

        return {
            "events": events,
            "current_execution": execution,
            "pending_tasks": remaining,
            "completed_task_ids": completed_ids,
            "task_results": task_results,
            "iterations": iterations,
            "errors": errors,
            "python_retry_count": 0,
            "retry_same_task": False,
            "memory": memory_agent.snapshot(),
            "continue_execution": False,
            "ready_to_finalize": False,
            "should_finish": False,
        }

    def _node_evaluator(self, state: AgentState) -> AgentState:
        pending_tasks = _as_task_list(state.get("pending_tasks", []))
        task_results = list(state.get("task_results", []))
        plan_graph = _as_task_list(state.get("plan_graph", []))
        user_goal = str(state.get("user_goal", "")).strip()
        iterations = int(state.get("iterations", 0))
        max_iterations = int(state.get("max_iterations", self.config.max_iterations))
        errors = list(state.get("errors", []))
        should_finish = bool(state.get("should_finish"))

        if bool(state.get("retry_same_task")) and not should_finish:
            return {
                "events": [],
                "continue_execution": True,
                "ready_to_finalize": False,
                "replan_requested": False,
            }

        current_execution = state.get("current_execution")
        last_failed = False
        if isinstance(current_execution, dict):
            tool_output = current_execution.get("tool_output", {})
            if isinstance(tool_output, dict) and tool_output.get("ok") is False:
                last_failed = True

        evaluation_payload: dict[str, Any]
        if pending_tasks and not last_failed and iterations < max_iterations and not should_finish:
            evaluation_payload = {
                "status": "pass",
                "reason": "Step accepted; continue with remaining planned tasks.",
            }
        else:
            memory_snapshot = state.get("memory", {}) if isinstance(state.get("memory"), dict) else {}
            answer_draft = self.executor.synthesize_final_answer(
                user_goal=user_goal,
                task_results=task_results,
                memory=memory_snapshot,
            )
            evaluation_payload = self.evaluator.evaluate(
                user_goal=user_goal,
                plan=[str(task.get("task", "")) for task in plan_graph],
                task_results=task_results,
                final_answer=answer_draft,
            )

        status = str(evaluation_payload.get("status", "pass")).strip().lower()
        reason = str(evaluation_payload.get("reason", "")).strip()

        replan_requested = False
        continue_execution = False
        ready_to_finalize = False
        evaluator_feedback = ""

        if status == "retry" and iterations < max_iterations and not should_finish:
            replan_requested = True
            evaluator_feedback = reason or "Evaluator requested retry."
            if not pending_tasks:
                pending_tasks = [
                    {
                        "id": f"retry_{iterations + 1}",
                        "task": f"Address evaluator feedback: {evaluator_feedback}",
                        "depends_on": [],
                    }
                ]
        elif pending_tasks and iterations < max_iterations and not should_finish:
            continue_execution = True
        else:
            ready_to_finalize = True

        if iterations >= max_iterations and pending_tasks:
            errors.append(
                {
                    "agent": "evaluator",
                    "error": f"Max iterations ({max_iterations}) reached before completing all tasks.",
                }
            )
            continue_execution = False
            replan_requested = False
            ready_to_finalize = True
            should_finish = True

        return {
            "events": [{"type": "evaluation", "evaluation": evaluation_payload}],
            "evaluation": evaluation_payload,
            "pending_tasks": pending_tasks,
            "replan_requested": replan_requested,
            "evaluator_feedback": evaluator_feedback,
            "continue_execution": continue_execution,
            "ready_to_finalize": ready_to_finalize,
            "should_finish": should_finish,
            "errors": errors,
        }

    def _node_finalize(self, state: AgentState) -> AgentState:
        user_goal = str(state.get("user_goal", "")).strip()
        plan_graph = _as_task_list(state.get("plan_graph", []))
        task_results = list(state.get("task_results", []))
        errors = list(state.get("errors", []))

        memory_agent = self._memory_agent(state.get("memory"))
        memory_snapshot = memory_agent.snapshot()

        final_answer = str(state.get("final_answer", "")).strip()
        if not final_answer:
            final_answer = self.executor.synthesize_final_answer(
                user_goal=user_goal,
                task_results=task_results,
                memory=memory_snapshot,
            )

        evaluation = state.get("evaluation") if isinstance(state.get("evaluation"), dict) else {}
        if not evaluation:
            evaluation = self.evaluator.evaluate(
                user_goal=user_goal,
                plan=[str(task.get("task", "")) for task in plan_graph],
                task_results=task_results,
                final_answer=final_answer,
            )

        memory_agent.append_chat_message("assistant", final_answer)
        conversation_history = list(state.get("conversation_history", []))
        conversation_history.append({"role": "assistant", "content": final_answer})

        result = {
            "goal": user_goal,
            "plan": [str(task.get("task", "")) for task in plan_graph],
            "plan_graph": plan_graph,
            "task_results": task_results,
            "errors": errors,
            "memory": memory_agent.snapshot(),
            "evaluation": evaluation,
            "final_answer": final_answer,
        }

        return {
            "events": [{"type": "final", "result": result}],
            "final_answer": final_answer,
            "evaluation": evaluation,
            "memory": memory_agent.snapshot(),
            "conversation_history": conversation_history,
            "should_finish": True,
        }

    @staticmethod
    def _after_executor(state: AgentState) -> Literal["router", "evaluator"]:
        if state.get("retry_same_task") and not state.get("should_finish"):
            return "router"
        return "evaluator"

    @staticmethod
    def _after_evaluator(state: AgentState) -> Literal["planner", "router", "finalize"]:
        if state.get("replan_requested") and not state.get("should_finish"):
            return "planner"
        if state.get("continue_execution") and not state.get("should_finish"):
            return "router"
        return "finalize"

    def _get_checkpoint_state(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            snapshot = self.graph.get_state(config)
        except Exception:  # noqa: BLE001
            return {}

        values = getattr(snapshot, "values", None)
        return values if isinstance(values, dict) else {}

    def run_stream(
        self,
        user_goal: str,
        session_id: str | None = None,
    ):
        active_session_id = session_id or str(uuid4())
        config = {"configurable": {"thread_id": active_session_id}}

        previous_state = self._get_checkpoint_state(config)
        base_memory = previous_state.get("memory", {}) if isinstance(previous_state.get("memory"), dict) else {}

        memory_agent = self._memory_agent(base_memory)
        memory_agent.append_chat_message("user", user_goal)

        user_profile = memory_agent.read("user_profile", {})
        if not isinstance(user_profile, dict):
            user_profile = {}
        updates = self._extract_user_profile_updates(user_goal)
        if updates:
            user_profile.update(updates)
            memory_agent.write("user_profile", user_profile)

        retrieved_context = memory_agent.retrieve_chat_context(
            user_goal,
            top_k=max(1, int(SETTINGS.memory_retrieval_k)),
        )
        memory_agent.write("retrieved_chat_context", retrieved_context)

        conversation_history = previous_state.get("conversation_history", [])
        if not isinstance(conversation_history, list):
            conversation_history = []
        conversation_history = list(conversation_history)
        conversation_history.append({"role": "user", "content": user_goal})

        initial_state: AgentState = {
            "session_id": active_session_id,
            "user_goal": user_goal,
            "conversation_history": conversation_history,
            "memory": memory_agent.snapshot(),
            "plan_graph": [],
            "pending_tasks": [],
            "completed_task_ids": [],
            "task_results": [],
            "current_task": {},
            "current_route": {},
            "current_execution": {},
            "iterations": 0,
            "max_iterations": self.config.max_iterations,
            "max_python_retries": self.config.max_python_retries,
            "python_retry_count": 0,
            "replan_requested": False,
            "evaluator_feedback": "",
            "continue_execution": False,
            "ready_to_finalize": False,
            "retry_same_task": False,
            "should_finish": False,
            "errors": [],
            "events": [],
        }

        produced_final = False
        for update in self.graph.stream(initial_state, config=config, stream_mode="updates"):
            for node_output in update.values():
                if not isinstance(node_output, dict):
                    continue
                events = node_output.get("events", [])
                if not isinstance(events, list):
                    continue
                for event in events:
                    if isinstance(event, dict):
                        yield event
                        if event.get("type") == "final":
                            produced_final = True

        if not produced_final:
            raise RuntimeError("Workflow did not produce final output.")

    def run(
        self,
        user_goal: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        final: dict[str, Any] | None = None
        for event in self.run_stream(user_goal, session_id=session_id):
            if event.get("type") == "final":
                payload = event.get("result")
                if isinstance(payload, dict):
                    final = payload

        if final is None:
            raise RuntimeError("Workflow did not produce final output.")
        return final


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic workflow with LangGraph")
    parser.add_argument("--goal", required=True, help="User goal to process")
    parser.add_argument("--max-iterations", type=int, default=SETTINGS.max_iterations_default, help="Maximum tasks to execute")
    parser.add_argument("--file-root", default=SETTINGS.default_file_root, help="Root path for file_reader tool")
    parser.add_argument("--session-id", default=None, help="Optional session identifier for LangGraph checkpointing")
    parser.add_argument("--json", action="store_true", help="Print full JSON output")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = _parse_args()

    workflow = AgenticWorkflow(
        WorkflowConfig(max_iterations=args.max_iterations, file_root=args.file_root)
    )
    result = workflow.run(args.goal, session_id=args.session_id)

    if args.json:
        LOGGER.info(json.dumps(result, ensure_ascii=False, indent=2))
        return

    LOGGER.info("=== PLAN ===")
    for index, task in enumerate(result.get("plan", []), start=1):
        LOGGER.info("%s. %s", index, task)

    LOGGER.info("=== FINAL ANSWER ===")
    LOGGER.info("%s", result.get("final_answer", ""))

    LOGGER.info("=== EVALUATION ===")
    LOGGER.info(json.dumps(result.get("evaluation", {}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
