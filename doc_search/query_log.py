"""
SQLite-backed query logging for search analytics.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional


class QueryLog:
    """Log search queries with results count and timing to SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = ':memory:'
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            'CREATE TABLE IF NOT EXISTS query_log ('
            '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
            '  query TEXT NOT NULL,'
            '  results_count INTEGER NOT NULL,'
            '  elapsed_ms REAL NOT NULL,'
            '  timestamp REAL NOT NULL'
            ')'
        )
        self._conn.commit()

    def log(self, query: str, results_count: int, elapsed_ms: float) -> None:
        """Record a search query."""
        with self._lock:
            self._conn.execute(
                'INSERT INTO query_log (query, results_count, elapsed_ms, timestamp) '
                'VALUES (?, ?, ?, ?)',
                (query, results_count, elapsed_ms, time.time())
            )
            self._conn.commit()

    def get_recent(self, limit: int = 100) -> list:
        """Return recent queries."""
        with self._lock:
            cursor = self._conn.execute(
                'SELECT query, results_count, elapsed_ms, timestamp '
                'FROM query_log ORDER BY id DESC LIMIT ?',
                (limit,)
            )
            return cursor.fetchall()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
