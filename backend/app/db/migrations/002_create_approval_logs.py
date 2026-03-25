"""Database migration: Create approval logs table

Revision ID: 002_create_approval_logs
Create Date: 2026-03-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    """Create approval_logs table for workflow approvals."""
    op.create_table(
        'approval_logs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('approval_id', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('audit_id', sa.String(255), index=True),  # Link to audit log
        
        # Requester
        sa.Column('requested_by', sa.String(255), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        
        # Action Details
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(255), nullable=False),
        
        # Approval Decision
        sa.Column('status', sa.String(20), nullable=False, default='pending', index=True),
        sa.Column('decided_by', sa.String(255)),
        sa.Column('decided_at', sa.DateTime(timezone=True)),
        sa.Column('decision_reason', sa.Text),
        
        # Details
        sa.Column('requested_details', postgresql.JSONB, default=dict),
        sa.Column('approval_context', postgresql.JSONB, default=dict),
    )
    
    # Create indexes
    op.create_index('idx_approval_resource', 'approval_logs', ['resource_type', 'resource_id'], postgresql_using='btree')
    op.create_index('idx_approval_status_time', 'approval_logs', ['status', 'requested_at'], postgresql_using='btree')
    op.create_index('idx_approval_requester', 'approval_logs', ['requested_by'], postgresql_using='btree')


def downgrade() -> None:
    """Drop approval_logs table."""
    op.drop_table('approval_logs')
