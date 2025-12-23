"""
Database Abstraction Interface

This module defines the database abstraction layer that allows switching between
different database backends (SQLite, PostgreSQL, etc.) without changing the
rest of the codebase.

The interface defines common database operations and behaviors that all database
adapters must implement. This makes it easy to swap database backends by
simply implementing a new adapter class.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import Pool


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.
    
    This interface defines the contract that all database implementations
    must follow. By using this abstraction, we can switch between SQLite,
    PostgreSQL, or any other database without modifying the rest of the codebase.
    
    To add a new database backend:
    1. Create a new class inheriting from DatabaseAdapter
    2. Implement all abstract methods
    3. Update the factory function to return the new adapter
    """
    
    @abstractmethod
    def create_engine(self, database_url: str, **kwargs) -> AsyncEngine:
        """
        Create and configure the async database engine.
        
        Args:
            database_url: Connection string for the database
            **kwargs: Additional engine configuration options
        
        Returns:
            Configured AsyncEngine instance
        """
        pass
    
    @abstractmethod
    def get_pool_class(self) -> Optional[type[Pool]]:
        """
        Get the connection pool class for this database type.
        
        Returns:
            Pool class (e.g., NullPool for SQLite, QueuePool for PostgreSQL)
            or None to use default
        """
        pass
    
    @abstractmethod
    def get_connect_args(self) -> dict[str, Any]:
        """
        Get connection arguments specific to this database type.
        
        Returns:
            Dictionary of connection arguments
        """
        pass
    
    @abstractmethod
    def get_engine_kwargs(self) -> dict[str, Any]:
        """
        Get additional engine configuration specific to this database type.
        
        Returns:
            Dictionary of engine configuration options
        """
        pass
    
    @abstractmethod
    async def lock_table_for_batch_reservation(
        self, 
        session: AsyncSession, 
        table_name: str
    ) -> None:
        """
        Lock a table for batch reservation operations.
        
        Different databases have different locking mechanisms, so each adapter
        implements its own locking strategy.
        
        Args:
            session: The database session
            table_name: Name of the table to lock
        
        Raises:
            DatabaseError: If locking fails
        """
        pass
    
    @abstractmethod
    def get_dialect_name(self) -> str:
        """
        Get the SQLAlchemy dialect name for this database.
        
        Returns:
            Dialect name (e.g., 'sqlite', 'postgresql')
        """
        pass

