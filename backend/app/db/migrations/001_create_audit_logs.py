"""Database migration: Create audit logs table

Revision ID: 001_create_audit_logs
Create Date: 2026-03-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    """Create audit_logs table."""
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('audit_id', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('trace_id', sa.String(255), index=True),
        
        # Timestamp
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True, server_default=sa.func.now()),
        
        # Subject (who performed the action)
        sa.Column('user_id', sa.String(255), index=True),
        sa.Column('user_email', sa.String(255)),
        
        # Action Details
        sa.Column('action', sa.String(50), nullable=False, index=True),
        sa.Column('resource_type', sa.String(50), nullable=False, index=True),
        sa.Column('resource_id', sa.String(255), index=True),
        
        # Request Context
        sa.Column('http_method', sa.String(10)),
        sa.Column('http_path', sa.String(500)),
        sa.Column('http_status_code', sa.Integer),
        sa.Column('ip_address', sa.String(50)),
        sa.Column('user_agent', sa.String(500)),
        
        # Result
        sa.Column('success', sa.Boolean, nullable=False, default=True),
        sa.Column('severity', sa.String(20), nullable=False, default='info'),
        
        # Details (JSON)
        sa.Column('details', postgresql.JSONB, default=dict),
        sa.Column('error_message', sa.Text),
        
        # Approval Context
        sa.Column('requires_approval', sa.Boolean, default=False),
        sa.Column('approval_status', sa.String(20)),
        sa.Column('approved_by', sa.String(255)),
        sa.Column('approval_reason', sa.Text),
    )
    
    # Create indexes for common queries
    op.create_index('idx_audit_user_timestamp', 'audit_logs', ['user_id', 'timestamp'], postgresql_using='btree')
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'], postgresql_using='btree')
    op.create_index('idx_audit_action', 'audit_logs', ['action', 'timestamp'], postgresql_using='btree')


def downgrade() -> None:
    """Drop audit_logs table."""
    op.drop_table('audit_logs')
