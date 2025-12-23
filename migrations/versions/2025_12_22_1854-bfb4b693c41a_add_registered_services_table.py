"""add_registered_services_table

Revision ID: bfb4b693c41a
Revises: 7a053b484dae
Create Date: 2025-12-22 18:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'bfb4b693c41a'
down_revision: Union[str, None] = '7a053b484dae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add registered_services table and update url_batch_reserve.reserver to integer.
    
    Changes:
    1. Create registered_services table for service instance registration
    2. Change url_batch_reserve.reserver from String to Integer (service ID)
    """
    # Get connection to check if tables exist
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    # Create registered_services table (only if it doesn't exist)
    if 'registered_services' not in existing_tables:
        op.create_table(
            'registered_services',
            sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
            sa.Column('service_name', sa.String(length=100), nullable=True),
            sa.Column('reserved', sa.Integer(), nullable=False, server_default='0'),  # SQLite boolean
            sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Create indexes
        op.create_index(
            'ix_registered_services_reserved',
            'registered_services',
            ['reserved']
        )
        op.create_index(
            'ix_registered_services_registered_at',
            'registered_services',
            ['registered_at']
        )
        op.create_index(
            'ix_registered_services_last_heartbeat',
            'registered_services',
            ['last_heartbeat']
        )
    
    # Update url_batch_reserve.reserver from String to Integer
    # This is a data migration - we need to handle existing data
    if 'url_batch_reserve' in existing_tables:
        # Check current column type
        columns = inspector.get_columns('url_batch_reserve')
        reserver_col = next((c for c in columns if c['name'] == 'reserver'), None)
        
        if reserver_col and reserver_col['type'].python_type == str:
            # Column is currently String, need to convert to Integer
            if is_sqlite:
                # SQLite: Create new table, copy data, drop old, rename new
                op.execute("""
                    CREATE TABLE url_batch_reserve_new (
                        id INTEGER NOT NULL,
                        start_id INTEGER NOT NULL,
                        end_id INTEGER NOT NULL,
                        reserver INTEGER NOT NULL,
                        reserved_at DATETIME NOT NULL,
                        PRIMARY KEY (id)
                    )
                """)
                
                # Copy data, converting reserver to integer (use 1 as default if can't convert)
                op.execute("""
                    INSERT INTO url_batch_reserve_new (id, start_id, end_id, reserver, reserved_at)
                    SELECT id, start_id, end_id, 
                           CASE 
                               WHEN CAST(reserver AS INTEGER) IS NULL THEN 1
                               ELSE CAST(reserver AS INTEGER)
                           END,
                           reserved_at
                    FROM url_batch_reserve
                """)
                
                # Drop old table and rename new
                op.drop_table('url_batch_reserve')
                op.execute("ALTER TABLE url_batch_reserve_new RENAME TO url_batch_reserve")
                
                # Recreate indexes
                op.create_index('ix_url_batch_reserve_start_id', 'url_batch_reserve', ['start_id'])
                op.create_index('ix_url_batch_reserve_end_id', 'url_batch_reserve', ['end_id'])
                op.create_index('ix_url_batch_reserve_reserver', 'url_batch_reserve', ['reserver'])
                op.create_index('ix_url_batch_reserve_reserved_at', 'url_batch_reserve', ['reserved_at'])
            else:
                # PostgreSQL: Use ALTER COLUMN
                op.execute("ALTER TABLE url_batch_reserve ALTER COLUMN reserver TYPE INTEGER USING reserver::integer")


def downgrade() -> None:
    """
    Revert changes: drop registered_services and change reserver back to String.
    """
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    # Drop registered_services table
    try:
        op.drop_index('ix_registered_services_last_heartbeat', table_name='registered_services')
        op.drop_index('ix_registered_services_registered_at', table_name='registered_services')
        op.drop_index('ix_registered_services_reserved', table_name='registered_services')
        op.drop_table('registered_services')
    except Exception:
        pass
    
    # Revert url_batch_reserve.reserver back to String
    if is_sqlite:
        op.execute("""
            CREATE TABLE url_batch_reserve_new (
                id INTEGER NOT NULL,
                start_id INTEGER NOT NULL,
                end_id INTEGER NOT NULL,
                reserver VARCHAR(100) NOT NULL,
                reserved_at DATETIME NOT NULL,
                PRIMARY KEY (id)
            )
        """)
        
        op.execute("""
            INSERT INTO url_batch_reserve_new (id, start_id, end_id, reserver, reserved_at)
            SELECT id, start_id, end_id, CAST(reserver AS TEXT), reserved_at
            FROM url_batch_reserve
        """)
        
        op.drop_table('url_batch_reserve')
        op.execute("ALTER TABLE url_batch_reserve_new RENAME TO url_batch_reserve")
        
        op.create_index('ix_url_batch_reserve_start_id', 'url_batch_reserve', ['start_id'])
        op.create_index('ix_url_batch_reserve_end_id', 'url_batch_reserve', ['end_id'])
        op.create_index('ix_url_batch_reserve_reserver', 'url_batch_reserve', ['reserver'])
        op.create_index('ix_url_batch_reserve_reserved_at', 'url_batch_reserve', ['reserved_at'])
    else:
        op.execute("ALTER TABLE url_batch_reserve ALTER COLUMN reserver TYPE VARCHAR(100) USING reserver::text")
