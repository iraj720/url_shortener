"""
Database Session Management with Connection Pooling

This module handles async database connections using SQLAlchemy's async engine.
Uses a database abstraction layer to support different database backends.

Key Features:
- Database abstraction: Easy to switch between SQLite, PostgreSQL, etc.
- Connection pooling: Configured per database type
- Async session management: Proper async context management
- Error handling: Automatic rollback on exceptions

The database adapter pattern allows us to:
- Use SQLite by default (no conditionals in code)
- Switch to PostgreSQL by changing the adapter (no code changes needed)
- Add new database backends easily
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.setting import settings
from app.db.sqlite_adapter import get_database_adapter

# Get the database adapter (currently SQLite by default)
# To switch databases, just change the adapter returned by get_database_adapter()
db_adapter = get_database_adapter()

# Create async engine using the adapter
# The adapter handles all database-specific configuration
engine = db_adapter.create_engine(
    settings.DATABASE_URL
)

# Create async session factory
# This factory creates sessions that are properly configured for async operations
async_session_maker = async_sessionmaker(
    engine,
    class_=SQLModelAsyncSession,
    expire_on_commit=False,  # Prevents SQLAlchemy from expiring objects after commit
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function for FastAPI to get database session.
    
    This function:
    - Creates a new async session from the pool
    - Yields it to the endpoint
    - Automatically commits on success
    - Rolls back on exception
    - Closes session automatically (context manager handles it)
    
    Usage in FastAPI:
        @router.get("/endpoint")
        async def endpoint(session: AsyncSession = Depends(get_session)):
            # Use session here
            pass
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()  # Commit transaction on successful completion
        except Exception:
            await session.rollback()  # Rollback on any exception
            raise
        # Session is automatically closed by the context manager
