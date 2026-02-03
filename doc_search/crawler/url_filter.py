"""
URL filtering logic for the web crawler.

This module handles:
- URL validation
- Extension checking (SKIP_EXTENSIONS, EXTRACTABLE_DOC_EXTENSIONS)
- Path pattern matching (SKIP_PATH_PATTERNS)
- should_follow logic for crawl decisions
"""

from typing import Optional, Callable
from urllib.parse import urlparse

from ..utils import normalize_url, is_same_domain, get_domain
from ..robots import RobotsChecker


# Extensions that should never be crawled (archives, media, binaries)
SKIP_EXTENSIONS = frozenset([
    # Archives
    '.tar', '.gz', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz',
    '.zip', '.rar', '.7z', '.bz2', '.xz', '.lz', '.lzma',
    # Documents (excluded by default, can be enabled with extract_docs=True)
    '.epub', '.mobi', '.ppt', '.pptx', '.odt', '.ods', '.odp',
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico', '.webp',
    '.bmp', '.tiff', '.tif', '.psd', '.ai', '.eps',
    # Media
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
    '.wav', '.ogg', '.webm', '.m4a', '.m4v',
    # Code/data files (usually not documentation)
    '.css', '.js', '.json', '.xml', '.rss', '.atom',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    # Executables and packages
    '.exe', '.msi', '.dmg', '.pkg', '.deb', '.rpm',
    '.whl', '.egg', '.jar', '.war', '.apk', '.ipa',
    # Source archives
    '.asc', '.sig', '.sha256', '.md5',
])

# Document extensions that can be extracted (when extract_docs=True)
EXTRACTABLE_DOC_EXTENSIONS = frozenset([
    '.pdf',
    '.doc', '.docx',
    '.xls', '.xlsx',
])

# URL path patterns that indicate non-documentation content
SKIP_PATH_PATTERNS = [
    '/download/', '/downloads/',
    '/archive/', '/archives/',
    '/releases/', '/release/',
    '/dist/', '/ftp/',
    '/source/', '/sources/',
    '/packages/', '/pkg/',
    '/binaries/', '/bin/',
]


