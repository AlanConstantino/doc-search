"""
Thread-safe crawl state management for resumable crawling.

This module contains the CrawlState class which manages:
- Visited URLs tracking
- Pending URL queue
- Failed URL retry counts
- Crawl statistics
- State persistence to disk
"""

import json
import threading
from collections import deque
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple


class CrawlState:
    """
    Thread-safe crawl state management for resumable crawling.
    """
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.visited: Set[str] = set()
        self.pending: deque = deque()  # (url, depth) tuples
        self.failed: Dict[str, int] = {}  # url -> retry count
        self.stats = {
            'pages_crawled': 0,
            'pages_failed': 0,
            'pages_skipped': 0,
            'pages_unchanged': 0,
            'docs_extracted': 0,
            'bytes_downloaded': 0,
            'start_time': None,
            'last_checkpoint': None
        }
        self._lock = threading.Lock()
    
    def save(self):
        """Save state to disk (thread-safe)."""
        with self._lock:
            state = {
                'visited': list(self.visited),
                'pending': list(self.pending),
                'failed': self.failed,
                'stats': self.stats
            }
        
        # Write atomically
        tmp_file = self.state_file.with_suffix('.tmp')
        with open(tmp_file, 'w') as f:
            json.dump(state, f)
        tmp_file.rename(self.state_file)
    
    def load(self) -> bool:
        """Load state from disk. Returns True if loaded successfully."""
        if not self.state_file.exists():
            return False
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            with self._lock:
                self.visited = set(state.get('visited', []))
                # Handle both old format (just urls) and new format (url, depth tuples)
                pending = state.get('pending', [])
                self.pending = deque()
                for item in pending:
                    if isinstance(item, list) and len(item) == 2:
                        self.pending.append(tuple(item))
                    else:
                        self.pending.append((item, 0))  # Assume depth 0 for old format
                self.failed = state.get('failed', {})
                self.stats = state.get('stats', self.stats)
            return True
        except (json.JSONDecodeError, IOError):
            return False
    
    def clear(self):
        """Clear all state."""
        with self._lock:
            self.visited.clear()
            self.pending.clear()
            self.failed.clear()
            self.stats = {
                'pages_crawled': 0,
                'pages_failed': 0,
                'pages_skipped': 0,
                'pages_unchanged': 0,
                'docs_extracted': 0,
                'bytes_downloaded': 0,
                'start_time': None,
                'last_checkpoint': None
            }
        if self.state_file.exists():
            self.state_file.unlink()
    
    def pop_url(self) -> Optional[Tuple[str, int]]:
        """Pop a URL from the queue (thread-safe)."""
        with self._lock:
            if self.pending:
                item = self.pending.popleft()
                if isinstance(item, tuple):
                    return item
                return (item, 0)
            return None
    
    def add_urls(self, urls: List[Tuple[str, int]]):
        """Add URLs to the queue (thread-safe), avoiding duplicates."""
        with self._lock:
            # Build set of URLs already in pending for fast lookup
            pending_urls = {url for url, _ in self.pending}
            for url, depth in urls:
                if url not in self.visited and url not in pending_urls:
                    self.pending.append((url, depth))
                    pending_urls.add(url)
    
    def mark_visited(self, url: str):
        """Mark a URL as visited (thread-safe)."""
        with self._lock:
            self.visited.add(url)
    
    def is_visited(self, url: str) -> bool:
        """Check if URL was visited (thread-safe)."""
        with self._lock:
            return url in self.visited
    
    def mark_failed(self, url: str, depth: int) -> bool:
        """
        Mark a URL as failed, possibly retry.
        Returns True if should retry.
        """
        with self._lock:
            retry_count = self.failed.get(url, 0)
            if retry_count < 3:
                self.failed[url] = retry_count + 1
                self.pending.append((url, depth))
                self.visited.discard(url)
                return True
            else:
                self.stats['pages_failed'] += 1
                return False
    
    def increment_stat(self, stat: str, value: int = 1):
        """Increment a stat counter (thread-safe)."""
        with self._lock:
            self.stats[stat] = self.stats.get(stat, 0) + value
    
    def get_progress(self, max_pages: Optional[int] = None) -> str:
        """Get progress string (thread-safe)."""
        with self._lock:
            crawled = self.stats['pages_crawled']
            pending = len(self.pending)
            limit = max_pages or '∞'
            return f"[{crawled}/{limit}] (queue: {pending})"
