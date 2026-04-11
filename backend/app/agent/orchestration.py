"""Planner -> router -> tools orchestration for chat requests."""

from __future__ import annotations

import json
import inspect
import logging
import re
from types import UnionType
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Union, get_args, get_origin
from uuid import uuid4

from langchain_groq import ChatGroq
from sqlalchemy.orm import Session

from app.agent.state import (
    AgentState,
    InputTriggerType,
    PlannerDecision,
    PlannerOutput,
    ToolExecutionResult,
    ToolRequirement,
    UserInput,
    ResponseContent,
    ActionCard,
    PendingApproval,
    StateBuilder,
)
from app.agent.tools.calendar_tools import create_calendar_tools
from app.agent.tools.email_tools import create_email_tools
from app.agent.tools.planning_tools import create_planning_tools
from app.agent.tools.search_tools import create_search_tools
from app.agent.tools.task_tools import create_task_tools
from app.cache.config import get_redis
from app.core.config import settings
from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.db.models import Approval, User
from app.services.conversation_memory import ConversationMemoryService

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Lightweight orchestrator implementing planner, router and tool execution."""

    _LATEST_EMAIL_ALIASES = {
        "latest",
        "recent",
        "newest",
        "last",
        "latest email",
        "most recent",
        "most recent email",
        "last email",
    }
    _URGENT_EMAIL_ALIASES = {
        "urgent",
        "most urgent",
        "critical",
        "important",
        "priority",
    }

    def __init__(self, db: Session):
        self.db = db
        self._planner_llm = None
        self._assistant_llm = None
        if settings.groq_api_key:
            self._planner_llm = ChatGroq(
                model=settings.groq_planner_model,
                temperature=0,
                api_key=settings.groq_api_key,
            )
            self._assistant_llm = ChatGroq(
                model=settings.groq_execution_model,
                temperature=settings.llm_temperature,
                api_key=settings.groq_api_key,
            )

    def execute_chat(
        self,
        user: User,
        message: str,
        session_id: str | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> AgentState:
        start = perf_counter()
        trace_id = get_trace_id() or str(uuid4())
        resolved_session_id = session_id or str(uuid4())
        memory_service = ConversationMemoryService(self.db)
        runtime_memory = memory_service.get_runtime_context(
            user_id=user.id,
            session_id=resolved_session_id,
            query=message,
        )
        user_context = self._build_user_context(
            user,
            conversation_context=runtime_memory.to_dict(),
            external_context=external_context,
        )
        state = StateBuilder.create_initial_state(
            user_id=user.id,
            trace_id=trace_id,
            session_id=resolved_session_id,
            user_input=UserInput(
                type=InputTriggerType.USER_CHAT,
                content=message,
                context={
                    "message_type": "text",
                    "user_context": user_context,
                },
            ),
        )

        try:
            self._run_planner(state, user_context=user_context)
            self._run_router(state)
            self._run_tools(state, user)
            self._build_response(state)
            self._persist_state(state)
            self._persist_conversation_turns(
                memory_service=memory_service,
                user=user,
                state=state,
                user_message=message,
            )

            state.metadata.end_time = datetime.utcnow()
            state.metadata.execution_time_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("orchestration.execute_chat", "success", state.metadata.execution_time_ms)
            return state

        except Exception as exc:
            state.metadata.errors.append({"message": str(exc), "timestamp": datetime.utcnow().isoformat()})
            state.metadata.end_time = datetime.utcnow()
            state.metadata.execution_time_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("orchestration.execute_chat", "error", state.metadata.execution_time_ms)
            logger.error("orchestration.execute_chat.error", extra={"trace_id": trace_id, "user_id": user.id}, exc_info=True)
            state.response = ResponseContent(message="I could not complete that request right now. Please try again.")
            return state

    def _run_planner(self, state: AgentState, user_context: dict[str, Any]) -> None:
        if self._run_planner_with_llm(state, user_context=user_context):
            return

        logger.warning(
            "orchestration.planner.llm_failed_no_fallback",
            extra={"trace_id": state.trace_id, "user_id": state.user_id},
        )
        state.plan = PlannerOutput(
            action_type=PlannerDecision.CHAT_RESPONSE,
            reasoning="Unable to determine intent from LLM. Responding conversationally.",
            tools_required=[],
            requires_approval=False,
            confidence=0.5,
            estimated_duration_seconds=1.0,
        )
        state.current_node = "planner"
        state.metadata.nodes_executed.append("planner")

    def _run_planner_with_llm(self, state: AgentState, user_context: dict[str, Any]) -> bool:
        if not self._planner_llm:
            return False

        supported_actions = [decision.value for decision in PlannerDecision]
        supported_tools = [
            "fetch_latest_emails",
            "summarize_inbox",
            "check_urgent_emails",
            "generate_draft_reply",
            "list_tasks",
            "create_task",
            "update_task",
            "move_task",
            "list_free_slots",
            "find_best_slot",
            "create_event",
            "generate_daily_plan",
            "serp_search",
            "summarize_search_result",
            "save_search_note",
            "list_search_notes",
        ]

        prompt = (
            f"You are an expert intent planner for {settings.assistant_name}. Your task is to understand the semantic intent "
            "of user messages and determine the best action and tools to execute.\n\n"
            "INTENT UNDERSTANDING (not keyword matching):\n"
            "- User wants to review/send emails: INTENT = email operations\n"
            "- User wants to check calendar/see free slots/schedule meeting: INTENT = calendar operations\n"
            "- User wants to create/update/complete tasks: INTENT = task management\n"
            "- User wants web research, to search Google, or to summarize/extract info from a URL: INTENT = web search operations\n"
            "- User needs help planning/organizing: INTENT = planning\n"
            "- Otherwise: INTENT = conversational response\n\n"
            "Return ONLY valid JSON with this schema:\n"
            "{\n"
            "  \"action_type\": string (one of the allowed values),\n"
            "  \"reasoning\": string (explain your semantic understanding),\n"
            "  \"requires_approval\": boolean (true if action modifies data),\n"
            "  \"approval_reason\": string|null,\n"
            "  \"confidence\": number (0-1, 1=certain),\n"
            "  \"tools_required\": [{\"tool_name\": string, \"parameters\": object}]\n"
            "}\n\n"
            f"Allowed action_type values: {supported_actions}\n"
            f"Allowed tool_name values: {supported_tools}\n\n"
            "RULES:\n"
            "1. Base decisions on semantic intent, not keywords\n"
            "2. If tools_required is empty, set action_type=chat_response\n"
            "3. Always include a reasoning field explaining what the user is trying to accomplish\n"
            "4. Return valid JSON even if you're unsure - use confidence field\n"
            "5. If message is unclear, use chat_response action\n"
            "6. If user is asking for advice/suggestions/brainstorming (no explicit data fetch or update request), use chat_response\n\n"
            f"User profile context (JSON): {json.dumps(user_context, default=str)}\n\n"
            f"User message: {state.user_input.content or ''}"
        )

        try:
            result = self._planner_llm.invoke(prompt)
            raw_content = str(result.content).strip()
            data = self._extract_json(raw_content)

            action_type = str(data.get("action_type", PlannerDecision.CHAT_RESPONSE.value)).lower()
            if action_type not in supported_actions:
                action_type = PlannerDecision.CHAT_RESPONSE.value

            action_enum = PlannerDecision(action_type)
            reasoning = str(data.get("reasoning", "LLM intent classification"))
            tools_required: list[ToolRequirement] = []

            for entry in data.get("tools_required", []):
                tool_name = str(entry.get("tool_name", "")).strip()
                if tool_name not in supported_tools:
                    continue
                tools_required.append(
                    ToolRequirement(
                        tool_name=tool_name,
                        parameters=entry.get("parameters") or {},
                    )
                )

            if action_enum == PlannerDecision.CHAT_RESPONSE and not tools_required:
                calendar_follow_up_params = self._infer_create_event_follow_up_params(
                    user_message=state.user_input.content or "",
                    user_context=user_context,
                )
                if calendar_follow_up_params is not None:
                    action_enum = PlannerDecision.CREATE_EVENT
                    tools_required = [
                        ToolRequirement(
                            tool_name="create_event",
                            parameters=calendar_follow_up_params,
                        )
                    ]
                    reasoning = f"{reasoning} Follow-up interpreted as calendar event creation continuation."

            if self._is_explicit_new_email_request(state.user_input.content or ""):
                action_enum = PlannerDecision.CHAT_RESPONSE
                tools_required = []
                reasoning = f"{reasoning} Direct outbound email compose request interpreted as chat drafting flow."

            state.plan = PlannerOutput(
                action_type=action_enum,
                reasoning=reasoning,
                tools_required=tools_required,
                requires_approval=bool(data.get("requires_approval", False)),
                approval_reason=data.get("approval_reason"),
                confidence=float(data.get("confidence", 0.75)),
                estimated_duration_seconds=2.0,
            )
            state.current_node = "planner"
            state.metadata.nodes_executed.append("planner")
            return True
        except Exception:
            logger.warning(
                "orchestration.planner.llm_fallback",
                extra={"trace_id": state.trace_id, "user_id": state.user_id},
                exc_info=True,
            )
            return False

    @staticmethod
    def _extract_json(raw_content: str) -> dict[str, Any]:
        if raw_content.startswith("```"):
            lines = raw_content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_content = "\n".join(lines).strip()
        return json.loads(raw_content)


    def _run_router(self, state: AgentState) -> None:
        tool_names = [tool.tool_name for tool in (state.plan.tools_required if state.plan else [])]
        state.router_decision = tool_names
        state.current_node = "router"
        state.metadata.nodes_executed.append("router")

    def _run_tools(self, state: AgentState, user: User) -> None:
        tools = {}
        tools.update(create_email_tools(self.db))
        tools.update(create_task_tools(self.db))
        tools.update(create_calendar_tools(self.db))
        tools.update(create_search_tools(self.db))
        tools.update(create_planning_tools(self.db))

        for requirement in state.plan.tools_required if state.plan else []:
            start = perf_counter()
            tool_name = requirement.tool_name
            params = dict(requirement.parameters)

            if tool_name == "generate_draft_reply":
                params = self._normalize_generate_draft_params(params=params, tools=tools, user=user)

            if str(params.get("email_id") or "").strip().lower() in self._LATEST_EMAIL_ALIASES:
                latest_raw = tools["fetch_latest_emails"](user_id=user.id, limit=1)
                latest = self._normalize_tool_result("fetch_latest_emails", latest_raw)
                emails = latest.get("emails", []) if isinstance(latest.get("emails", []), list) else []
                if latest.get("status") != "success" or not emails:
                    result = {"status": "failed", "error": "No recent emails found"}
                    if latest.get("status") != "success" and latest.get("error"):
                        result["error"] = latest.get("error")
                    state.tool_results.append(
                        ToolExecutionResult(
                            tool_name=tool_name,
                            success=False,
                            result=result,
                            error=result.get("error"),
                            execution_time_ms=(perf_counter() - start) * 1000,
                        )
                    )
                    continue
                params["email_id"] = emails[0]["id"]

            try:
                tool_fn = tools.get(tool_name)
                if not tool_fn:
                    result = {"status": "failed", "error": f"Unknown tool: {tool_name}"}
                else:
                    enriched_params = self._enrich_tool_params(
                        tool_name=tool_name,
                        params=params,
                        user_message=state.user_input.content,
                        conversation_context=((state.user_input.context or {}).get("user_context") or {}).get("conversation_context"),
                    )
                    coerced_params = self._coerce_tool_params(tool_fn=tool_fn, params=enriched_params)
                    safe_params = self._sanitize_tool_params(tool_fn=tool_fn, params=coerced_params)
                    missing_required = self._find_missing_required_params(tool_fn=tool_fn, params=safe_params)
                    if missing_required:
                        result = {
                            "status": "failed",
                            "error_code": "missing_required_parameters",
                            "missing_parameters": missing_required,
                            "error": self._format_missing_params_error(tool_name=tool_name, missing_params=missing_required),
                        }
                    else:
                        raw_result = tool_fn(user_id=user.id, **safe_params)
                        result = self._normalize_tool_result(tool_name, raw_result)

                success = result.get("status") == "success"
                error_text = result.get("error")
                state.tool_results.append(
                    ToolExecutionResult(
                        tool_name=tool_name,
                        success=success,
                        result=result,
                        error=error_text,
                        execution_time_ms=(perf_counter() - start) * 1000,
                    )
                )

                self._capture_pending_approval(state, user, tool_name, result)

            except Exception as exc:
                state.tool_results.append(
                    ToolExecutionResult(
                        tool_name=tool_name,
                        success=False,
                        result=None,
                        error=str(exc),
                        execution_time_ms=(perf_counter() - start) * 1000,
                    )
                )

        state.current_node = "tools"
        state.metadata.nodes_executed.append("tools")

    @staticmethod
    def _sanitize_tool_params(tool_fn: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Drop unexpected parameters before invoking a tool function."""
        if not isinstance(params, dict):
            return {}

        # user_id is always injected by the orchestrator call site; never forward planner-provided values.
        sanitized_params = {key: value for key, value in params.items() if key != "user_id"}

        try:
            signature = inspect.signature(tool_fn)
        except (TypeError, ValueError):
            return sanitized_params

        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return sanitized_params

        allowed_keys = {
            name
            for name, param in signature.parameters.items()
            if name != "user_id"
            and param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return {key: value for key, value in sanitized_params.items() if key in allowed_keys}

    @staticmethod
    def _coerce_tool_params(tool_fn: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Coerce planner-provided params into tool signature-compatible values."""
        if not isinstance(params, dict):
            return {}

        try:
            signature = inspect.signature(tool_fn)
        except (TypeError, ValueError):
            return dict(params)

        coerced = dict(params)
        for name, param in signature.parameters.items():
            if name == "user_id" or name not in coerced:
                continue

            value = coerced.get(name)
            annotation = param.annotation
            normalized_value = AgentOrchestrator._coerce_value_for_annotation(annotation=annotation, value=value)
            coerced[name] = normalized_value

        return coerced

    @staticmethod
    def _coerce_value_for_annotation(annotation: Any, value: Any) -> Any:
        if value is None or annotation is inspect._empty:
            return value

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is None:
            target = annotation
            if target is bool:
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "1", "yes", "y"}:
                        return True
                    if lowered in {"false", "0", "no", "n"}:
                        return False
                if isinstance(value, (int, float)):
                    return bool(value)
                return value

            if target is int:
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                if isinstance(value, str):
                    text = value.strip()
                    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
                        return int(text)
                return value

            if target is float:
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return float(value.strip())
                    except Exception:
                        return value
                return value

            if target is str:
                return str(value).strip() if not isinstance(value, str) else value.strip()

            return value

        if origin in {list, tuple}:
            if isinstance(value, str):
                split = [item.strip() for item in value.split(",") if item.strip()]
                return split
            if isinstance(value, (list, tuple)):
                return list(value)
            return value

        if origin is dict:
            return value if isinstance(value, dict) else value

        if origin is type(None):
            return value

        # Handle Optional[...] / Union[..., None]
        if origin in {Union, UnionType}:
            non_none_args = [arg for arg in args if arg is not type(None)]
            for candidate in non_none_args:
                candidate_value = AgentOrchestrator._coerce_value_for_annotation(candidate, value)
                if candidate_value is not value:
                    return candidate_value
            return value

        return value

    def _normalize_generate_draft_params(self, params: dict[str, Any], tools: dict[str, Any], user: User) -> dict[str, Any]:
        normalized = dict(params or {})
        email_ref = str(normalized.get("email_id") or "").strip().lower()
        if not email_ref:
            return normalized

        if email_ref in self._URGENT_EMAIL_ALIASES:
            urgent_raw = tools["check_urgent_emails"](user_id=user.id)
            urgent_result = self._normalize_tool_result("check_urgent_emails", urgent_raw)
            urgent_items = urgent_result.get("urgent_emails")
            if isinstance(urgent_items, list) and urgent_items:
                urgent_id = urgent_items[0].get("id")
                if urgent_id:
                    normalized["email_id"] = urgent_id
                    return normalized

            latest_raw = tools["fetch_latest_emails"](user_id=user.id, limit=1)
            latest_result = self._normalize_tool_result("fetch_latest_emails", latest_raw)
            latest_items = latest_result.get("emails")
            if isinstance(latest_items, list) and latest_items:
                latest_id = latest_items[0].get("id")
                if latest_id:
                    normalized["email_id"] = latest_id
                    return normalized

        if email_ref in self._LATEST_EMAIL_ALIASES:
            normalized["email_id"] = "latest"

        tone = normalized.get("tone")
        if isinstance(tone, str):
            cleaned_tone = tone.strip().lower()
            allowed_tones = {"professional", "casual", "formal", "friendly"}
            if cleaned_tone and cleaned_tone not in allowed_tones:
                cleaned_tone = "professional"
            if cleaned_tone:
                normalized["tone"] = cleaned_tone

        return normalized

    @staticmethod
    def _find_missing_required_params(tool_fn: Any, params: dict[str, Any]) -> list[str]:
        """Return required keyword parameters that are not present or empty."""
        try:
            signature = inspect.signature(tool_fn)
        except (TypeError, ValueError):
            return []

        missing: list[str] = []
        for name, param in signature.parameters.items():
            if name == "user_id":
                continue
            if param.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                continue
            if param.default is not inspect.Parameter.empty:
                continue

            if name not in params:
                missing.append(name)
                continue

            value = params.get(name)
            if value is None:
                missing.append(name)
            elif isinstance(value, str) and not value.strip():
                missing.append(name)

        return missing

    @staticmethod
    def _format_missing_params_error(tool_name: str, missing_params: list[str]) -> str:
        if not missing_params:
            return f"I need more information to run {tool_name}."

        ordered = ", ".join(missing_params)
        if tool_name == "create_event":
            return (
                "I can create that calendar event, but I still need: "
                f"{ordered}. For a full-day one-time event, share the date and I can set it from 00:00 to 00:00 the next day."
            )

        return f"I can run {tool_name}, but I still need: {ordered}."

    @staticmethod
    def _enrich_tool_params(
        tool_name: str,
        params: dict[str, Any],
        user_message: str | None,
        conversation_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize planner params and infer sensible defaults for calendar all-day requests."""
        if not isinstance(params, dict):
            return {}

        enriched = dict(params)
        if tool_name == "summarize_search_result":
            link = str(enriched.get("link") or "").strip()
            if not link:
                message = user_message or ""
                extracted_link = AgentOrchestrator._extract_first_url(message)
                if extracted_link:
                    enriched["link"] = extracted_link
            return enriched

        if tool_name != "create_event":
            return enriched

        attendees = enriched.get("attendees")
        if isinstance(attendees, str):
            enriched["attendees"] = [item.strip() for item in attendees.split(",") if item.strip()]

        message = (user_message or "").lower()
        recent_user_text = AgentOrchestrator._collect_recent_user_text(conversation_context)
        combined_message = f"{recent_user_text}\n{message}".strip()
        normalized_time_hint = str(enriched.get("time") or "").strip().lower()
        normalized_duration = str(enriched.get("duration") or "").strip().lower()
        full_day_requested = any(
            [
                bool(enriched.get("all_day")),
                bool(enriched.get("is_all_day")),
                normalized_time_hint in {"all day", "full day"},
                normalized_duration in {"all day", "full day"},
                "all day" in combined_message,
                "full day" in combined_message,
            ]
        )

        if not enriched.get("title"):
            fallback_title = enriched.get("event_title") or enriched.get("name")
            extracted_title = AgentOrchestrator._extract_event_title_from_message(message)
            if extracted_title:
                fallback_title = extracted_title
            if full_day_requested:
                enriched["title"] = str(fallback_title or "Full Day Event")
            elif fallback_title:
                enriched["title"] = str(fallback_title)

        date_value = AgentOrchestrator._extract_event_date(enriched=enriched, message=combined_message)
        if not date_value:
            return enriched

        if not full_day_requested:
            start_hint = str(enriched.get("start_time") or "").strip()
            end_hint = str(enriched.get("end_time") or "").strip()

            if not start_hint:
                start_hint = AgentOrchestrator._extract_labeled_time_from_message(message=message, label="start") or ""
            if not end_hint:
                end_hint = AgentOrchestrator._extract_labeled_time_from_message(message=message, label="end") or ""

            start_iso = AgentOrchestrator._resolve_event_datetime(date_value=date_value, value=start_hint)
            end_iso = AgentOrchestrator._resolve_event_datetime(date_value=date_value, value=end_hint)

            if start_iso:
                enriched["start_time"] = start_iso
            if end_iso:
                enriched["end_time"] = end_iso

            return enriched

        if not enriched.get("start_time"):
            enriched["start_time"] = f"{date_value}T00:00:00"

        if not enriched.get("end_time"):
            try:
                start_date = datetime.fromisoformat(date_value)
                next_day = (start_date + timedelta(days=1)).date().isoformat()
                enriched["end_time"] = f"{next_day}T00:00:00"
            except Exception:
                pass

        return enriched

    @staticmethod
    def _extract_event_date(enriched: dict[str, Any], message: str) -> str | None:
        """Extract event date in YYYY-MM-DD from planner params or user text."""
        candidate_keys = ["date", "event_date", "start_date"]
        for key in candidate_keys:
            value = enriched.get(key)
            if isinstance(value, str) and value.strip():
                normalized = AgentOrchestrator._normalize_date_string(value)
                if normalized:
                    return normalized

        start_time = enriched.get("start_time")
        if isinstance(start_time, str) and start_time.strip():
            normalized = AgentOrchestrator._normalize_date_string(start_time)
            if normalized:
                return normalized

        date_in_message = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
        if date_in_message:
            normalized = AgentOrchestrator._normalize_date_string(date_in_message.group(1))
            if normalized:
                return normalized

        slash_or_dash = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", message)
        if slash_or_dash:
            normalized = AgentOrchestrator._normalize_date_string(slash_or_dash.group(1))
            if normalized:
                return normalized

        if "tomorrow" in message:
            return (datetime.utcnow().date() + timedelta(days=1)).isoformat()
        if "tmrw" in message:
            return (datetime.utcnow().date() + timedelta(days=1)).isoformat()
        if "today" in message:
            return datetime.utcnow().date().isoformat()

        return None

    @staticmethod
    def _normalize_date_string(value: str) -> str | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except Exception:
            raw = (value or "").strip()
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y", "%m-%d-%Y", "%d-%m-%Y"):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    return parsed.date().isoformat()
                except Exception:
                    continue
            try:
                parsed = datetime.fromisoformat(value.strip().split("T")[0])
                return parsed.date().isoformat()
            except Exception:
                return None

    @staticmethod
    def _extract_first_url(message: str) -> str | None:
        match = re.search(r"https?://[^\s)\]>\"']+", message or "")
        if not match:
            return None
        return match.group(0).strip()

    @staticmethod
    def _collect_recent_user_text(conversation_context: dict[str, Any] | None) -> str:
        turns = []
        if isinstance(conversation_context, dict):
            maybe_turns = conversation_context.get("recent_turns")
            if isinstance(maybe_turns, list):
                turns = maybe_turns

        snippets: list[str] = []
        for turn in turns[-8:]:
            if not isinstance(turn, dict):
                continue
            if str(turn.get("role") or "").lower() != "user":
                continue
            content = str(turn.get("content") or "").strip()
            if content:
                snippets.append(content)

        return "\n".join(snippets)

    @staticmethod
    def _extract_event_title_from_message(message: str) -> str | None:
        text = (message or "").strip()
        if not text:
            return None

        title_match = re.search(
            r"(?:^|\b)(?:title|name|event|called)\s*[:=-]\s*(.+?)(?=(?:\n|\r|\bstart\b|\bend\b|\btime\b|$))",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not title_match:
            return None

        title = title_match.group(1).strip().strip(".,")
        return title or None

    @staticmethod
    def _extract_labeled_time_from_message(message: str, label: str) -> str | None:
        pattern = rf"\b{re.escape(label)}(?:\s*time)?(?:\s+at)?\s*[:=-]?\s*([^\n\r,;]+)"
        match = re.search(pattern, message or "", flags=re.IGNORECASE)
        if not match:
            return None
        candidate = match.group(1).strip().strip(".,")
        return candidate or None

    @staticmethod
    def _extract_time_candidates_from_message(message: str) -> list[str]:
        text = (message or "").strip().lower()
        if not text:
            return []

        candidates = re.findall(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b", text)
        normalized = []
        for candidate in candidates:
            cleaned = re.sub(r"\s+", " ", candidate.strip())
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _resolve_event_datetime(date_value: str, value: str) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None

        parsed_iso = AgentOrchestrator._parse_iso_datetime(raw)
        if parsed_iso:
            return parsed_iso.replace(microsecond=0).isoformat()

        normalized = raw.lower().replace(".", "")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = re.sub(r"(\d)(am|pm)\b", r"\1 \2", normalized)

        time_formats = ["%I:%M %p", "%I %p", "%H:%M", "%H"]
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(normalized, fmt).time().replace(microsecond=0)
                return datetime.combine(datetime.fromisoformat(date_value).date(), parsed_time).isoformat()
            except Exception:
                continue

        return None

    @staticmethod
    def _infer_create_event_follow_up_params(user_message: str, user_context: dict[str, Any]) -> dict[str, Any] | None:
        if not AgentOrchestrator._has_recent_create_event_missing_prompt(user_context):
            return None

        text = (user_message or "").strip()
        combined = f"{AgentOrchestrator._collect_recent_user_text((user_context or {}).get('conversation_context'))}\n{text}".strip()
        params: dict[str, Any] = {}

        title = AgentOrchestrator._extract_event_title_from_message(text)
        if title:
            params["title"] = title

        date_value = AgentOrchestrator._extract_event_date(enriched=params, message=combined.lower())
        time_candidates = AgentOrchestrator._extract_time_candidates_from_message(text)
        start_hint = AgentOrchestrator._extract_labeled_time_from_message(message=text, label="start")
        end_hint = AgentOrchestrator._extract_labeled_time_from_message(message=text, label="end")

        if date_value:
            start_iso = None
            if start_hint:
                start_iso = AgentOrchestrator._resolve_event_datetime(date_value=date_value, value=start_hint)
            if not start_iso and time_candidates:
                start_iso = AgentOrchestrator._resolve_event_datetime(date_value=date_value, value=time_candidates[0])
            if start_iso:
                params["start_time"] = start_iso

            end_iso = None
            if end_hint:
                end_iso = AgentOrchestrator._resolve_event_datetime(date_value=date_value, value=end_hint)
            if not end_iso and len(time_candidates) > 1:
                end_iso = AgentOrchestrator._resolve_event_datetime(date_value=date_value, value=time_candidates[1])
            if end_iso:
                params["end_time"] = end_iso

        if params:
            return params

        if AgentOrchestrator._is_affirmative_help_follow_up(text.lower()):
            return {}

        return None

    @staticmethod
    def _has_recent_create_event_missing_prompt(user_context: dict[str, Any]) -> bool:
        conversation_context = dict((user_context or {}).get("conversation_context") or {})
        recent_turns = conversation_context.get("recent_turns")
        if not isinstance(recent_turns, list):
            return False

        for turn in reversed(recent_turns[-8:]):
            if not isinstance(turn, dict):
                continue
            if str(turn.get("role") or "").lower() != "assistant":
                continue
            content = str(turn.get("content") or "").lower()
            if (
                "i can create that calendar event" in content
                and "i still need" in content
                and "start_time" in content
                and "end_time" in content
            ):
                return True

        return False

    @staticmethod
    def _format_slot_range(start: str, end: str) -> str:
        start_dt = AgentOrchestrator._parse_iso_datetime(start)
        end_dt = AgentOrchestrator._parse_iso_datetime(end)
        if not start_dt or not end_dt:
            return f"{start} to {end}"

        start_day = start_dt.strftime("%b %d, %Y").replace(" 0", " ")
        start_time = start_dt.strftime("%I:%M %p").lstrip("0")
        end_time = end_dt.strftime("%I:%M %p").lstrip("0")

        if start_dt.date() == end_dt.date():
            return f"{start_day}, {start_time} to {end_time}"

        end_day = end_dt.strftime("%b %d, %Y").replace(" 0", " ")
        return f"{start_day}, {start_time} to {end_day}, {end_time}"

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _format_task_due_date(value: Any) -> str | None:
        if value in (None, ""):
            return None
        due_dt = AgentOrchestrator._parse_iso_datetime(str(value))
        if due_dt:
            return due_dt.strftime("%b %d, %Y").replace(" 0", " ")
        return str(value)

    @staticmethod
    def _format_task_explanation(task: dict[str, Any], index: int) -> str:
        title = str(task.get("title") or "Untitled task").strip()
        priority = str(task.get("priority") or "medium").strip().lower()
        status = str(task.get("status") or "todo").strip().lower()
        due_text = AgentOrchestrator._format_task_due_date(task.get("due_date"))
        description = str(task.get("description") or "").strip()

        summary_bits = [f"{priority} priority", status]
        if due_text:
            summary_bits.append(f"due {due_text}")

        explanation = f"{index}. {title} ({', '.join(summary_bits)})"
        if description:
            trimmed = f"{description[:160]}..." if len(description) > 160 else description
            explanation += f" - {trimmed}"
        return explanation

    @staticmethod
    def _normalize_tool_result(tool_name: str, raw_result: Any) -> dict[str, Any]:
        """Convert tool outputs into a consistent payload shape for downstream handling."""
        if not isinstance(raw_result, dict):
            return {
                "status": "failed",
                "error": f"Unexpected result type from {tool_name}: {type(raw_result).__name__}",
                "raw_result": raw_result,
            }

        result = dict(raw_result)
        status = str(result.get("status", "")).lower()

        if status in {"success", "failed"}:
            return result

        if result.get("success") is True:
            result["status"] = "success"
            return result

        if result.get("error"):
            result["status"] = "failed"
            return result

        result["status"] = "failed"
        result["error"] = result.get("error") or "Tool returned an unrecognized payload"
        return result

    def _capture_pending_approval(self, state: AgentState, user: User, tool_name: str, result: dict) -> None:
        approval_id = result.get("approval_id")
        if not approval_id and result.get("requires_approval") and tool_name == "generate_draft_reply":
            approval_id = self._create_draft_approval(user, result)

        if not approval_id:
            return

        state.pending_approval = PendingApproval(
            approval_id=approval_id,
            action_type=result.get("action_type") or state.plan.action_type.value,
            action_payload=result,
            reason=(state.plan.approval_reason if state.plan else "Approval required"),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=15),
            ai_confidence=state.plan.confidence if state.plan else 0.8,
        )
        self._publish_approval_requested(user_id=user.id, approval_id=approval_id, result=result, trace_id=state.trace_id)

    def _create_draft_approval(self, user: User, result: dict) -> str | None:
        draft = result.get("draft") or {}
        if not draft:
            return None

        try:
            approval = Approval(
                user_id=user.id,
                approval_type=Approval.ApprovalType.SEND_EMAIL,
                status=Approval.ApprovalStatus.PENDING,
                action_description=f"Send drafted email to {draft.get('to_recipient', 'recipient')}",
                action_payload=draft,
                ai_reasoning="AI generated an email draft",
                confidence_score=float(draft.get("confidence", 0.8)),
                expires_at=datetime.utcnow() + timedelta(minutes=15),
            )
            self.db.add(approval)
            self.db.commit()
            return approval.id
        except Exception:
            self.db.rollback()
            return None

    def _publish_approval_requested(self, user_id: str, approval_id: str, result: dict, trace_id: str) -> None:
        payload = {
            "type": "approvals:requested",
            "approval_id": approval_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id,
            "data": {
                "approval_id": approval_id,
                "action_type": result.get("action_type", "other"),
                "preview": result.get("event_preview") or result.get("draft") or {},
            },
        }
        try:
            redis_client = get_redis()
            redis_client.publish(f"ws:approvals:{user_id}", json.dumps(payload))
        except Exception:
            logger.warning("orchestration.publish_approval_requested.failed", extra={"trace_id": trace_id, "user_id": user_id})

    def _build_response(self, state: AgentState) -> None:
        if state.pending_approval:
            state.response = ResponseContent(
                message="I prepared this action and it now needs your approval before execution.",
                action_cards=[
                    ActionCard(
                        id=state.pending_approval.approval_id,
                        label="Review approval",
                        action="approve",
                        payload={"approval_id": state.pending_approval.approval_id},
                    )
                ],
                suggested_follow_ups=["Approve this action", "Modify this action", "Reject this action"],
            )
            state.current_node = "awaiting_approval"
            state.metadata.nodes_executed.append("awaiting_approval")
            return

        successful = [item for item in state.tool_results if item.success]
        failed = [item for item in state.tool_results if not item.success]
        if not successful:
            if state.plan and not state.plan.tools_required:
                contextual_message = self._generate_contextual_follow_up_reply(state)
                message = contextual_message or self._generate_conversational_reply(state)
            elif failed:
                error_text = " | ".join((item.error or "").lower() for item in failed)
                missing_param_failures = [
                    item for item in failed
                    if isinstance(item.result, dict) and item.result.get("error_code") == "missing_required_parameters"
                ]
                if missing_param_failures:
                    first_failure = missing_param_failures[0]
                    message = (first_failure.error or "").strip() or "I need a few required fields before I can complete that action."
                elif (
                    "gmail not connected" in error_text
                    or "no emails found" in error_text
                    or "failed to summarize inbox" in error_text
                ):
                    message = (
                        "I could not access your inbox right now. "
                        "Please connect Gmail (or sync sample data) and try again."
                    )
                elif "calendar not connected" in error_text:
                    message = "I could not access your calendar because Calendar is not connected yet. Please connect Calendar and try again."
                elif "not found" in error_text:
                    message = "I could not find the required data for that request. Please try a more specific prompt."
                else:
                    # Fall back to a conversational answer when tool execution fails.
                    message = self._generate_conversational_reply(state)
            else:
                message = "I could not complete that request yet. Please try again in a moment."
        else:
            first = successful[0]
            successful_by_tool = {item.tool_name: item.result or {} for item in successful}

            if "summarize_inbox" in successful_by_tool or "check_urgent_emails" in successful_by_tool:
                summary_result = successful_by_tool.get("summarize_inbox", {})
                urgent_result = successful_by_tool.get("check_urgent_emails", {})

                total = summary_result.get("total_count", 0)
                unread = summary_result.get("unread_count", 0)
                summary_text = summary_result.get("summary", "")

                urgent_count = urgent_result.get("urgent_count")
                if urgent_count is None:
                    urgent_count = summary_result.get("urgent_count", 0)

                if summary_text:
                    message = (
                        f"I checked your inbox: {total} emails ({unread} unread), "
                        f"with {urgent_count} urgent email(s).\n\n{summary_text}"
                    )
                else:
                    message = (
                        f"I checked your inbox: {total} emails ({unread} unread), "
                        f"with {urgent_count} urgent email(s)."
                    )

            elif first.tool_name == "generate_daily_plan":
                summary = (first.result or {}).get("plan", {}).get("summary", {})
                message = (
                    "Here is your plan for today: "
                    f"{summary.get('high_priority_tasks', 0)} high-priority tasks, "
                    f"{summary.get('total_tasks', 0)} total tasks, and "
                    f"{summary.get('urgent_emails', 0)} urgent emails."
                )
            elif first.tool_name == "list_free_slots":
                free_slots = (first.result or {}).get("free_slots", [])
                count = len(free_slots)
                if count == 0:
                    message = "I checked your schedule and there are no free slots matching that request."
                else:
                    preview = []
                    for slot in free_slots[:3]:
                        start = str(slot.get("start_time", ""))
                        end = str(slot.get("end_time", ""))
                        if start and end:
                            preview.append(self._format_slot_range(start, end))
                    suffix = f" First slots: {', '.join(preview)}." if preview else ""
                    message = f"I found {count} free slot(s).{suffix}"
            elif first.tool_name == "create_task":
                task = (first.result or {}).get("task", {})
                title = task.get("title") or "your task"
                status = task.get("status") or "todo"
                priority = task.get("priority") or "medium"
                message = f"Added task '{title}' with {priority} priority ({status})."
            elif first.tool_name == "list_tasks":
                result = first.result or {}
                count = int(result.get("count") or 0)
                tasks = result.get("tasks") if isinstance(result.get("tasks"), list) else []
                if count == 0:
                    message = (
                        "I did not find any tasks right now. "
                        "Would you like me to add one, or help with something else?"
                    )
                else:
                    explanations = [
                        self._format_task_explanation(task, idx)
                        for idx, task in enumerate(tasks[:5], start=1)
                        if isinstance(task, dict)
                    ]

                    message = f"I found {count} task(s)."
                    if explanations:
                        message += "\n\nHere is what those tasks are:\n" + "\n".join(explanations)
                    overflow = count - len(explanations)
                    if overflow > 0:
                        message += f"\n...and {overflow} more."
                    message += "\n\nWould you like me to add any other tasks, or help with something else?"
            elif first.tool_name == "check_urgent_emails":
                urgent_count = (first.result or {}).get("urgent_count", 0)
                message = f"I checked your inbox and found {urgent_count} urgent email(s)."
            elif first.tool_name == "summarize_inbox":
                result = first.result or {}
                total = result.get("total_count", 0)
                unread = result.get("unread_count", 0)
                summary = result.get("summary", "")
                if summary:
                    message = f"Inbox summary for {total} emails ({unread} unread):\n\n{summary}"
                else:
                    message = f"I summarized your inbox: {total} emails ({unread} unread)."
            elif first.tool_name == "create_event":
                result = first.result or {}
                event = result.get("event") or result.get("event_preview") or {}
                title = event.get("title") or "your event"
                start_time = event.get("start_time")
                end_time = event.get("end_time")
                if start_time and end_time:
                    message = f"Created '{title}' from {start_time} to {end_time}."
                else:
                    message = f"Created '{title}'."
            elif first.tool_name == "serp_search":
                result = first.result or {}
                query = result.get("query") or "your query"
                count = int(result.get("count") or 0)
                top_results = list(result.get("results") or [])
                if count == 0 or not top_results:
                    message = f"I searched Google for '{query}', but no results were returned."
                else:
                    preview = []
                    for item in top_results[:3]:
                        title = str(item.get("title") or "Untitled result")
                        link = str(item.get("link") or "")
                        preview.append(f"{title} ({link})" if link else title)
                    findings = []
                    for idx, item in enumerate(top_results[:2], start=1):
                        title = str(item.get("title") or f"Result {idx}")
                        extracted = str(item.get("page_summary") or item.get("snippet") or "").strip()
                        if extracted:
                            findings.append(f"{idx}. {title}: {extracted[:280]}")

                    message = (
                        f"I found {count} Google result(s) for '{query}'. "
                        f"Top results: {'; '.join(preview)}"
                    )
                    if findings:
                        message += "\n\nWhat those pages say:\n" + "\n".join(findings)
            elif first.tool_name == "summarize_search_result":
                result = first.result or {}
                link = str(result.get("link") or "that link")
                summary = str(result.get("summary") or "").strip()
                if summary:
                    message = f"Here is what I found in {link}:\n\n{summary}"
                else:
                    message = f"I could not extract useful content from {link}."
            elif first.tool_name == "save_search_note":
                note = (first.result or {}).get("note") or {}
                query = note.get("query") or "your search"
                message = f"Saved a note for search '{query}'."
            elif first.tool_name == "list_search_notes":
                count = int((first.result or {}).get("count") or 0)
                message = f"I found {count} saved search note(s)."
            else:
                message = f"Completed using {first.tool_name}."

        state.response = ResponseContent(
            message=message,
            suggested_follow_ups=["What is next on my calendar?", "Show my top tasks", "Summarize urgent emails"],
        )
        state.current_node = "response_generator"
        state.metadata.nodes_executed.append("response_generator")

    def _generate_contextual_follow_up_reply(self, state: AgentState) -> str | None:
        """Handle short anaphoric follow-ups using recent in-session context when possible."""
        raw_text = (state.user_input.content or "").strip()
        user_text = (state.user_input.content or "").strip().lower()

        direct_compose = self._generate_direct_email_compose_reply(raw_text)
        if direct_compose:
            return direct_compose

        if self._is_affirmative_help_follow_up(user_text):
            recipient = self._extract_recent_email_recipient_from_context(state)
            if recipient:
                return (
                    f"Absolutely. I can help you draft that email to {recipient}. "
                    "Share the main point, preferred tone, and any deadline, and I will prepare a clean draft."
                )

        if not self._is_name_results_follow_up(user_text):
            return None

        query, titles = self._extract_recent_search_titles_from_context(state)
        if not titles:
            return None

        numbered = "\n".join(f"{idx}. {title}" for idx, title in enumerate(titles, start=1))
        if query:
            return f"Here are the results I found for '{query}':\n{numbered}"
        return f"Here are the result names:\n{numbered}"

    @staticmethod
    def _is_name_results_follow_up(user_text: str) -> bool:
        patterns = [
            r"\bcan you name them\b",
            r"\bname them\b",
            r"\blist them\b",
            r"\bwhat are they\b",
            r"\bwhich ones\b",
            r"\bname (those|these)\b",
        ]
        return any(re.search(pattern, user_text) for pattern in patterns)

    @staticmethod
    def _is_affirmative_help_follow_up(user_text: str) -> bool:
        patterns = [
            r"^yes$",
            r"^yes\s+i\s+need\s+help$",
            r"^i\s+need\s+help$",
            r"^yes\s+please$",
            r"^yes\s+add\s+it(?:\s+then)?$",
            r"^help\s+me$",
            r"^sure$",
        ]
        return any(re.search(pattern, user_text.strip()) for pattern in patterns)

    @staticmethod
    def _extract_recent_email_recipient_from_context(state: AgentState) -> str | None:
        """Extract recipient email from recent turns when assistant asked about composing an email."""
        user_context = dict((state.user_input.context or {}).get("user_context") or {})
        conversation_context = dict(user_context.get("conversation_context") or {})
        recent_turns = conversation_context.get("recent_turns")

        if not isinstance(recent_turns, list) or not recent_turns:
            return None

        assistant_asked_email_help = False
        for turn in reversed(recent_turns[-6:]):
            if not isinstance(turn, dict):
                continue
            if str(turn.get("role") or "").lower() != "assistant":
                continue

            content = str(turn.get("content") or "").lower()
            if "help composing an email" in content or "schedule a task related to this email" in content:
                assistant_asked_email_help = True
                break

        if not assistant_asked_email_help:
            return None

        email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        for turn in reversed(recent_turns):
            if not isinstance(turn, dict):
                continue
            if str(turn.get("role") or "").lower() != "user":
                continue

            content = str(turn.get("content") or "")
            match = email_pattern.search(content)
            if match:
                return match.group(0)

        return None

    @staticmethod
    def _is_explicit_new_email_request(user_text: str) -> bool:
        text = (user_text or "").strip().lower()
        if not text:
            return False

        has_email_verb = any(token in text for token in ["send", "sent", "compose", "draft", "write"])
        has_email_noun = any(token in text for token in ["email", "mail"])
        has_recipient = bool(re.search(r"\bto\s+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text))
        return has_email_verb and has_email_noun and has_recipient

    @staticmethod
    def _generate_direct_email_compose_reply(user_text: str) -> str | None:
        """Generate a deterministic draft response for explicit outbound compose requests."""
        if not AgentOrchestrator._is_explicit_new_email_request(user_text):
            return None

        recipient_match = re.search(r"\bto\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", user_text, flags=re.IGNORECASE)
        recipient = recipient_match.group(1) if recipient_match else "the recipient"

        details_match = re.search(r"\b(?:regarding|about|for)\b\s+(.+)$", user_text, flags=re.IGNORECASE)
        details = details_match.group(1).strip() if details_match else "my leave request"

        tomorrow_requested = bool(re.search(r"\b(tomorrow|tmrw)\b", user_text, flags=re.IGNORECASE))
        subject = "Leave Request" + (" for Tomorrow" if tomorrow_requested else "")

        return (
            f"I can draft that email to {recipient}.\n\n"
            f"Subject: {subject}\n\n"
            "Hi,\n\n"
            f"I am writing to inform you that I will not be able to attend class {'tomorrow' if tomorrow_requested else 'as discussed'} due to {details}. "
            "I kindly request leave for this absence.\n\n"
            "Thank you for your understanding.\n\n"
            "Best regards,"
        )

    @staticmethod
    def _extract_recent_search_titles_from_context(state: AgentState) -> tuple[str | None, list[str]]:
        """Extract titles from the latest assistant message that contains a serp summary."""
        user_context = dict((state.user_input.context or {}).get("user_context") or {})
        conversation_context = dict(user_context.get("conversation_context") or {})
        recent_turns = conversation_context.get("recent_turns")

        if not isinstance(recent_turns, list):
            return None, []

        for turn in reversed(recent_turns):
            if not isinstance(turn, dict):
                continue
            if str(turn.get("role") or "").lower() != "assistant":
                continue

            content = str(turn.get("content") or "").strip()
            if "Top results:" not in content:
                continue

            query_match = re.search(r"Google result\(s\) for '([^']+)'", content)
            query = query_match.group(1).strip() if query_match else None
            _, _, raw_results = content.partition("Top results:")
            candidates = [item.strip() for item in raw_results.split(";") if item.strip()]

            titles: list[str] = []
            for candidate in candidates:
                title = re.sub(r"\s*\(https?://[^)]*\)\s*$", "", candidate).strip()
                if title:
                    titles.append(title)

            if titles:
                return query, titles

        return None, []

    def _generate_conversational_reply(self, state: AgentState) -> str:
        """Generate a natural assistant response when no tools are required."""
        user_text = state.user_input.content or ""
        user_context = dict((state.user_input.context or {}).get("user_context") or {})

        if not self._assistant_llm:
            return (
                "I can help you think through options and plan next steps for your day, "
                "calendar, emails, and tasks. Tell me what you are deciding and I will suggest a clear plan."
            )

        prompt = (
            f"You are {settings.assistant_name}, a practical personal assistant. Respond naturally and conversationally. "
            "The user wants normal chat guidance as well as help with planning, calendar, emails, and tasks. "
            "Give concise, actionable suggestions. "
            "If useful, propose a short step-by-step plan. "
            "Do not mention internal tools, routing, or implementation details.\n\n"
            f"Personalization context (JSON): {json.dumps(user_context, default=str)}\n\n"
            f"User message: {user_text}"
        )

        try:
            result = self._assistant_llm.invoke(prompt)
            text = str(result.content or "").strip()
            if text:
                return text
        except Exception:
            logger.warning(
                "orchestration.assistant_chat_fallback",
                extra={"trace_id": state.trace_id, "user_id": state.user_id},
                exc_info=True,
            )

        return (
            "Got it. I can help you decide what to do next across tasks, calendar, and emails. "
            "Tell me your goal for today and I will suggest a focused plan."
        )

    @staticmethod
    def _build_user_context(
        user: User,
        conversation_context: dict[str, Any] | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        preferences = dict(user.preferences or {})
        profile = dict(preferences.get("assistant_profile") or {})

        resolved_context = {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "timezone": user.timezone,
            "language": profile.get("language") or preferences.get("language") or "en",
            "organization": profile.get("organization"),
            "role": profile.get("role"),
            "working_hours_start": profile.get("working_hours_start"),
            "working_hours_end": profile.get("working_hours_end"),
            "communication_tone": profile.get("communication_tone") or preferences.get("tone"),
            "role_context": profile.get("role_context"),
            "ai_instructions": profile.get("ai_instructions"),
            "conversation_context": conversation_context or {},
            "assistant_name": settings.assistant_name,
        }

        if isinstance(external_context, dict):
            ui_context = dict(external_context.get("ui") or {})
            if ui_context:
                resolved_context["ui"] = ui_context

            explicit_context = dict(external_context.get("explicit") or {})
            for key in ["role_context", "ai_instructions", "communication_tone", "language"]:
                value = explicit_context.get(key)
                if isinstance(value, str) and value.strip():
                    resolved_context[key] = value.strip()

        return resolved_context

    def _persist_conversation_turns(
        self,
        *,
        memory_service: ConversationMemoryService,
        user: User,
        state: AgentState,
        user_message: str,
    ) -> None:
        """Persist message pair without blocking main agent response flow."""
        assistant_message = state.response.message if state.response else ""
        try:
            memory_service.persist_turn_pair(
                user=user,
                session_id=state.session_id,
                user_message=user_message,
                assistant_message=assistant_message,
                trace_id=state.trace_id,
                tool_results=[item.model_dump(mode="json") for item in state.tool_results],
                approval_id=state.pending_approval.approval_id if state.pending_approval else None,
            )
        except Exception:
            self.db.rollback()
            logger.warning(
                "orchestration.persist_conversation_turns.failed",
                extra={"trace_id": state.trace_id, "user_id": state.user_id},
                exc_info=True,
            )

    def _persist_state(self, state: AgentState) -> None:
        try:
            redis_client = get_redis()
            cache_key = f"state:{state.user_id}:{state.trace_id}"
            redis_client.setex(cache_key, 86400, json.dumps(state.to_redis_dict(), default=str))
        except Exception:
            logger.warning("orchestration.persist_state.failed", extra={"trace_id": state.trace_id, "user_id": state.user_id})
