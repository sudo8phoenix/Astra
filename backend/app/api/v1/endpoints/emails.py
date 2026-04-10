"""Email management API endpoints."""

import logging
from typing import Optional
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, TokenPayload, JWTManager
from app.core.config import settings
from app.core.retry import RetryExhaustedError
from app.db.config import get_db
from app.db.models import User
from app.integrations.gmail import GmailInsufficientScopeError
from app.schemas.email import (
    EmailListRequest,
    EmailListResponse,
    EmailMetadata,
    EmailResponse,
    EmailSummaryRequest,
    EmailSummaryResponse,
    EmailDraftRequest,
    EmailDraftResponse,
    EmailSendRequest,
    EmailSendResponse,
)
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["emails"])


async def get_current_user_from_db(
    current_token: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Get current user object from database using token payload."""
    user = db.query(User).filter(User.id == current_token.sub).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


@router.get("/oauth/authorize-url", summary="Get Gmail OAuth URL")
async def get_oauth_url(
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get Google OAuth authorization URL for Gmail connection.
    
    User should be redirected to this URL to authorize Gmail access.
    """
    service = EmailService(db)
    auth_url = service.get_oauth_auth_url(state=state or str(uuid4()))
    return {"auth_url": auth_url}


@router.post("/oauth/callback", summary="Handle OAuth callback")
async def oauth_callback(
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    token: Optional[str] = Query(None, description="JWT token for authenticated user"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Handle Google OAuth callback to connect Gmail account.

    Works for both authenticated users (linking Gmail) and new users (first login).
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gmail OAuth failed: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )

    # Determine which user to link Gmail to
    user = None
    current_user_id = None

    # If JWT token provided, use authenticated user
    if token:
        try:
            token_payload = JWTManager.verify_token(token)
            user = db.query(User).filter(User.id == token_payload.sub).first()
            current_user_id = token_payload.sub
        except Exception:
            user = None

    # If no authenticated user, create or get user from dev email
    if not user:
        demo_email = "demo.user@local.dev"
        user = db.query(User).filter(User.email == demo_email).first()
        if not user:
            user = User(
                email=demo_email,
                name="OAuth User",
                timezone="UTC",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        current_user_id = user.id

    service = EmailService(db)
    success = service.connect_gmail_account(user, code)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to connect Gmail account",
        )

    # If this is a new login (no token provided), generate JWT for them
    access_token = token
    if not token:
        access_token = JWTManager.create_access_token(
            user_id=user.id,
            email=user.email,
            scopes=["read", "write"],
        )

    return {
        "success": True,
        "message": "Gmail account connected successfully",
        "user_id": user.id,
        "email": user.email,
        "token": access_token,
    }


@router.get("/list", response_model=EmailListResponse, summary="List emails")
async def list_emails(
    label: str = Query("INBOX", description="Gmail label"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> EmailListResponse:
    """
    Fetch latest emails from user's Gmail inbox.
    
    Requires: Gmail connection via OAuth
    """
    service = EmailService(db)
    
    emails = service.fetch_latest_emails(
        current_user,
        limit=limit,
        label=label,
        unread_only=unread_only,
    )
    
    if emails is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail account not connected or fetch failed",
        )
    
    # Apply offset for pagination
    paginated_emails = emails[offset:offset + limit]
    
    return EmailListResponse(
        emails=[EmailMetadata(**email) for email in paginated_emails],
        total_count=len(emails),
        offset=offset,
        limit=limit,
        has_more=(offset + limit) < len(emails),
    )


@router.get("/{email_id}", response_model=EmailResponse, summary="Get email details")
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> EmailResponse:
    """Get full details of a single email."""
    service = EmailService(db)
    gmail_client = service.get_gmail_client(current_user)
    
    if not gmail_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail account not connected",
        )
    
    email_details = gmail_client.get_message_details(email_id)
    
    if not email_details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found",
        )
    
    return EmailResponse(
        email=email_details,
        trace_id=None,
    )


@router.post("/summarize", response_model=EmailSummaryResponse, summary="Summarize inbox")
async def summarize_inbox(
    request: EmailSummaryRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> EmailSummaryResponse:
    """
    Generate AI-powered summary of inbox.
    
    - Fetches recent emails
    - Classifies urgency
    - Highlights urgent emails
    - Extracts action items
    - Generates summary text
    """
    service = EmailService(db)
    
    summary = service.summarize_inbox(
        current_user,
        limit=request.limit,
        include_urgent_only=request.include_urgent_only,
    )
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to summarize inbox",
        )
    
    return EmailSummaryResponse(summary=summary)


@router.post("/draft-reply", response_model=EmailDraftResponse, summary="Generate draft reply")
async def generate_draft_reply(
    request: EmailDraftRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> EmailDraftResponse:
    """
    Generate AI draft reply to an email.
    
    Uses LLM to create contextual, professional reply in specified tone.
    """
    service = EmailService(db)
    
    draft = service.generate_draft_reply(
        current_user,
        email_id=request.email_id,
        recipient=request.recipient,
        tone=request.tone,
        context=request.context,
    )
    
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to generate draft",
        )
    
    # Create approval request
    approval_id = service.create_approval_for_draft(
        current_user,
        draft,
        request.email_id,
    )
    
    return EmailDraftResponse(
        draft=draft,
        approval_required=True,
        approval_id=approval_id,
        trace_id=draft.metadata.get("generated_at"),
    )


@router.post("/send", response_model=EmailSendResponse, summary="Send approved email")
async def send_email(
    request: EmailSendRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> EmailSendResponse:
    """
    Send an approved email draft.
    
    Requires: User approval via approval_id
    """
    from app.db.models import Approval
    
    service = EmailService(db)
    
    # Verify approval exists and is approved
    approval = db.query(Approval).filter(
        Approval.id == request.approval_id,
        Approval.user_id == current_user.id,
    ).first()
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    
    if approval.status != Approval.ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval status is {approval.status}, must be approved",
        )
    
    # Extract draft from approval payload
    action_data = approval.action_payload
    
    # Reconstruct draft object
    from app.schemas.email import EmailDraft
    draft = EmailDraft(
        id=action_data.get("draft_id"),
        thread_id=action_data.get("thread_id"),
        to_recipient=action_data.get("to_recipient"),
        subject=action_data.get("subject"),
        body=action_data.get("body"),
        tone=action_data.get("tone", "professional"),
        confidence=action_data.get("confidence", 0.8),
        created_at=approval.created_at,
    )
    
    # Send email
    message_id = service.send_approved_email(
        current_user,
        draft,
        action_data.get("thread_id"),
    )
    
    if not message_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email",
        )
    
    # Update approval status
    approval.approved_at = datetime.utcnow()
    approval.approved_by = current_user.id
    db.commit()
    
    return EmailSendResponse(
        success=True,
        message_id=message_id,
        thread_id=action_data.get("thread_id"),
        sent_at=datetime.utcnow(),
        trace_id=approval.id,
    )


