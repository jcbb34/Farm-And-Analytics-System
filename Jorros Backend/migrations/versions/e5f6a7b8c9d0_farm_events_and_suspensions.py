"""Durable farm events and suspensions. Existing tables and history are unchanged."""
from alembic import op
import sqlalchemy as sa
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('farm_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('scope_type', sa.String(20), nullable=False),
        sa.Column('scope_json', sa.UnicodeText(), nullable=False),
        sa.Column('reason', sa.UnicodeText(), nullable=False),
        sa.Column('instructions', sa.UnicodeText(), nullable=True),
        sa.Column('source_name', sa.String(150), nullable=True),
        sa.Column('source_reference', sa.String(600), nullable=True),
        sa.Column('checklist_json', sa.UnicodeText(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('notice_version', sa.Integer(), nullable=False),
        sa.Column('command_key', sa.String(64), nullable=False, unique=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('end_reason', sa.UnicodeText(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_farm_events_ends_at', 'farm_events', ['ends_at'], unique=False)
    op.create_index('ix_farm_events_starts_at', 'farm_events', ['starts_at'], unique=False)
    op.create_index('ix_farm_events_status', 'farm_events', ['status'], unique=False)
    op.create_table('farm_event_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('farm_events.id'), nullable=False),
        sa.Column('activity_id', sa.Integer(), sa.ForeignKey('farm_activities.id'), nullable=False),
        sa.Column('original_json', sa.UnicodeText(), nullable=False),
        sa.Column('resolution', sa.String(30), nullable=False),
        sa.Column('essential_review', sa.Boolean(), nullable=False),
        sa.Column('authorized_employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=True),
        sa.Column('review_reason', sa.UnicodeText(), nullable=True),
        sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('event_id', 'activity_id', name='uq_farm_event_task'))
    op.create_index('ix_farm_event_tasks_activity_id', 'farm_event_tasks', ['activity_id'], unique=False)
    op.create_index('ix_farm_event_tasks_event_id', 'farm_event_tasks', ['event_id'], unique=False)
    op.create_index('ix_farm_event_tasks_resolution', 'farm_event_tasks', ['resolution'], unique=False)
    op.create_table('farm_event_acknowledgements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('farm_events.id'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('notice_version', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('event_id', 'employee_id', 'notice_version', name='uq_farm_event_acknowledgement'))
    op.create_index('ix_farm_event_acknowledgements_employee_id', 'farm_event_acknowledgements', ['employee_id'], unique=False)
    op.create_index('ix_farm_event_acknowledgements_event_id', 'farm_event_acknowledgements', ['event_id'], unique=False)
    op.create_table('farm_event_audits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('farm_events.id'), nullable=False),
        sa.Column('action', sa.String(60), nullable=False),
        sa.Column('reason', sa.UnicodeText(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('actor_name', sa.String(150), nullable=False),
        sa.Column('details_json', sa.UnicodeText(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_farm_event_audits_event_id', 'farm_event_audits', ['event_id'], unique=False)
    op.create_table('farm_event_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('farm_events.id'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('area', sa.String(150), nullable=False),
        sa.Column('description', sa.UnicodeText(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_farm_event_reports_event_id', 'farm_event_reports', ['event_id'], unique=False)


def downgrade():
    op.drop_table('farm_event_reports')
    op.drop_table('farm_event_audits')
    op.drop_table('farm_event_acknowledgements')
    op.drop_table('farm_event_tasks')
    op.drop_table('farm_events')
