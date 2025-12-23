"""
SQLite Database Adapter

This module implements the DatabaseAdapter interface for SQLite.
All SQLite-specific configuration and behavior is encapsulated here.

SQLite is a file-based database that's perfect for:
- Local development
- Testing
- Single-instance deployments
- Low to medium traffic applications

Key characteristics:
- File-based (single .db file)
- No server required
- Single writer at a time (file locking)
- Excellent for reads, limited concurrent writes
"""

from typing import Any
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.interface import DatabaseAdapter


class SQLiteAdapter(DatabaseAdapter):
    """
    SQLite database adapter implementation.
    
    This adapter handles all SQLite-specific configuration and operations.
    SQLite uses file-based storage and has different characteristics than
    server-based databases like PostgreSQL.
    """
    
    def create_engine(self, database_url: str, **kwargs) -> AsyncEngine:
        """
        Create SQLite async engine with appropriate configuration.
        
        SQLite-specific configuration:
        - NullPool: Single connection (file-based, no pooling needed)
        - check_same_thread=False: Required for async SQLite operations
        - echo: Set to False in production (only True for debugging)
        
        Args:
            database_url: SQLite connection string (sqlite+aiosqlite:///...)
            **kwargs: Additional engine options (merged with SQLite defaults)
        
        Returns:
            Configured AsyncEngine for SQLite
        """
        # SQLite-specific connection arguments
        connect_args = self.get_connect_args()
        
        # SQLite-specific engine configuration
        engine_kwargs = self.get_engine_kwargs()
        
        # Merge with any provided kwargs
        engine_kwargs.update(kwargs)
        
        return create_async_engine(
            database_url,
            poolclass=self.get_pool_class(),
            connect_args=connect_args,
            **engine_kwargs
        )
    
    def get_pool_class(self) -> type[NullPool]:
        """
        Get the connection pool class for SQLite.
        
        SQLite uses NullPool (single connection) because:
        - File-based database doesn't benefit from connection pooling
        - SQLite handles one writer at a time (file locking)
        - Single connection is sufficient for most use cases
        
        Returns:
            NullPool class
        """
        return NullPool
    
    def get_connect_args(self) -> dict[str, Any]:
        """
        Get SQLite-specific connection arguments.
        
        Returns:
            Dictionary with SQLite connection arguments
        """
        return {
            "check_same_thread": False
        }
    
    def get_engine_kwargs(self) -> dict[str, Any]:
        """
        Get SQLite-specific engine configuration.
        
        Returns:
            Dictionary with SQLite engine options
        """
        return {
            "echo": False  # Set to True only for SQL debugging in development
        }
    
    async def lock_table_for_batch_reservation(
        self, 
        session: AsyncSession, 
        table_name: str
    ) -> None:
        """
        Lock table for batch reservation using SQLite's locking mechanism.
        
        Uses SELECT ... FOR UPDATE on all rows to effectively lock the table
        for the duration of the transaction.
        
        Args:
            session: The database session
            table_name: Name of the table to lock
        """
        from app.db.models import URLBatchReserve
        
        lock_statement = select(URLBatchReserve).with_for_update(nowait=False)
        await session.execute(lock_statement)
    
    def get_dialect_name(self) -> str:
        """
        Get the SQLAlchemy dialect name for SQLite.
        
        Returns:
            'sqlite'
        """
        return "sqlite"


def get_database_adapter() -> DatabaseAdapter:
    """
    Factory function to get the database adapter.
    
    Returns SQLiteAdapter by default. To switch to PostgreSQL, create a
    PostgreSQLAdapter class and update this function.
    
    Returns:
        DatabaseAdapter instance
    """
    return SQLiteAdapter()