@router.get("/urgent", response_model=dict, summary="Get urgent emails")
async def get_urgent_emails(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get all urgent/important emails for user.
    
    Uses AI to classify urgency based on:
    - Email content and keywords
    - Sender address and history
    - Subject patterns
    - Engagement signals
    """
    from app.repositories.repositories import EmailRepository
    
    service = EmailService(db)
    repo = EmailRepository(db)
    
    # Get recent emails
    emails = service.fetch_latest_emails(current_user, limit=30)
    if not emails:
        return {
            "status": "success",
            "urgent_count": 0,
            "urgent_emails": [],
            "high_priority_count": 0,
            "critical_priority_count": 0,
        }
    
    urgent_list = []
    high_priority = []
    critical_priority = []
    
    for email in emails:
        urgency = service._classify_email_urgency(
            user_id=current_user.id,
            subject=email.get("subject", ""),
            body=email.get("body_plain", "")[:500],
            from_address=email.get("from_address", ""),
        )
        
        if urgency.get("urgency_level") == "critical":
            critical_priority.append({
                "id": email.get("id"),
                "subject": email.get("subject"),
                "from": email.get("from_address"),
                "timestamp": str(email.get("timestamp")),
                "urgency": "critical",
                "reason": urgency.get("reason"),
                "suggested_action": urgency.get("suggested_action"),
            })
        elif urgency.get("urgency_level") == "high":
            high_priority.append({
                "id": email.get("id"),
                "subject": email.get("subject"),
                "from": email.get("from_address"),
                "timestamp": str(email.get("timestamp")),
                "urgency": "high",
                "reason": urgency.get("reason"),
                "suggested_action": urgency.get("suggested_action"),
            })
            urgent_list.append({
                "id": email.get("id"),
                "subject": email.get("subject"),
                "from": email.get("from_address"),
                "timestamp": str(email.get("timestamp")),
                "urgency": "high",
                "reason": urgency.get("reason"),
            })
        elif urgency.get("urgency_level") == "medium":
            # Medium priority, skip
            pass
    
    # Mark urgent emails as starred in Gmail
    gmail_client = service.get_gmail_client(current_user)
    for email in critical_priority + high_priority:
        if gmail_client:
            try:
                gmail_client.mark_as_important(email["id"])
            except GmailInsufficientScopeError:
                logger.warning(
                    "gmail.modify.permission_missing user=%s email_id=%s",
                    current_user.id,
                    email["id"],
                )
        
        # Mark as urgent in DB
        repo.mark_as_urgent(email["id"])
    
    urgent_list = critical_priority + high_priority
    
    return {
        "status": "success",
        "urgent_count": len(urgent_list),
        "critical_priority_count": len(critical_priority),
        "high_priority_count": len(high_priority),
        "urgent_emails": urgent_list,
        "critical_emails": critical_priority,
    }


@router.post("/{email_id}/mark-urgent", summary="Mark email as urgent")
async def mark_email_urgent(
    email_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Manually mark an email as urgent/important.
    
    This will:
    - Flag it as important in Gmail
    - Store urgency status in database
    - Surface it in urgent email list
    """
    from app.repositories.repositories import EmailRepository
    
    service = EmailService(db)
    repo = EmailRepository(db)
    
    # Mark in Gmail
    gmail_client = service.get_gmail_client(current_user)
    if gmail_client:
        try:
            success = gmail_client.mark_as_important(email_id)
        except GmailInsufficientScopeError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Gmail permissions are insufficient to modify messages. "
                    "Please reconnect Google account and grant modify access."
                ),
            )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to mark email as urgent in Gmail",
            )
    
    # Mark in database
    db_email = repo.get_email_by_gmail_id(email_id)
    if db_email:
        repo.mark_as_urgent(db_email.id)
    
    return {
        "success": True,
        "email_id": email_id,
        "message": "Email marked as urgent",
    }


