"""Create initial schema for AI Assistant

Revision ID: 001_create_initial_schema
Revises: 
Create Date: 2026-03-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_create_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    # Create users table when schema was not pre-initialized outside Alembic.
    if not inspector.has_table('users'):
        op.create_table(
            'users',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('timezone', sa.String(50), nullable=False, server_default='UTC'),
            sa.Column('oauth_provider', sa.String(50), nullable=True),
            sa.Column('oauth_id', sa.String(255), nullable=True),
            sa.Column('preferences', postgresql.JSON(), nullable=True, server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email'),
            sa.UniqueConstraint('oauth_id'),
        )
        op.create_index('idx_user_email', 'users', ['email'])
        op.create_index('idx_user_oauth', 'users', ['oauth_provider', 'oauth_id'])

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.Enum('high', 'medium', 'low', name='prioritylevel'), nullable=False, server_default='medium'),
        sa.Column('status', sa.Enum('todo', 'in_progress', 'completed', 'cancelled', name='taskstatus'), nullable=False, server_default='todo'),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('ai_generated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_metadata', postgresql.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_task_user_status', 'tasks', ['user_id', 'status'])
    op.create_index('idx_task_user_due', 'tasks', ['user_id', 'due_date'])
    op.create_check_constraint('ck_completed_at_check', 'tasks', "completed_at IS NULL OR status = 'completed'")

    # Create calendar_events table
    op.create_table(
        'calendar_events',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('google_event_id', sa.String(255), nullable=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('scheduled', 'confirmed', 'tentative', 'cancelled', name='eventstatus'), nullable=False, server_default='scheduled'),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('all_day', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('attendees', postgresql.JSON(), nullable=True),
        sa.Column('color_id', sa.String(50), nullable=True),
        sa.Column('reminders', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_event_id'),
    )
    op.create_index('idx_calendar_user_start', 'calendar_events', ['user_id', 'start_time'])
    op.create_check_constraint('ck_time_check', 'calendar_events', 'start_time < end_time')

    # Create emails table
    op.create_table(
        'emails',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('gmail_message_id', sa.String(255), nullable=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('sender', sa.String(255), nullable=True),
        sa.Column('recipients', postgresql.JSON(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('draft_reply', sa.Text(), nullable=True),
        sa.Column('is_urgent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.Enum('received', 'draft', 'sent', 'marked_for_review', name='emailstatus'), nullable=False, server_default='received'),
        sa.Column('labels', postgresql.JSON(), nullable=True),
        sa.Column('has_attachments', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('thread_id', sa.String(255), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gmail_message_id'),
    )
    op.create_index('idx_email_user_received', 'emails', ['user_id', 'received_at'])
    op.create_index('idx_email_thread', 'emails', ['thread_id'])

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('message_type', sa.Enum('whatsapp', 'sms', 'other', name='messagetype'), nullable=False),
        sa.Column('direction', sa.Enum('inbound', 'outbound', name='messagedirection'), nullable=False),
        sa.Column('sender_phone', sa.String(50), nullable=False),
        sa.Column('recipient_phone', sa.String(50), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('suggested_reply', sa.Text(), nullable=True),
        sa.Column('reply_confidence', sa.Float(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id'),
    )
    op.create_index('idx_message_user_received', 'messages', ['user_id', 'received_at'])
    op.create_index('idx_message_phone', 'messages', ['sender_phone', 'recipient_phone'])

    # Create approvals table
    op.create_table(
        'approvals',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('approval_type', sa.Enum('send_email', 'send_message', 'create_event', 'update_event', 'delete_event', 'mark_complete', 'schedule_task', 'other', name='approvaltype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'expired', name='approvalstatus'), nullable=False, server_default='pending'),
        sa.Column('action_description', sa.String(500), nullable=False),
        sa.Column('action_payload', postgresql.JSON(), nullable=False),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('approved_by', sa.String(36), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_approval_user_status', 'approvals', ['user_id', 'status'])
    op.create_index('idx_approval_expires', 'approvals', ['expires_at'])

    # Create agent_runs table
    op.create_table(
        'agent_runs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('run_type', sa.Enum('morning_routine', 'end_of_day', 'user_query', 'scheduled', 'email_received', 'message_received', name='runtype'), nullable=False),
        sa.Column('status', sa.Enum('started', 'planning', 'executing', 'completed', 'failed', 'cancelled', name='runstatus'), nullable=False, server_default='started'),
        sa.Column('trigger_data', postgresql.JSON(), nullable=True),
        sa.Column('planner_input', postgresql.JSON(), nullable=True),
        sa.Column('planner_output', postgresql.JSON(), nullable=True),
        sa.Column('router_decisions', postgresql.JSON(), nullable=True),
        sa.Column('tool_results', postgresql.JSON(), nullable=True),
        sa.Column('final_response', sa.Text(), nullable=True),
        sa.Column('approvals_required', postgresql.JSON(), nullable=True),
        sa.Column('total_tokens_used', sa.Integer(), nullable=True),
        sa.Column('llm_cost', sa.DECIMAL(10, 6), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_traceback', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_agentrun_user_type', 'agent_runs', ['user_id', 'run_type'])
    op.create_index('idx_agentrun_user_created', 'agent_runs', ['user_id', 'created_at'])
    op.create_index('idx_agentrun_status', 'agent_runs', ['status'])


def downgrade() -> None:
    # Drop all indices and tables in reverse order
    op.drop_index('idx_agentrun_status', 'agent_runs')
    op.drop_index('idx_agentrun_user_created', 'agent_runs')
    op.drop_index('idx_agentrun_user_type', 'agent_runs')
    op.drop_table('agent_runs')

    op.drop_index('idx_approval_expires', 'approvals')
    op.drop_index('idx_approval_user_status', 'approvals')
    op.drop_table('approvals')

    op.drop_index('idx_message_phone', 'messages')
    op.drop_index('idx_message_user_received', 'messages')
    op.drop_table('messages')

    op.drop_index('idx_email_thread', 'emails')
    op.drop_index('idx_email_user_received', 'emails')
    op.drop_table('emails')

    op.drop_check_constraint('ck_time_check', 'calendar_events')
    op.drop_index('idx_calendar_user_start', 'calendar_events')
    op.drop_table('calendar_events')

    op.drop_check_constraint('ck_completed_at_check', 'tasks')
    op.drop_index('idx_task_user_due', 'tasks')
    op.drop_index('idx_task_user_status', 'tasks')
    op.drop_table('tasks')

    op.drop_index('idx_user_oauth', 'users')
    op.drop_index('idx_user_email', 'users')
    op.drop_table('users')
