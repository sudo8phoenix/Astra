"""
Gmail API integration for OAuth and email operations.

Handles:
- OAuth 2.0 flow for Gmail access
- Email fetching from Gmail API
- Email sending via Gmail API
- OAuth token storage and refresh
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import base64
import re
from time import perf_counter

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httpx

from app.core.config import settings
from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.core.retry import RetryExhaustedError, retry_sync

logger = logging.getLogger(__name__)


class GmailOAuthManager:
    """Manages Gmail OAuth 2.0 flow and token lifecycle."""
    
    SCOPES = settings.gmail_api_scopes.split(",")
    
    def __init__(self):
        """Initialize OAuth manager with Google credentials."""
        if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
            raise ValueError("Google OAuth credentials not configured in settings")
        
        self.client_id = settings.google_oauth_client_id
        self.client_secret = settings.google_oauth_client_secret
        self.redirect_uri = settings.google_oauth_redirect_uri

    def _build_oauth_flow(self) -> Flow:
        """Create a configured OAuth flow used by both auth URL and code exchange."""
        return Flow.from_client_config(
            {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uris": [self.redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
        )
    
    def get_auth_url(self, state: str = "") -> tuple[str, str]:
        """
        Generate Google OAuth authorization URL.
        
        Args:
            state: Optional state parameter for security
            
        Returns:
            Tuple of (auth_url, flow_instance_serialized)
        """
        flow = self._build_oauth_flow()
        
        auth_url, _ = flow.authorization_url(
            state=state,
            access_type="offline",
            prompt="consent"
        )
        
        return auth_url
    
    def exchange_code_for_token(self, auth_code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            auth_code: Authorization code from Google OAuth callback
            
        Returns:
            Token response dictionary with access_token, refresh_token, etc.
        """
        trace_id = get_trace_id() or "N/A"
        start = perf_counter()
        attempts = 1
        flow = self._build_oauth_flow()
        
        try:
            _, attempts = retry_sync(
                operation=lambda: flow.fetch_token(code=auth_code),
                exceptions=(Exception,),
                max_attempts=3,
                base_delay=0.4,
                backoff_factor=2.0,
            )
        except RetryExhaustedError:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="gmail_oauth",
                operation="exchange_code_for_token",
                status="error",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.error(
                "gmail.oauth.exchange.failed",
                extra={"trace_id": trace_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            raise

        duration_ms = (perf_counter() - start) * 1000
        metrics_collector.record_external_call(
            service="gmail_oauth",
            operation="exchange_code_for_token",
            status="success",
            duration_ms=duration_ms,
            attempts=attempts,
        )
        credentials = flow.credentials
        
        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_at": credentials.expiry.timestamp() if credentials.expiry else None,
            "token_type": "Bearer",
        }
    
    @staticmethod
    def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
        """
        Refresh expired access token using refresh token.
        
        Args:
            refresh_token: Refresh token from previous OAuth flow
            
        Returns:
            New token response with updated access_token and expiry
        """
        trace_id = get_trace_id() or "N/A"
        start = perf_counter()
        attempts = 1
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
        )
        
        try:
            _, attempts = retry_sync(
                operation=lambda: credentials.refresh(Request()),
                exceptions=(Exception,),
                max_attempts=3,
                base_delay=0.4,
                backoff_factor=2.0,
            )
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="gmail_oauth",
                operation="refresh_access_token",
                status="success",
                duration_ms=duration_ms,
                attempts=attempts,
            )
        except RetryExhaustedError:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="gmail_oauth",
                operation="refresh_access_token",
                status="error",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.error(
                "gmail.oauth.refresh.failed",
                extra={"trace_id": trace_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            raise
        
        return {
            "access_token": credentials.token,
            "refresh_token": refresh_token,
            "expires_at": credentials.expiry.timestamp() if credentials.expiry else None,
            "token_type": "Bearer",
        }


class GmailClient:
    """Gmail API client for fetching and sending emails."""
    
    def __init__(self, access_token: str):
        """
        Initialize Gmail client with access token.
        
        Args:
            access_token: OAuth access token for Gmail API
        """
        self.access_token = access_token
        self.service = build(
            "gmail",
            "v1",
            credentials=Credentials(token=access_token),
            cache_discovery=False,
        )

    def _execute_with_retry(self, operation: str, fn):
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        attempts = 1
        try:
            result, attempts = retry_sync(
                operation=fn,
                exceptions=(HttpError,),
                max_attempts=3,
                base_delay=0.4,
                backoff_factor=2.0,
            )
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="gmail_api",
                operation=operation,
                status="success",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.info(
                "gmail.external_call.success",
                extra={
                    "trace_id": trace_id,
                    "operation": operation,
                    "duration_ms": round(duration_ms, 2),
                    "attempts": attempts,
                },
            )
            return result
        except RetryExhaustedError:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="gmail_api",
                operation=operation,
                status="error",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.error(
                "gmail.external_call.retry_exhausted",
                extra={
                    "trace_id": trace_id,
                    "operation": operation,
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            raise
    
    def fetch_emails(
        self,
        label_name: str = "INBOX",
        max_results: int = 10,
        query: str = "",
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch emails from Gmail.
        
        Args:
            label_name: Gmail label (INBOX, SENT, DRAFT, SPAM, TRASH, STARRED)
            max_results: Maximum number of emails to fetch
            query: Gmail search query (https://support.google.com/mail/answer/7190)
            page_token: Pagination token from previous response
            
        Returns:
            Dictionary with messages list and pagination info
        """
        try:
            # Get label ID
            labels = self._execute_with_retry(
                "list_labels",
                lambda: self.service.users().labels().list(userId="me").execute(),
            )
            label_id = None
            for label in labels.get("labels", []):
                if label["name"] == label_name:
                    label_id = label["id"]
                    break
            
            if not label_id and label_name != "INBOX":
                logger.warning(f"Label {label_name} not found, using INBOX")
                label_name = "INBOX"
            
            # Build query
            full_query = query
            if label_name and label_name != "INBOX":
                full_query += f" label:{label_name}"
            
            # Fetch messages
            results = self._execute_with_retry(
                "list_messages",
                lambda: self.service.users().messages().list(
                    userId="me",
                    q=full_query,
                    maxResults=min(max_results, 100),  # API limit is 100
                    pageToken=page_token,
                ).execute(),
            )
            
            messages = results.get("messages", [])
            
            # Fetch full message details
            email_list = []
            for message in messages:
                email_details = self.get_message_details(message["id"])
                if email_details:
                    email_list.append(email_details)
            
            return {
                "emails": email_list,
                "total_count": results.get("resultSizeEstimate", len(email_list)),
                "next_page_token": results.get("nextPageToken"),
            }
        
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            raise
    
    def get_message_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full message details for a single email.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Dictionary with email details
        """
        try:
            message = self._execute_with_retry(
                "get_message_details",
                lambda: self.service.users().messages().get(
                    userId="me",
                    id=message_id,
                    format="full",
                ).execute(),
            )
            
            headers = message["payload"].get("headers", [])
            header_dict = {h["name"]: h["value"] for h in headers}
            
            # Extract parts
            body = ""
            body_plain = ""
            attachments = []
            
            if "parts" in message["payload"]:
                for part in message["payload"]["parts"]:
                    if part["mimeType"] == "text/plain":
                        data = part["body"].get("data", "")
                        if data:
                            body_plain = base64.urlsafe_b64decode(data).decode("utf-8")
                    elif part["mimeType"] == "text/html":
                        data = part["body"].get("data", "")
                        if data:
                            body = base64.urlsafe_b64decode(data).decode("utf-8")
                    elif "filename" in part:
                        attachments.append({
                            "filename": part["filename"],
                            "mime_type": part["mimeType"],
                            "size": part["body"].get("size", 0),
                        })
            else:
                data = message["payload"]["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8")
                    body_plain = body
            
            # Parse recipients
            to_addresses = header_dict.get("To", "").split(",") if "To" in header_dict else []
            cc_addresses = header_dict.get("Cc", "").split(",") if "Cc" in header_dict else []
            bcc_addresses = header_dict.get("Bcc", "").split(",") if "Bcc" in header_dict else []
            
            to_addresses = [addr.strip() for addr in to_addresses if addr.strip()]
            cc_addresses = [addr.strip() for addr in cc_addresses if addr.strip()]
            bcc_addresses = [addr.strip() for addr in bcc_addresses if addr.strip()]
            
            return {
                "id": message_id,
                "thread_id": message["threadId"],
                "from_address": header_dict.get("From", ""),
                "from_name": self._extract_name_from_email(header_dict.get("From", "")),
                "to_addresses": to_addresses,
                "cc_addresses": cc_addresses,
                "bcc_addresses": bcc_addresses,
                "subject": header_dict.get("Subject", "(No subject)"),
                "snippet": message.get("snippet", ""),
                "body": body or body_plain,
                "body_plain": body_plain,
                "timestamp": datetime.fromtimestamp(int(message["internalDate"]) / 1000),
                "labels": message.get("labelIds", []),
                "is_unread": "UNREAD" in message.get("labelIds", []),
                "is_starred": "STARRED" in message.get("labelIds", []),
                "has_attachments": len(attachments) > 0,
                "attachments": attachments if attachments else None,
            }
        
        except HttpError as error:
            logger.error(f"Error fetching message {message_id}: {error}")
            return None
    
    @staticmethod
    def _extract_name_from_email(email_str: str) -> Optional[str]:
        """Extract display name from email string 'Name <email@domain.com>'."""
        match = re.match(r"(.+?)\s*<(.+?)>", email_str)
        if match:
            return match.group(1).strip()
        return None
    
    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        in_reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send an email via Gmail API.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
            thread_id: Gmail thread ID (for threading)
            cc: List of CC addresses
            bcc: List of BCC addresses
            in_reply_to_message_id: Message ID to reply to
            
        Returns:
            Sent message ID or None if failed
        """
        try:
            import email
            from email.mime.text import MIMEText
            
            message = email.mime.multipart.MIMEMultipart("alternative")
            message["to"] = to
            message["subject"] = subject
            if cc:
                message["cc"] = ", ".join(cc)
            if bcc:
                message["bcc"] = ", ".join(bcc)
            if in_reply_to_message_id:
                message["In-Reply-To"] = in_reply_to_message_id
            
            part = MIMEText(body, "html" if "<html>" in body.lower() else "plain")
            message.attach(part)
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            send_message = {"raw": raw_message}
            if thread_id:
                send_message["threadId"] = thread_id
            
            sent = self._execute_with_retry(
                "send_message",
                lambda: self.service.users().messages().send(
                    userId="me",
                    body=send_message,
                ).execute(),
            )
            
            logger.info(f"Email sent successfully: {sent['id']}")
            return sent["id"]
        
        except HttpError as error:
            logger.error(f"Error sending email: {error}")
            return None
    
    def mark_as_read(self, message_id: str) -> bool:
        """Mark email as read."""
        try:
            self._execute_with_retry(
                "mark_as_read",
                lambda: self.service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute(),
            )
            return True
        except HttpError as error:
            logger.error(f"Error marking message as read: {error}")
            return False
    
    def mark_as_important(self, message_id: str) -> bool:
        """Mark email as important/starred."""
        try:
            self._execute_with_retry(
                "mark_as_important",
                lambda: self.service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": ["STARRED"]},
                ).execute(),
            )
            return True
        except HttpError as error:
            logger.error(f"Error marking message as important: {error}")
            return False
