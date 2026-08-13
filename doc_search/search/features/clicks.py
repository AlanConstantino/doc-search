"""
SQLite-backed click logging for simple CTR ranking boosts.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional


class ClickLog:
    """Append-only click log with per-URL aggregates."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = ':memory:'
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            'CREATE TABLE IF NOT EXISTS click_log ('
            '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
            '  query TEXT,'
            '  url TEXT NOT NULL,'
            '  rank INTEGER,'
            '  timestamp REAL NOT NULL'
            ')'
        )
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_click_url ON click_log(url)'
        )
        self._conn.commit()

    def log(self, query: str, url: str, rank: int = 0) -> None:
        with self._lock:
            self._conn.execute(
                'INSERT INTO click_log (query, url, rank, timestamp) VALUES (?, ?, ?, ?)',
                (query or '', url or '', int(rank or 0), time.time()),
            )
            self._conn.commit()

    def counts(self) -> Dict[str, int]:
        """Return url -> click count."""
        with self._lock:
            cur = self._conn.execute(
                'SELECT url, COUNT(*) FROM click_log GROUP BY url'
            )
            return {row[0]: row[1] for row in cur.fetchall() if row[0]}

    def close(self) -> None:
        self._conn.close()

    @classmethod
    def for_site(cls, site_dir: Path) -> 'ClickLog':
        path = Path(site_dir) / 'clicks.db'
        return cls(str(path))
