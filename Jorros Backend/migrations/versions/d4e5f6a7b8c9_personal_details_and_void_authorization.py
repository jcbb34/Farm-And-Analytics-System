"""Structured details and completed Owner/Admin void approvals.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from alembic import op
import sqlalchemy as sa
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

def upgrade():
    for table in ('users', 'employees'):
        op.add_column(table, sa.Column('personal_details_json', sa.UnicodeText(), nullable=True))
    op.create_table('void_operations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('operation_key', sa.String(32), nullable=False, unique=True),
        sa.Column('requester_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('authorizer_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('reason', sa.UnicodeText(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

def downgrade():
    op.drop_table('void_operations')
    for table in ('employees', 'users'):
        op.drop_column(table, 'personal_details_json')
