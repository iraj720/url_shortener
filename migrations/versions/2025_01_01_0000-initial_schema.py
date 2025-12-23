"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create initial database schema:
    - short_urls table: Stores URL shortening mappings
    - visit_logs table: Stores individual visit logs for analytics
    - url_batch_reserve table: Tracks ID range reservations for workers
    """
    # Get connection to check if tables exist
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Check if we're using SQLite (SQLite has limitations with foreign keys)
    is_sqlite = bind.dialect.name == 'sqlite'
    
    # Create short_urls table (only if it doesn't exist)
    if 'short_urls' not in existing_tables:
        op.create_table(
            'short_urls',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('original_url', sa.Text(), nullable=False),
            sa.Column('short_code', sa.String(length=10), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('visit_count', sa.Integer(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id')
        )
        
        op.create_index(
            'ix_short_urls_short_code',
            'short_urls',
            ['short_code'],
            unique=True
        )
        
        op.create_index(
            'ix_short_urls_created_at',
            'short_urls',
            ['created_at']
        )
        
        op.create_index(
            'ix_short_urls_original_url',
            'short_urls',
            ['original_url']
        )
    
    # Create visit_logs table (only if it doesn't exist)
    if 'visit_logs' not in existing_tables:
        # Create table (SQLite doesn't support foreign keys added after table creation)
        op.create_table(
            'visit_logs',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('short_code', sa.String(length=10), nullable=False),
            sa.Column('ip_address', sa.String(length=45), nullable=False),
            sa.Column('visited_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('user_agent', sa.String(length=500), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Add foreign key constraint (only for PostgreSQL, SQLite doesn't support it)
        if not is_sqlite:
            op.create_foreign_key(
                'fk_visit_logs_short_code',
                'visit_logs',
                'short_urls',
                ['short_code'],
                ['short_code'],
                ondelete='CASCADE'
            )
        
        op.create_index(
            'ix_visit_logs_short_code',
            'visit_logs',
            ['short_code']
        )

        op.create_index(
            'ix_visit_logs_visited_at',
            'visit_logs',
            ['visited_at']
        )
    
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
    Drop all tables and indexes.
    """
    # Get connection to check dialect
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    # Drop foreign key constraint (only for PostgreSQL, SQLite handles it differently)
    if not is_sqlite:
        try:
            op.drop_constraint('fk_visit_logs_short_code', 'visit_logs', type_='foreignkey')
        except Exception:
            pass  # Constraint might not exist
    
    # Drop url_batch_reserve indexes
    try:
        op.drop_index('ix_url_batch_reserve_reserved_at', table_name='url_batch_reserve')
        op.drop_index('ix_url_batch_reserve_reserver', table_name='url_batch_reserve')
        op.drop_index('ix_url_batch_reserve_end_id', table_name='url_batch_reserve')
        op.drop_index('ix_url_batch_reserve_start_id', table_name='url_batch_reserve')
    except Exception:
        pass  # Indexes might not exist
    
    # Drop visit_logs indexes
    try:
        op.drop_index('ix_visit_logs_visited_at', table_name='visit_logs')
        op.drop_index('ix_visit_logs_short_code', table_name='visit_logs')
    except Exception:
        pass  # Indexes might not exist
    
    # Drop short_urls indexes
    try:
        op.drop_index('ix_short_urls_original_url', table_name='short_urls')
        op.drop_index('ix_short_urls_created_at', table_name='short_urls')
        op.drop_index('ix_short_urls_short_code', table_name='short_urls')
    except Exception:
        pass  # Indexes might not exist
    
    # Drop tables
    try:
        op.drop_table('url_batch_reserve')
    except Exception:
        pass
    try:
        op.drop_table('visit_logs')
    except Exception:
        pass
    try:
        op.drop_table('short_urls')
    except Exception:
        pass

