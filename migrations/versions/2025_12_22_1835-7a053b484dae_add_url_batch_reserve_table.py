"""add_url_batch_reserve_table

Revision ID: 7a053b484dae
Revises: 001_initial
Create Date: 2025-12-22 18:35:01.394921

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '7a053b484dae'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add url_batch_reserve table for tracking ID range reservations.
    This table allows multiple workers to reserve non-overlapping ID ranges.
    """
    # Get connection to check if table exists
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Create url_batch_reserve table (only if it doesn't exist)
    if 'url_batch_reserve' not in existing_tables:
        op.create_table(
            'url_batch_reserve',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('start_id', sa.Integer(), nullable=False),
            sa.Column('end_id', sa.Integer(), nullable=False),
            sa.Column('reserver', sa.String(length=100), nullable=False),
            sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Create indexes on url_batch_reserve for fast lookups
        op.create_index(
            'ix_url_batch_reserve_start_id',
            'url_batch_reserve',
            ['start_id']
        )
        op.create_index(
            'ix_url_batch_reserve_end_id',
            'url_batch_reserve',
            ['end_id']
        )
        op.create_index(
            'ix_url_batch_reserve_reserver',
            'url_batch_reserve',
            ['reserver']
        )
        op.create_index(
            'ix_url_batch_reserve_reserved_at',
            'url_batch_reserve',
            ['reserved_at']
        )


def downgrade() -> None:
    """
    Drop url_batch_reserve table and indexes.
    """
    try:
        op.drop_index('ix_url_batch_reserve_reserved_at', table_name='url_batch_reserve')
        op.drop_index('ix_url_batch_reserve_reserver', table_name='url_batch_reserve')
        op.drop_index('ix_url_batch_reserve_end_id', table_name='url_batch_reserve')
        op.drop_index('ix_url_batch_reserve_start_id', table_name='url_batch_reserve')
    except Exception:
        pass  # Indexes might not exist
    
    try:
        op.drop_table('url_batch_reserve')
    except Exception:
        pass  # Table might not exist
