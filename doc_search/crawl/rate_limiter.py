"""
Thread-safe per-domain rate limiter for web crawling.

This module provides the RateLimiter class for enforcing polite
crawling behavior with configurable per-domain delays and backoff support.
"""

import time
import threading
from collections import defaultdict
from typing import Dict

from ..core.constants import DEFAULT_CRAWL_DELAY


class RateLimiter:
    """
    Thread-safe per-domain rate limiter.
    
    Enforces minimum delays between requests to the same domain,
    supports custom per-domain delays, and handles backoff for rate limiting.
    """
    
    def __init__(self, default_delay: float = DEFAULT_CRAWL_DELAY):
        """
        Initialize rate limiter.
        
        Args:
            default_delay: Default delay in seconds between requests to the same domain
        """
        self.default_delay = default_delay
        self._domain_delays: Dict[str, float] = {}
        self._last_request: Dict[str, float] = defaultdict(float)
        self._backoff_until: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def set_domain_delay(self, domain: str, delay: float):
        """Set custom delay for a specific domain."""
        with self._lock:
            self._domain_delays[domain] = delay
    
    def get_delay(self, domain: str) -> float:
        """Get delay for a domain."""
        with self._lock:
            return self._domain_delays.get(domain, self.default_delay)
    
    def set_backoff(self, domain: str, seconds: float):
        """Set backoff until time for a domain."""
        with self._lock:
            self._backoff_until[domain] = time.time() + seconds
    
    def wait_for_domain(self, domain: str):
        """Wait according to rate limiting rules for a domain."""
        with self._lock:
            now = time.time()
            
            # Check backoff
            backoff_until = self._backoff_until.get(domain, 0)
            if now < backoff_until:
                wait_time = backoff_until - now
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()
                now = time.time()
            
            # Normal delay between requests
            delay = self._domain_delays.get(domain, self.default_delay)
            last = self._last_request.get(domain, 0)
            elapsed = now - last
            
            if elapsed < delay:
                wait_time = delay - elapsed
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()
            
            self._last_request[domain] = time.time()
