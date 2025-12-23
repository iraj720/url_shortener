"""
Database module with abstraction layer.

This module provides:
- DatabaseAdapter interface: Abstract base class for database implementations
- SQLiteAdapter: SQLite-specific implementation (default)
- Session management: Database session creation and management

To add a new database backend:
1. Create a new adapter class inheriting from DatabaseAdapter
2. Implement all abstract methods
3. Update get_database_adapter() in sqlite_adapter.py to return the new adapter
4. No other code changes needed!
"""

from app.db.interface import DatabaseAdapter
from app.db.session import get_session, async_session_maker, engine

__all__ = [
    "DatabaseAdapter",
    "get_session",
    "async_session_maker",
    "engine",
]

