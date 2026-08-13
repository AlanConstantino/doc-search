"""
robots.txt parsing and compliance.
"""

import urllib.robotparser
from urllib.parse import urljoin, urlparse
from typing import Optional


class RobotsChecker:
    """
    Handles robots.txt parsing and checking.
    """
    
    def __init__(self, base_url: str, user_agent: str = "DocSearchBot/1.0"):
        self.base_url = base_url
        self.user_agent = user_agent
        self.parser = urllib.robotparser.RobotFileParser()
        self._loaded = False
        self._crawl_delay: Optional[float] = None
    
    def load(self, timeout: float = 10.0) -> bool:
        """
        Load and parse robots.txt from the site.
        Returns True if loaded successfully.
        """
        try:
            parsed = urlparse(self.base_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            self.parser.set_url(robots_url)
            self.parser.read()
            self._loaded = True
            
            # Try to get crawl delay
            try:
                delay = self.parser.crawl_delay(self.user_agent)
                if delay is not None:
                    self._crawl_delay = float(delay)
            except (AttributeError, TypeError):
                pass
            
            return True
        except Exception as e:
            # If we can't load robots.txt, assume everything is allowed
            self._loaded = True
            return False
    
    def can_fetch(self, url: str) -> bool:
        """
        Check if the URL can be fetched according to robots.txt.
        """
        if not self._loaded:
            self.load()
        
        try:
            return self.parser.can_fetch(self.user_agent, url)
        except Exception:
            return True
    
    def get_crawl_delay(self, default: float = 1.0) -> float:
        """
        Get the crawl delay from robots.txt, or return default.
        """
        if not self._loaded:
            self.load()
        
        if self._crawl_delay is not None:
            return max(self._crawl_delay, 0.5)  # Minimum 0.5s for safety
        return default