def is_skippable_extension(url: str, extract_docs: bool = False) -> bool:
    """
    Check if URL has an extension that should be skipped.
    
    Args:
        url: The URL to check
        extract_docs: If True, extractable document extensions (PDF, DOCX, etc.)
                      will NOT be skipped
    
    Returns:
        True if the URL should be skipped based on its extension
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Check each skip extension
    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return True
    
    # Check extractable document extensions
    # Skip them unless extract_docs is enabled
    if not extract_docs:
        for ext in EXTRACTABLE_DOC_EXTENSIONS:
            if path.endswith(ext):
                return True
    
    # Handle compound extensions like .tar.gz
    if '.tar.' in path:
        return True
    
    return False


def is_extractable_doc(url: str) -> bool:
    """
    Check if URL is an extractable document (PDF, DOCX, etc.).
    
    Args:
        url: The URL to check
    
    Returns:
        True if the URL points to an extractable document
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext in EXTRACTABLE_DOC_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def is_skippable_path(url: str) -> bool:
    """
    Check if URL path indicates non-documentation content.
    
    Args:
        url: The URL to check
    
    Returns:
        True if the URL path matches a skip pattern
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    for pattern in SKIP_PATH_PATTERNS:
        if pattern in path:
            return True
    
    return False


def is_under_base_path(url: str, base_path: str, same_path: bool = True) -> bool:
    """
    Check if URL is under the base path.
    
    Args:
        url: The URL to check
        base_path: The base path to compare against (e.g., '/3.11')
        same_path: If False, always returns True (no path restriction)
    
    Returns:
        True if the URL is under the base path
    """
    if not same_path:
        return True
    
    if not base_path:
        return True
    
    parsed = urlparse(url)
    url_path = parsed.path.rstrip('/')
    
    # URL must start with base_path
    # e.g., base_path="/3.11" should match "/3.11", "/3.11/", "/3.11/library/", etc.
    if url_path == base_path:
        return True
    if url_path.startswith(base_path + '/'):
        return True
    
    return False


class UrlFilter:
    """
    URL filtering logic for the web crawler.
    
    Encapsulates all the logic for determining whether a URL should be crawled,
    including extension checking, path pattern matching, domain restrictions,
    and robots.txt compliance.
    """
    
    def __init__(
        self,
        base_url: str,
        robots_checker: Optional[RobotsChecker] = None,
        stay_on_domain: bool = True,
        same_path: bool = False,
        extract_docs: bool = False,
        max_depth: Optional[int] = None,
        url_filter: Optional[Callable[[str], bool]] = None,
    ):
        """
        Initialize the URL filter.
        
        Args:
            base_url: The starting URL for the crawl
            robots_checker: RobotsChecker instance for robots.txt compliance
            stay_on_domain: If True, only crawl URLs on the same domain
            same_path: If True, only crawl URLs under the starting path
            extract_docs: If True, allow extractable document extensions
            max_depth: Maximum crawl depth (None for unlimited)
            url_filter: Optional custom filter function
        """
        self.base_url = normalize_url(base_url)
        self.base_domain = get_domain(base_url)
        self.robots_checker = robots_checker
        self.stay_on_domain = stay_on_domain
        self.same_path = same_path
        self.extract_docs = extract_docs
        self.max_depth = max_depth
        self.custom_filter = url_filter
        
        # Extract base path for same_path filtering
        parsed = urlparse(self.base_url)
        self.base_path = parsed.path.rstrip('/') or ''
        # For root paths (empty or /), allow everything under domain
        if self.base_path == '' or self.base_path == '/':
            self.base_path = ''
            self.same_path = False  # No path restriction for root
    
    def is_skippable_extension(self, url: str) -> bool:
        """Check if URL has an extension that should be skipped."""
        return is_skippable_extension(url, self.extract_docs)
    
    def is_extractable_doc(self, url: str) -> bool:
        """Check if URL is an extractable document (PDF, DOCX, etc.)."""
        return is_extractable_doc(url)
    
    def is_skippable_path(self, url: str) -> bool:
        """Check if URL path indicates non-documentation content."""
        return is_skippable_path(url)
    
    def is_under_base_path(self, url: str) -> bool:
        """Check if URL is under the base path."""
        return is_under_base_path(url, self.base_path, self.same_path)
    
    def should_follow(
        self,
        url: str,
        depth: int = 0,
        is_visited_func: Optional[Callable[[str], bool]] = None,
        force: bool = False,
    ) -> bool:
        """
        Check if URL should be crawled.
        
        Args:
            url: The URL to check
            depth: Current crawl depth
            is_visited_func: Optional function to check if URL was already visited
            force: If True, skip the visited check (for incremental crawling)
        
        Returns:
            True if the URL should be crawled
        """
        # Already visited (skip in incremental mode with force=True)
        if not force and is_visited_func and is_visited_func(url):
            return False
        
        # Depth check
        if self.max_depth is not None and depth > self.max_depth:
            return False
        
        # Skip non-HTML extensions
        if self.is_skippable_extension(url):
            return False
        
        # Skip obvious non-doc paths
        if self.is_skippable_path(url):
            return False
        
        # Domain check
        if self.stay_on_domain and not is_same_domain(url, self.base_url):
            return False
        
        # Path prefix check
        if not self.is_under_base_path(url):
            return False
        
        # Robots.txt check
        if self.robots_checker and not self.robots_checker.can_fetch(url):
            return False
        
        # Custom filter
        if self.custom_filter and not self.custom_filter(url):
            return False
        
        return True


__all__ = [
    'SKIP_EXTENSIONS',
    'EXTRACTABLE_DOC_EXTENSIONS',
    'SKIP_PATH_PATTERNS',
    'is_skippable_extension',
    'is_extractable_doc',
    'is_skippable_path',
    'is_under_base_path',
    'UrlFilter',
]
