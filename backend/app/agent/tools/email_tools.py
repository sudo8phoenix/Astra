"""
LangGraph tools for email management.

Tools that the planner node can invoke to:
- Fetch and list emails
- Summarize inbox
- Generate draft replies
- Check urgent emails
"""

import json
import logging
from time import perf_counter
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.db.models import User
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def create_email_tools(db: Session):
    """Create email tools for LangGraph agent."""
    
    service = EmailService(db)
    
    def fetch_latest_emails(user_id: str, limit: int = 10, label: str = "INBOX") -> Dict[str, Any]:
        """
        Fetch latest emails from user's Gmail inbox.
        
        Args:
            user_id: User ID
            limit: Number of emails to fetch (1-50)
            label: Gmail label (INBOX, SENT, DRAFT, etc.)
            
        Returns:
            Dictionary with email list or error
        """
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {"error": "User not found", "status": "failed"}
            
            emails = service.fetch_latest_emails(
                user,
                limit=min(limit, 50),  # Cap at 50
                label=label,
            )
            
            if not emails:
                return {
                    "error": "Gmail not connected or no emails found",
                    "status": "failed",
                }
            
            # Return email summaries
            email_summaries = []
            for email in emails[:10]:  # Limit output to 10
                email_summaries.append({
                    "id": email.get("id"),
                    "subject": email.get("subject"),
                    "from": email.get("from_address"),
                    "timestamp": str(email.get("timestamp")),
                    "is_unread": email.get("is_unread"),
                })
            
            response = {
                "status": "success",
                "count": len(emails),
                "emails": email_summaries,
            }
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.fetch_latest_emails", "success", duration_ms)
            logger.info(
                "tool.fetch_latest_emails.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "duration_ms": round(duration_ms, 2),
                    "count": len(email_summaries),
                },
            )
            return response
        
        except Exception as e:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.fetch_latest_emails", "error", duration_ms)
            logger.error(
                "tool.fetch_latest_emails.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"error": str(e), "status": "failed"}
    
    def summarize_inbox(
        user_id: str,
        limit: int = 10,
        include_urgent_only: bool = False,
        priority: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        """
        Generate AI summary of inbox.
        
        Args:
            user_id: User ID
            limit: Number of emails to summarize
            
        Returns:
            Summary of inbox or error
        """
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {"error": "User not found", "status": "failed"}
            
            normalized_priority = (priority or "").strip().lower()
            if normalized_priority in {"urgent", "high", "critical"}:
                include_urgent_only = True

            summary = service.summarize_inbox(
                user,
                limit=min(limit, 20),
                include_urgent_only=include_urgent_only,
            )
            
            if not summary:
                return {"error": "Failed to summarize inbox", "status": "failed"}
            
            response = {
                "status": "success",
                "total_count": summary.total_count,
                "unread_count": summary.unread_count,
                "summary": summary.summary_text,
                "key_senders": summary.key_senders,
                "action_items": summary.action_items,
                "urgent_count": len(summary.urgent_emails) if summary.urgent_emails else 0,
            }
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.summarize_inbox", "success", duration_ms)
            logger.info(
                "tool.summarize_inbox.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return response
        
        except Exception as e:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.summarize_inbox", "error", duration_ms)
            logger.error(
                "tool.summarize_inbox.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"error": str(e), "status": "failed"}
    
    def check_urgent_emails(user_id: str) -> Dict[str, Any]:
        """
        Check for urgent/important emails.
        
        Args:
            user_id: User ID
            
        Returns:
            List of urgent emails or error
        """
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {"error": "User not found", "status": "failed"}
            
            emails = service.fetch_latest_emails(user, limit=20)
            if not emails:
                return {
                    "status": "success",
                    "urgent_count": 0,
                    "urgent_emails": [],
                }
            
            urgent_emails = []
            for email in emails:
                urgency = service._classify_email_urgency(
                    user_id=user_id,
                    subject=email.get("subject", ""),
                    body=email.get("body_plain", "")[:500],
                    from_address=email.get("from_address", ""),
                )
                
                if urgency.get("urgency_level") in ["high", "critical"]:
                    urgent_emails.append({
                        "id": email.get("id"),
                        "subject": email.get("subject"),
                        "from": email.get("from_address"),
                        "urgency": urgency.get("urgency_level"),
                        "reason": urgency.get("reason"),
                    })
            
            response = {
                "status": "success",
                "urgent_count": len(urgent_emails),
                "urgent_emails": urgent_emails,
            }
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.check_urgent_emails", "success", duration_ms)
            logger.info(
                "tool.check_urgent_emails.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "duration_ms": round(duration_ms, 2),
                    "urgent_count": len(urgent_emails),
                },
            )
            return response
        
        except Exception as e:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.check_urgent_emails", "error", duration_ms)
            logger.error(
                "tool.check_urgent_emails.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"error": str(e), "status": "failed"}
    
    def generate_draft_reply(
        user_id: str,
        email_id: str,
        tone: str = "professional",
    ) -> Dict[str, Any]:
        """
        Generate draft reply to an email.
        
        Args:
            user_id: User ID
            email_id: Email ID to reply to
            tone: Reply tone (professional, casual, formal, friendly)
            
        Returns:
            Draft reply or error
        """
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {"error": "User not found", "status": "failed"}
            
            # Get email details
            gmail_client = service.get_gmail_client(user)
            if not gmail_client:
                return {"error": "Gmail not connected", "status": "failed"}
            
            email_details = gmail_client.get_message_details(email_id)
            if not email_details:
                return {"error": "Email not found", "status": "failed"}
            
            # Generate draft
            draft = service.generate_draft_reply(
                user,
                email_id=email_id,
                recipient=email_details.get("from_address"),
                tone=tone,
            )
            
            if not draft:
                return {"error": "Failed to generate draft", "status": "failed"}

            approval_id = service.create_approval_for_draft(
                user=user,
                draft=draft,
                email_id=email_id,
            )
            
            response = {
                "status": "success",
                "draft": {
                    "id": draft.id,
                    "body": draft.body,
                    "tone": draft.tone,
                    "confidence": draft.confidence,
                    "thread_id": draft.thread_id,
                    "to_recipient": getattr(draft, "to_recipient", None),
                },
                "requires_approval": True,
                "approval_id": approval_id,
                "action_type": "send_email",
            }
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.generate_draft_reply", "success", duration_ms)
            logger.info(
                "tool.generate_draft_reply.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "duration_ms": round(duration_ms, 2),
                    "email_id": email_id,
                },
            )
            return response
        
        except Exception as e:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.generate_draft_reply", "error", duration_ms)
            logger.error(
                "tool.generate_draft_reply.error",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "duration_ms": round(duration_ms, 2),
                    "email_id": email_id,
                },
                exc_info=True,
            )
            return {"error": str(e), "status": "failed"}
    
    return {
        "fetch_latest_emails": fetch_latest_emails,
        "summarize_inbox": summarize_inbox,
        "check_urgent_emails": check_urgent_emails,
        "generate_draft_reply": generate_draft_reply,
    }


def register_email_tools(graph: Any) -> None:
    """
    Register email tools with LangGraph.
    
    Usage in planner node:
        tools = {
            "fetch_latest_emails": {...},
            "summarize_inbox": {...},
            "check_urgent_emails": {...},
            "generate_draft_reply": {...},
        }
    """
    # This function is a placeholder for integrating with LangGraph
    # Actual integration depends on the LangGraph architecture
    pass