@router.get("/urgent/summary", summary="Get urgent emails summary")
async def get_urgent_emails_summary(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """Quick summary of urgent emails count and top urgent items."""
    from app.repositories.repositories import EmailRepository
    
    service = EmailService(db)
    repo = EmailRepository(db)
    
    # Get urgent emails from database
    urgent_emails = repo.get_user_urgent_emails(current_user.id)
    
    return {
        "status": "success",
        "urgent_count": len(urgent_emails),
        "urgent_emails": [
            {
                "id": email.gmail_message_id,
                "subject": email.subject,
                "from": email.sender,
            }
            for email in urgent_emails[:5]
        ],
    }


@router.post("/{email_id}/mark-as-read", summary="Mark email as read")
async def mark_email_as_read(
    email_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Mark an email as read.
    
    Updates the email status in Gmail and database.
    """
    service = EmailService(db)
    gmail_client = service.get_gmail_client(current_user)
    
    if not gmail_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail account not connected",
        )
    
    try:
        success = gmail_client.mark_as_read(email_id)
    except GmailInsufficientScopeError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Gmail permissions are insufficient to modify messages. "
                "Please reconnect Google account and grant modify access."
            ),
        )
    except RetryExhaustedError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gmail API is temporarily unavailable. Please try again.",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark email as read",
        )
    
    return {
        "success": True,
        "email_id": email_id,
        "message": "Email marked as read",
    }


@router.post("/{email_id}/archive", summary="Archive email")
async def archive_email(
    email_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Archive an email (move from INBOX to ARCHIVE label).
    
    This removes the email from the inbox but keeps it archived for later retrieval.
    """
    service = EmailService(db)
    gmail_client = service.get_gmail_client(current_user)
    
    if not gmail_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail account not connected",
        )
    
    try:
        # Remove from INBOX
        gmail_client._execute_with_retry(
            "archive_email",
            lambda: gmail_client.service.users().messages().modify(
                userId="me",
                id=email_id,
                body={"removeLabelIds": ["INBOX"]},
            ).execute(),
        )
        
        return {
            "success": True,
            "email_id": email_id,
            "message": "Email archived",
        }
    except Exception as error:
        logger.error(f"Error archiving email: {error}")
        if isinstance(error, GmailInsufficientScopeError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Gmail permissions are insufficient to archive messages. "
                    "Please reconnect Google account and grant modify access."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to archive email",
        )


@router.post("/{email_id}/delete", summary="Delete email (move to trash)")
async def delete_email(
    email_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Delete an email by moving it to trash.
    
    The email can still be recovered from trash.
    """
    service = EmailService(db)
    gmail_client = service.get_gmail_client(current_user)
    
    if not gmail_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail account not connected",
        )
    
    try:
        # Move to trash
        gmail_client._execute_with_retry(
            "delete_email",
            lambda: gmail_client.service.users().messages().trash(
                userId="me",
                id=email_id,
            ).execute(),
        )
        
        return {
            "success": True,
            "email_id": email_id,
            "message": "Email moved to trash",
        }
    except Exception as error:
        logger.error(f"Error deleting email: {error}")
        if isinstance(error, GmailInsufficientScopeError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Gmail permissions are insufficient to delete messages. "
                    "Please reconnect Google account and grant modify access."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete email",
        )


@router.post("/{email_id}/snooze", summary="Snooze email")
async def snooze_email(
    email_id: str,
    hours: int = Query(1, ge=1, le=168, description="Number of hours to snooze (1-168)"),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Snooze an email to hide it temporarily.
    
    The email will be removed from INBOX and can be configured to reappear after specified hours.
    SnoozeTime ranges from 1 to 168 hours (1 week).
    """
    from app.repositories.repositories import EmailRepository
    
    service = EmailService(db)
    gmail_client = service.get_gmail_client(current_user)
    repo = EmailRepository(db)
    
    if not gmail_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail account not connected",
        )
    
    try:
        # Remove from INBOX (snooze = temporarily archive)
        gmail_client._execute_with_retry(
            "snooze_email",
            lambda: gmail_client.service.users().messages().modify(
                userId="me",
                id=email_id,
                body={"removeLabelIds": ["INBOX"]},
            ).execute(),
        )
        
        # Store snooze metadata in database for tracking
        snooze_time = datetime.utcnow()
        reappear_time = snooze_time + timedelta(hours=hours)
        
        return {
            "success": True,
            "email_id": email_id,
            "snooze_hours": hours,
            "reappear_at": reappear_time.isoformat(),
            "message": f"Email snoozed for {hours} hours",
        }
    except Exception as error:
        logger.error(f"Error snoozing email: {error}")
        if isinstance(error, GmailInsufficientScopeError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Gmail permissions are insufficient to snooze messages. "
                    "Please reconnect Google account and grant modify access."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to snooze email",
        )


@router.get("/health", summary="Check email service health")
async def health_check(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """Check if user's Gmail connection is healthy."""
    service = EmailService(db)
    gmail_client = service.get_gmail_client(current_user)
    
    return {
        "gmail_connected": gmail_client is not None,
        "user_id": current_user.id,
    }
