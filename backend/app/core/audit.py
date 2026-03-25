"""
Audit Logging Module

Implements comprehensive audit logging for compliance, security, and debugging.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ============================================================================
# AUDIT LOG ENUMS
# ============================================================================


class AuditActionType(str, Enum):
    """Types of auditable actions."""
    
    # Authentication
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    TOKEN_REFRESH = "token_refresh"
    PASSWORD_CHANGE = "password_change"
    OAUTH_CONNECT = "oauth_connect"
    
    # Authorization & Access
    RESOURCE_CREATED = "resource_created"
    RESOURCE_READ = "resource_read"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETED = "resource_deleted"
    PERMISSION_DENIED = "permission_denied"
    
    # Email Operations
    EMAIL_FETCH = "email_fetch"
    EMAIL_DRAFT = "email_draft"
    EMAIL_SEND = "email_send"
    EMAIL_APPROVED = "email_approved"
    EMAIL_REJECTED = "email_rejected"
    
    # Calendar Operations
    CALENDAR_FETCH = "calendar_fetch"
    CALENDAR_EVENT_CREATED = "calendar_event_created"
    CALENDAR_EVENT_UPDATED = "calendar_event_updated"
    CALENDAR_EVENT_DELETED = "calendar_event_deleted"
    
    # Task Operations
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_COMPLETED = "task_completed"
    
    # System Events
    CONFIG_CHANGED = "config_changed"
    ERROR_OCCURRED = "error_occurred"
    SECURITY_ALERT = "security_alert"


class AuditResourceType(str, Enum):
    """Types of resources being audited."""
    
    USER = "user"
    EMAIL = "email"
    CALENDAR = "calendar"
    CALENDAR_EVENT = "calendar_event"
    TASK = "task"
    APPROVAL = "approval"
    SESSION = "session"
    API_KEY = "api_key"
    INTEGRATION = "integration"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ============================================================================
# AUDIT LOG SCHEMAS
# ============================================================================


class AuditLogDetail(BaseModel):
    """Additional context for audit event."""
    
    key: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None


class AuditLogEntry(BaseModel):
    """Audit log entry schema."""
    
    # Identifiers
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(  # For linking request flows
        default_factory=lambda: str(uuid4())
    )
    
    # Timestamp
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Subject (who performed the action)
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    
    # Action Details
    action: AuditActionType
    resource_type: AuditResourceType
    resource_id: Optional[str] = None
    
    # Request Context
    http_method: Optional[str] = None
    http_path: Optional[str] = None
    http_status_code: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Result
    success: bool = True
    severity: AuditSeverity = AuditSeverity.INFO
    
    # Details
    details: list[AuditLogDetail] = Field(default_factory=list)
    error_message: Optional[str] = None
    
    # Approval Flow Context
    requires_approval: bool = False
    approval_status: Optional[str] = None  # pending, approved, rejected
    approved_by: Optional[str] = None
    approval_reason: Optional[str] = None
    
    class Config:
        use_enum_values = True


class ApprovalLog(BaseModel):
    """Approval workflow audit entry."""
    
    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    audit_id: str  # Link to original action
    
    # Requester
    requested_by: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Action Details
    action: AuditActionType
    resource_type: AuditResourceType
    resource_id: str
    
    # Approval Decision
    status: str  # pending, approved, rejected, expired
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_reason: Optional[str] = None
    
    # Details
    requested_details: dict[str, Any] = Field(default_factory=dict)
    approval_context: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


# ============================================================================
# AUDIT LOGGER
# ============================================================================


class AuditLogger:
    """
    Audit logging service.
    
    Usage:
        logger = AuditLogger(db)
        await logger.log_email_action(
            user_id="user123",
            action=AuditActionType.EMAIL_SEND,
            resource_id="email456",
            success=True,
            details=[
                AuditLogDetail(key="recipient", new_value="john@example.com")
            ],
        )
    """
    
    def __init__(self, db_session=None):
        """Initialize audit logger with optional database session."""
        self.db = db_session
    
    async def log(self, entry: AuditLogEntry) -> str:
        """
        Log audit entry to database.
        
        Args:
            entry: Audit log entry
        
        Returns:
            Audit ID
        """
        # TODO: Store in database
        # if self.db:
        #     audit_record = AuditLogModel(**entry.model_dump())
        #     self.db.add(audit_record)
        #     await self.db.commit()
        
        return entry.audit_id
    
    async def log_authentication(
        self,
        user_id: str,
        action: AuditActionType,
        success: bool,
        ip_address: str,
        user_agent: str,
        details: Optional[list[AuditLogDetail]] = None,
    ) -> str:
        """Log authentication event."""
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=AuditResourceType.SESSION,
            success=success,
            severity=AuditSeverity.WARNING if not success else AuditSeverity.INFO,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or [],
        )
        return await self.log(entry)
    
    async def log_authorization(
        self,
        user_id: str,
        action: AuditActionType,
        resource_type: AuditResourceType,
        resource_id: str,
        allowed: bool,
        details: Optional[list[AuditLogDetail]] = None,
    ) -> str:
        """Log authorization attempt."""
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            success=allowed,
            severity=AuditSeverity.WARNING if not allowed else AuditSeverity.DEBUG,
            details=details or [],
        )
        return await self.log(entry)
    
    async def log_email_action(
        self,
        user_id: str,
        action: AuditActionType,
        resource_id: str,
        success: bool,
        details: Optional[list[AuditLogDetail]] = None,
        requires_approval: bool = False,
        approval_status: Optional[str] = None,
    ) -> str:
        """Log email-related action."""
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=AuditResourceType.EMAIL,
            resource_id=resource_id,
            success=success,
            details=details or [],
            requires_approval=requires_approval,
            approval_status=approval_status,
        )
        return await self.log(entry)
    
    async def log_approval_action(
        self,
        user_id: str,
        action: AuditActionType,
        resource_type: AuditResourceType,
        resource_id: str,
        success: bool,
        details: Optional[list[AuditLogDetail]] = None,
        approved_by: Optional[str] = None,
        approval_reason: Optional[str] = None,
    ) -> str:
        """Log approval workflow action."""
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            success=success,
            details=details or [],
            requires_approval=True,
            approval_status="approved" if success else "rejected",
            approved_by=approved_by,
            approval_reason=approval_reason,
        )
        return await self.log(entry)
    
    async def log_error(
        self,
        user_id: Optional[str],
        action: AuditActionType,
        resource_type: AuditResourceType,
        error_message: str,
        details: Optional[list[AuditLogDetail]] = None,
    ) -> str:
        """Log error event."""
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            success=False,
            severity=AuditSeverity.CRITICAL,
            error_message=error_message,
            details=details or [],
        )
        return await self.log(entry)


# ============================================================================
# AUDIT LOG QUERY HELPERS
# ============================================================================


class AuditQuery:
    """Helper for querying audit logs."""
    
    def __init__(self, db_session=None):
        """Initialize with database session."""
        self.db = db_session
    
    async def get_user_activity(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """Get all audit logs for a user."""
        # TODO: Query from database filtered by user_id
        # SELECT * FROM audit_logs WHERE user_id = ? ORDER BY timestamp DESC
        pass
    
    async def get_resource_history(
        self,
        resource_type: AuditResourceType,
        resource_id: str,
    ) -> list[AuditLogEntry]:
        """Get all changes to a specific resource."""
        # TODO: Query from database
        pass
    
    async def get_approval_history(
        self,
        resource_id: str,
    ) -> list[ApprovalLog]:
        """Get approval workflow history for a resource."""
        # TODO: Query from database
        pass
    
    async def get_failed_access_attempts(
        self,
        user_id: str,
        minutes: int = 30,
    ) -> list[AuditLogEntry]:
        """Get recent failed access attempts (for security monitoring)."""
        # TODO: Query from database
        pass
