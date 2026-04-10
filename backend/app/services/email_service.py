"""
Email management service with LLM integration.

Provides high-level operations for:
- Email fetching and caching
- Inbox summarization using LLM
- Draft reply generation using LLM
- Urgency classification
- Approval workflow management
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import json
import math

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.llm_monitoring import llm_usage_monitor
from app.integrations.gmail import GmailClient, GmailOAuthManager
from app.db.models import User, Email, Approval
from app.schemas.email import (
    EmailMetadata,
    EmailSummary,
    EmailDraft,
    EmailUrgencyClassification,
)
from app.schemas.approvals import ApprovalActionType

logger = logging.getLogger(__name__)


class EmailService:
    """Service for email management and AI processing."""

    _LATEST_EMAIL_ALIASES = {"latest", "recent", "newest", "last"}
    _URGENT_EMAIL_ALIASES = {"urgent", "high", "critical", "important", "priority"}
    
    def __init__(self, db: Session):
        """Initialize email service."""
        self.db = db
        self.oauth_manager: GmailOAuthManager | None = None
        self.llm = ChatGroq(
            model=settings.groq_execution_model,
            temperature=settings.llm_temperature,
            api_key=settings.groq_api_key,
        )
        self.planner_llm = ChatGroq(
            model=settings.groq_planner_model,
            temperature=settings.llm_temperature,
            api_key=settings.groq_api_key,
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough fallback token estimate when provider usage is unavailable."""
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 4))

    def _estimate_cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        input_cost = (prompt_tokens / 1000.0) * settings.llm_input_cost_per_1k_tokens_usd
        output_cost = (completion_tokens / 1000.0) * settings.llm_output_cost_per_1k_tokens_usd
        return float(input_cost + output_cost)

    def _record_llm_usage(
        self,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        source: str,
    ) -> None:
        cost_usd = self._estimate_cost_usd(prompt_tokens, completion_tokens)
        usage_state = llm_usage_monitor.record_usage(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        logger.info(
            "llm.usage.recorded",
            extra={
                "user_id": user_id,
                "source": source,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": round(cost_usd, 6),
                "daily_tokens": usage_state["daily_tokens"],
                "daily_cost_usd": usage_state["daily_cost_usd"],
                "threshold_exceeded": usage_state["threshold_exceeded"],
            },
        )

    def _get_oauth_manager(self) -> Optional[GmailOAuthManager]:
        """Lazily initialize Gmail OAuth support when credentials are available."""
        if self.oauth_manager is not None:
            return self.oauth_manager

        try:
            self.oauth_manager = GmailOAuthManager()
        except ValueError as error:
            logger.warning("Gmail OAuth manager unavailable: %s", error)
            return None

        return self.oauth_manager
    
    def get_oauth_auth_url(self, state: str = "") -> str:
        """
        Get Google OAuth authorization URL for email connection.
        
        Args:
            state: State parameter for security
            
        Returns:
            Authorization URL to redirect user to
        """
        oauth_manager = self._get_oauth_manager()
        if not oauth_manager:
            raise ValueError("Google OAuth credentials not configured in settings")

        auth_url = oauth_manager.get_auth_url(state=state)
        return auth_url
    
    def connect_gmail_account(self, user: User, auth_code: str) -> bool:
        """
        Connect user's Gmail account via OAuth.
        
        Args:
            user: User object to update with Gmail token
            auth_code: Authorization code from Google OAuth callback
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            oauth_manager = self._get_oauth_manager()
            if not oauth_manager:
                return False

            token_response = oauth_manager.exchange_code_for_token(auth_code)

            # Reassign JSON preferences to ensure SQLAlchemy persists updates.
            preferences = dict(user.preferences or {})
            preferences["gmail_access_token"] = token_response["access_token"]
            preferences["gmail_refresh_token"] = token_response.get("refresh_token")
            preferences["gmail_token_expires_at"] = token_response.get("expires_at")
            preferences["gmail_connected"] = True
            user.preferences = preferences
            user.oauth_provider = "google"
            
            self.db.commit()
            logger.info(f"Gmail account connected for user {user.id}")
            return True
        
        except Exception as e:
            logger.error(f"Error connecting Gmail account: {e}")
            return False
    
    def get_gmail_client(self, user: User) -> Optional[GmailClient]:
        """
        Get authenticated Gmail client for user.
        
        Handles token refresh if needed.
        
        Args:
            user: User object with Gmail credentials
            
        Returns:
            GmailClient instance or None if not connected
        """
        if not user.preferences or not user.preferences.get("gmail_connected"):
            return None

        preferences = dict(user.preferences or {})
        access_token = preferences.get("gmail_access_token")
        refresh_token = preferences.get("gmail_refresh_token")
        expires_at = preferences.get("gmail_token_expires_at")

        if not access_token:
            return None

        def _is_expiring(raw_value: Any) -> bool:
            if raw_value is None:
                return False

            threshold = datetime.utcnow() + timedelta(minutes=5)
            if isinstance(raw_value, (int, float)):
                return datetime.utcfromtimestamp(raw_value) <= threshold

            if isinstance(raw_value, str):
                try:
                    if raw_value.isdigit():
                        return datetime.utcfromtimestamp(float(raw_value)) <= threshold

                    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    return parsed <= threshold
                except Exception:
                    logger.warning("Invalid gmail token expiry value for user %s", user.id)
                    return True

            return True
        
        # Check if token needs refresh
        if _is_expiring(expires_at):
            if refresh_token:
                try:
                    oauth_manager = self._get_oauth_manager()
                    if not oauth_manager:
                        return None

                    new_token_response = oauth_manager.refresh_access_token(refresh_token)
                    preferences["gmail_access_token"] = new_token_response["access_token"]
                    preferences["gmail_token_expires_at"] = new_token_response["expires_at"]
                    user.preferences = preferences
                    self.db.commit()
                    access_token = new_token_response["access_token"]
                except Exception as e:
                    logger.error(f"Error refreshing Gmail token: {e}")
                    # Treat refresh failures as disconnected so the user is guided to reconnect.
                    preferences["gmail_connected"] = False
                    preferences["gmail_access_token"] = None
                    user.preferences = preferences
                    self.db.commit()
                    return None
            else:
                preferences["gmail_connected"] = False
                user.preferences = preferences
                self.db.commit()
                return None
        
        try:
            return GmailClient(access_token)
        except Exception as e:
            logger.error(f"Error creating Gmail client: {e}")
            return None
    
    def fetch_latest_emails(
        self,
        user: User,
        limit: int = 20,
        label: str = "INBOX",
        unread_only: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch latest emails from user's Gmail.
        
        Args:
            user: User object
            limit: Number of emails to fetch
            label: Gmail label to fetch from
            unread_only: Only fetch unread emails
            
        Returns:
            List of email details or None if failed
        """
        gmail_client = self.get_gmail_client(user)
        if not gmail_client:
            logger.warning(f"Gmail client not available for user {user.id}")
            return None
        
        try:
            query = "is:unread" if unread_only else ""
            result = gmail_client.fetch_emails(
                label_name=label,
                max_results=limit,
                query=query,
            )

            # Store emails in database when schema is available.
            for email_data in result.get("emails", []):
                try:
                    self._store_email_in_db(user.id, email_data)
                except Exception as persist_error:
                    logger.warning(
                        "Skipping local email persistence for user %s: %s",
                        user.id,
                        persist_error,
                    )
            
            return result.get("emails", [])
        
        except Exception as e:
            logger.error(f"Error fetching emails for user {user.id}: {e}")
            return None
    
    def summarize_inbox(
        self,
        user: User,
        limit: int = 10,
        include_urgent_only: bool = False,
    ) -> Optional[EmailSummary]:
        """
        Summarize user's inbox using LLM.
        
        Args:
            user: User object
            limit: Number of emails to summarize
            include_urgent_only: Only summarize urgent emails
            
        Returns:
            EmailSummary object or None if failed
        """
        # Fetch latest emails
        emails = self.fetch_latest_emails(user, limit=limit)
        if not emails:
            return None
        
        # Classify urgency for each email
        urgent_emails = []
        regular_emails = []
        
        for email_data in emails:
            urgency = self._classify_email_urgency(
                user_id=user.id,
                subject=email_data["subject"],
                body=email_data.get("body_plain", "")[:500],
                from_address=email_data["from_address"],
            )
            
            email_obj = EmailMetadata(**email_data)
            
            if urgency["urgency_level"] in ["high", "critical"]:
                urgent_emails.append(email_obj)
                # Mark as important in Gmail
                gmail_client = self.get_gmail_client(user)
                if gmail_client:
                    try:
                        gmail_client.mark_as_important(email_data["id"])
                    except GmailInsufficientScopeError as mark_error:
                        logger.warning(
                            "Skipping important mark for user %s message %s due to missing Gmail scope: %s",
                            user.id,
                            email_data.get("id"),
                            mark_error,
                        )
                    except Exception as mark_error:
                        logger.warning(
                            "Failed to mark email as important for user %s message %s: %s",
                            user.id,
                            email_data.get("id"),
                            mark_error,
                        )
            else:
                regular_emails.append(email_obj)
        
        # Generate summary using LLM
        summary_text = self._generate_inbox_summary(user_id=user.id, emails=emails)
        
        # Extract key senders and action items
        key_senders = self._extract_key_senders(emails, limit=5)
        action_items = self._extract_action_items(emails)
        
        return EmailSummary(
            total_count=len(emails),
            unread_count=sum(1 for e in emails if e["is_unread"]),
            urgent_emails=urgent_emails if urgent_emails else None,
            summary_text=summary_text,
            key_senders=key_senders,
            action_items=action_items,
            trace_id="email-summary-" + datetime.utcnow().isoformat(),
        )
    
    def generate_draft_reply(
        self,
        user: User,
        email_id: str,
        recipient: Optional[str] = None,
        tone: str = "professional",
        context: Optional[str] = None,
    ) -> Optional[EmailDraft]:
        """
        Generate a draft reply to an email using LLM.
        
        Args:
            user: User object
            email_id: Gmail message ID to reply to
            recipient: Email recipient
            tone: Tone of reply (professional, casual, formal, friendly)
            context: Additional context for generation
            
        Returns:
            EmailDraft object or None if failed
        """
        normalized_email_id = (email_id or "").strip()
        if not normalized_email_id:
            return None

        # Fetch original email
        gmail_client = self.get_gmail_client(user)
        if not gmail_client:
            return None

        resolved_email_id = self._resolve_reply_email_id(
            user=user,
            gmail_client=gmail_client,
            email_id=normalized_email_id,
        )
        if not resolved_email_id:
            logger.warning(
                "Unable to resolve reply target email id '%s' for user %s",
                normalized_email_id,
                user.id,
            )
            return None
        
        email_details = gmail_client.get_message_details(resolved_email_id)
        if not email_details:
            return None

        resolved_recipient = (recipient or "").strip() or email_details.get("from_address")
        if not resolved_recipient:
            return None
        
        # Get thread ID from DB or API
        db_email = None
        try:
            db_email = self.db.query(Email).filter(
                Email.gmail_message_id == resolved_email_id,
                Email.user_id == user.id,
            ).first()
        except Exception as db_error:
            self.db.rollback()
            if "UndefinedTable" not in str(db_error):
                raise
            logger.warning(
                "Skipping local email lookup for draft generation user %s message %s: %s",
                user.id,
                resolved_email_id,
                db_error,
            )

        thread_id = (
            db_email.thread_id
            if db_email
            else email_details.get("thread_id") or resolved_email_id
        )
        
        # Generate draft using LLM
        draft_body, confidence = self._generate_draft_body(
            user_id=user.id,
            original_subject=email_details["subject"],
            original_body=email_details["body"],
            from_address=email_details["from_address"],
            tone=tone,
            context=context,
        )
        
        draft = EmailDraft(
            id="draft-" + datetime.utcnow().isoformat(),
            thread_id=thread_id,
            to_recipient=resolved_recipient,
            subject=None,  # Re: format handled client-side
            body=draft_body,
            tone=tone,
            confidence=confidence,
            metadata={
                "original_email_id": resolved_email_id,
                "requested_email_id": normalized_email_id,
                "context": context,
                "generated_at": datetime.utcnow().isoformat(),
            },
            created_at=datetime.utcnow(),
        )
        
        return draft

    def _resolve_reply_email_id(
        self,
        user: User,
        gmail_client: GmailClient,
        email_id: str,
    ) -> Optional[str]:
        """Resolve common planner aliases like latest/urgent into a real Gmail message ID."""
        normalized = (email_id or "").strip()
        if not normalized:
            return None

        lowered = normalized.lower()
        if lowered in self._LATEST_EMAIL_ALIASES:
            latest_emails = self.fetch_latest_emails(user, limit=1)
            if latest_emails:
                return latest_emails[0].get("id")
            return None

        if lowered in self._URGENT_EMAIL_ALIASES:
            recent_emails = self.fetch_latest_emails(user, limit=20)
            if not recent_emails:
                return None

            for email in recent_emails:
                urgency = self._classify_email_urgency(
                    user_id=user.id,
                    subject=email.get("subject", ""),
                    body=email.get("body_plain", "")[:500],
                    from_address=email.get("from_address", ""),
                )
                if urgency.get("urgency_level") in {"high", "critical"}:
                    return email.get("id")

            return recent_emails[0].get("id")

        return normalized
    
    def create_approval_for_draft(
        self,
        user: User,
        draft: EmailDraft,
        email_id: str,
    ) -> Optional[str]:
        """
        Create approval request for email draft.
        
        Args:
            user: User object
            draft: EmailDraft to approve
            email_id: Original email ID
            
        Returns:
            Approval ID or None if failed
        """
        action_payload = {
            "draft_id": draft.id,
            "thread_id": draft.thread_id,
            "to_recipient": draft.to_recipient,
            "subject": draft.subject or f"Re: {draft.subject}",
            "body": draft.body,
            "tone": draft.tone,
            "confidence": draft.confidence,
        }
        
        try:
            approval = Approval(
                user_id=user.id,
                approval_type=Approval.ApprovalType.SEND_EMAIL,
                action_description=f"Send email to {draft.to_recipient}",
                action_payload=action_payload,
                confidence_score=draft.confidence,
                expires_at=datetime.utcnow() + timedelta(minutes=15),
            )
            
            self.db.add(approval)
            self.db.commit()
            
            return approval.id
        
        except Exception as e:
            logger.error(f"Error creating approval: {e}")
            self.db.rollback()
            if "UndefinedTable" in str(e):
                logger.warning(
                    "Approval persistence unavailable for user %s draft %s; continuing without approval record",
                    user.id,
                    draft.id,
                )
            return None
    
    def send_approved_email(
        self,
        user: User,
        draft: EmailDraft,
        thread_id: str,
    ) -> Optional[str]:
        """
        Send approved email draft via Gmail.
        
        Args:
            user: User object
            draft: EmailDraft to send
            thread_id: Gmail thread ID
            
        Returns:
            Sent message ID or None if failed
        """
        gmail_client = self.get_gmail_client(user)
        if not gmail_client:
            return None
        
        try:
            message_id = gmail_client.send_message(
                to=draft.to_recipient,
                subject=draft.subject or "(no subject)",
                body=draft.body,
                thread_id=thread_id,
            )
            
            # Store sent email in DB
            if message_id:
                email_obj = Email(
                    user_id=user.id,
                    gmail_message_id=message_id,
                    subject=draft.subject or "(no subject)",
                    sender=user.email,
                    recipients=[draft.to_recipient],
                    body=draft.body,
                    status=Email.EmailStatus.SENT,
                    received_at=datetime.utcnow(),
                )
                self.db.add(email_obj)
                self.db.commit()
            
            return message_id
        
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return None
    
    # Private helper methods for LLM-based operations
    
    def _classify_email_urgency(
        self,
        user_id: str,
        subject: str,
        body: str,
        from_address: str,
    ) -> Dict[str, Any]:
        """Classify email urgency using LLM."""
        prompt = ChatPromptTemplate.from_template("""
        Analyze this email and classify its urgency level.
        
        From: {from_address}
        Subject: {subject}
        Body: {body}
        
        Respond with JSON:
        {{
            "urgency_level": "low|medium|high|critical",
            "reason": "brief explanation",
            "suggested_action": "recommended action or null"
        }}
        """)
        
        try:
            chain = prompt | self.llm | JsonOutputParser()
            payload = {
                "from_address": from_address,
                "subject": subject,
                "body": body,
            }
            result = chain.invoke(payload)

            prompt_tokens = self._estimate_tokens(f"{from_address}\n{subject}\n{body}")
            completion_tokens = self._estimate_tokens(json.dumps(result))
            self._record_llm_usage(
                user_id=user_id,
                model=settings.groq_execution_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                source="email_urgency_classification",
            )
            
            return result
        
        except Exception as e:
            logger.warning(f"Error classifying urgency: {e}")
            return {
                "urgency_level": "medium",
                "reason": "Classification failed, defaulting to medium",
                "suggested_action": None,
            }
    
    def _generate_draft_body(
        self,
        user_id: str,
        original_subject: str,
        original_body: str,
        from_address: str,
        tone: str = "professional",
        context: Optional[str] = None,
    ) -> tuple[str, float]:
        """Generate email draft body using LLM."""
        prompt = ChatPromptTemplate.from_template("""
        Generate an email reply in {tone} tone.
        
        Original email from: {from_address}
        Subject: {original_subject}
        Body: {original_body}
        
        {context_instruction}
        
        Respond with JSON:
        {{
            "draft_body": "generated email body",
            "confidence": 0.0-1.0
        }}
        """)
        
        context_instruction = ""
        if context:
            context_instruction = f"Additional context: {context}"
        else:
            context_instruction = "Write a professional, concise reply."
        
        try:
            chain = prompt | self.llm | JsonOutputParser()
            payload = {
                "tone": tone,
                "from_address": from_address,
                "original_subject": original_subject,
                "original_body": original_body[:1000],  # Limit for API
                "context_instruction": context_instruction,
            }
            result = chain.invoke(payload)

            prompt_tokens = self._estimate_tokens(
                f"{tone}\n{from_address}\n{original_subject}\n{original_body[:1000]}\n{context_instruction}"
            )
            completion_tokens = self._estimate_tokens(json.dumps(result))
            self._record_llm_usage(
                user_id=user_id,
                model=settings.groq_execution_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                source="email_draft_generation",
            )
            
            return (
                result.get("draft_body", ""),
                float(result.get("confidence", 0.7))
            )
        
        except Exception as e:
            logger.error(f"Error generating draft: {e}")
            return "(Unable to generate draft)", 0.0
    
    def _generate_inbox_summary(self, user_id: str, emails: List[Dict[str, Any]]) -> str:
        """Generate inbox summary using LLM."""
        email_summaries = []
        for email in emails[:10]:  # Limit to 10 for API
            summary = f"- {email['subject']} (from {email['from_address']})"
            if email.get("snippet"):
                summary += f": {email['snippet'][:100]}"
            email_summaries.append(summary)
        
        prompt = ChatPromptTemplate.from_template("""
        Generate a brief summary of the following emails:
        
        {email_list}
        
        Provide a 2-3 sentence summary of the key points and action items.
        """)
        
        try:
            chain = prompt | self.llm
            joined_email_list = "\n".join(email_summaries)
            result = chain.invoke({"email_list": joined_email_list})

            prompt_tokens = self._estimate_tokens(joined_email_list)
            completion_tokens = self._estimate_tokens(str(result.content))
            self._record_llm_usage(
                user_id=user_id,
                model=settings.groq_execution_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                source="inbox_summary_generation",
            )
            return result.content
        
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Unable to generate summary"
    
    def _extract_key_senders(
        self,
        emails: List[Dict[str, Any]],
        limit: int = 5,
    ) -> List[str]:
        """Extract key senders from emails."""
        sender_counts = {}
        for email in emails:
            sender = email.get("from_address", "Unknown")
            sender_counts[sender] = sender_counts.get(sender, 0) + 1
        
        return [sender for sender, _ in sorted(
            sender_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:limit]]
    
    def _extract_action_items(self, emails: List[Dict[str, Any]]) -> List[str]:
        """Extract action items from emails using keyword matching."""
        action_keywords = [
            "action needed",
            "please respond",
            "approval",
            "review",
            "feedback",
            "deadline",
            "asap",
            "urgent",
        ]
        
        action_items = []
        for email in emails:
            subject = (email.get("subject", "") + " " + email.get("body", "")).lower()
            for keyword in action_keywords:
                if keyword in subject and email["subject"] not in action_items:
                    action_items.append(email["subject"])
                    break
        
        return action_items[:5]
    
    def _store_email_in_db(self, user_id: str, email_data: Dict[str, Any]) -> None:
        """Store email in database if not already present."""
        existing = self.db.query(Email).filter(
            Email.gmail_message_id == email_data["id"]
        ).first()
        
        if existing:
            return
        
        email = Email(
            user_id=user_id,
            gmail_message_id=email_data["id"],
            subject=email_data.get("subject", "(No subject)"),
            sender=email_data.get("from_address"),
            recipients=email_data.get("to_addresses", []),
            body=email_data.get("body", ""),
            labels=email_data.get("labels", []),
            thread_id=email_data.get("thread_id"),
            received_at=email_data.get("timestamp", datetime.utcnow()),
            has_attachments=email_data.get("has_attachments", False),
        )
        
        self.db.add(email)
        self.db.commit()
