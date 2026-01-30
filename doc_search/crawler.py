"""
Web crawler with resumable state, rate limiting, and robots.txt compliance.
"""

import json
import time
import base64
import ssl
import gzip
from collections import deque
from pathlib import Path
from typing import Optional, Set, Dict, Any, Callable, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse

from .utils import (
    normalize_url, is_same_domain, url_to_filename, 
    is_html_content, get_domain
)
from .robots import RobotsChecker
from .parser import extract_text, extract_links


# Extensions that should never be crawled (archives, media, binaries)
SKIP_EXTENSIONS = frozenset([
    # Archives
    '.tar', '.gz', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz',
    '.zip', '.rar', '.7z', '.bz2', '.xz', '.lz', '.lzma',
    # Documents
    '.pdf', '.epub', '.mobi', '.doc', '.docx', '.xls', '.xlsx', 
    '.ppt', '.pptx', '.odt', '.ods', '.odp',
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


class CrawlState:
    """
    Manages crawl state for resumable crawling.
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
            'bytes_downloaded': 0,
            'start_time': None,
            'last_checkpoint': None
        }
    
    def save(self):
        """Save state to disk."""
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
        self.visited.clear()
        self.pending.clear()
        self.failed.clear()
        self.stats = {
            'pages_crawled': 0,
            'pages_failed': 0,
            'pages_skipped': 0,
            'bytes_downloaded': 0,
            'start_time': None,
            'last_checkpoint': None
        }
        if self.state_file.exists():
            self.state_file.unlink()


class Crawler:
    """
    Web crawler with politeness controls and resumable crawling.
    """
    
    USER_AGENT = "DocSearchBot/1.1 (+https://github.com/AlanConstantino/doc-search)"
    MAX_RETRIES = 3
    CHECKPOINT_INTERVAL = 100  # Save state every N pages
    
    def __init__(
        self,
        base_url: str,
        data_dir: Path,
        delay: float = 1.0,
        timeout: float = 30.0,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        auth: Optional[Tuple[str, str]] = None,  # (username, password)
        stay_on_domain: bool = True,
        same_path: bool = True,  # Only crawl URLs under the starting path
        url_filter: Optional[Callable[[str], bool]] = None,
        verbose: bool = True
    ):
        self.base_url = normalize_url(base_url)
        self.base_domain = get_domain(base_url)
        self.data_dir = Path(data_dir)
        self.delay = delay
        self.timeout = timeout
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.auth = auth
        self.stay_on_domain = stay_on_domain
        self.same_path = same_path
        self.url_filter = url_filter
        self.verbose = verbose
        
        # Extract base path for same_path filtering
        # Preserve trailing slash for proper path matching
        parsed = urlparse(self.base_url)
        self.base_path = parsed.path.rstrip('/') or ''
        # For root paths (empty or /), allow everything under domain
        if self.base_path == '' or self.base_path == '/':
            self.base_path = ''
            self.same_path = False  # No path restriction for root
        
        # Setup directories
        self.pages_dir = self.data_dir / 'pages'
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize state
        self.state = CrawlState(self.data_dir / 'crawl_state.json')
        
        # Initialize robots checker
        self.robots = RobotsChecker(base_url, self.USER_AGENT)
        
        # SSL context that doesn't verify (for self-signed certs in docs)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # Rate limiting state
        self._last_request_time = 0.0
        self._backoff_until = 0.0
    
    def _log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)
    
    def _progress(self):
        """Return progress string."""
        return f"[{self.state.stats['pages_crawled']}/{self.max_pages or '∞'}] (queue: {len(self.state.pending)})"
    
    def _get_auth_header(self) -> Optional[str]:
        """Get Basic Auth header if credentials provided."""
        if self.auth:
            username, password = self.auth
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        return None
    
    def _wait_for_rate_limit(self):
        """Wait according to rate limiting rules."""
        now = time.time()
        
        # Check backoff
        if now < self._backoff_until:
            wait_time = self._backoff_until - now
            self._log(f"  Backing off for {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        # Normal delay between requests
        elapsed = now - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        
        self._last_request_time = time.time()
    
    def _fetch(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch a URL and return (content, content_type).
        Returns (None, None) on failure.
        """
        self._wait_for_rate_limit()
        
        headers = {
            'User-Agent': self.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        auth_header = self._get_auth_header()
        if auth_header:
            headers['Authorization'] = auth_header
        
        request = Request(url, headers=headers)
        
        try:
            response = urlopen(request, timeout=self.timeout, context=self.ssl_context)
            
            # Read content
            content_bytes = response.read()
            
            # Handle gzip encoding
            content_encoding = response.headers.get('Content-Encoding', '')
            if 'gzip' in content_encoding.lower():
                try:
                    content_bytes = gzip.decompress(content_bytes)
                except Exception:
                    pass
            
            # Decode content
            content_type = response.headers.get('Content-Type', '')
            charset = 'utf-8'
            if 'charset=' in content_type:
                charset = content_type.split('charset=')[-1].split(';')[0].strip()
            
            try:
                content = content_bytes.decode(charset)
            except (UnicodeDecodeError, LookupError):
                content = content_bytes.decode('utf-8', errors='replace')
            
            self.state.stats['bytes_downloaded'] += len(content_bytes)
            
            return content, content_type
            
        except HTTPError as e:
            if e.code == 429:
                # Rate limited - back off
                retry_after = e.headers.get('Retry-After', '60')
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    wait_time = 60
                self._backoff_until = time.time() + wait_time
                self._log(f"  Rate limited, backing off for {wait_time}s")
            elif e.code >= 500:
                self._log(f"  Server error: {e.code}")
            else:
                self._log(f"  HTTP error: {e.code}")
            return None, None
            
        except URLError as e:
            self._log(f"  URL error: {e.reason}")
            return None, None
            
        except Exception as e:
            self._log(f"  Error: {e}")
            return None, None
    
    def _is_skippable_extension(self, url: str) -> bool:
        """Check if URL has an extension that should be skipped."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Check each skip extension
        for ext in SKIP_EXTENSIONS:
            if path.endswith(ext):
                return True
        
        # Handle compound extensions like .tar.gz
        if '.tar.' in path:
            return True
        
        return False
    
    def _is_skippable_path(self, url: str) -> bool:
        """Check if URL path indicates non-documentation content."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        for pattern in SKIP_PATH_PATTERNS:
            if pattern in path:
                return True
        
        return False
    
    def _is_under_base_path(self, url: str) -> bool:
        """Check if URL is under the base path."""
        if not self.same_path:
            return True
        
        if not self.base_path:
            return True
        
        parsed = urlparse(url)
        url_path = parsed.path.rstrip('/')
        
        # URL must start with base_path
        # e.g., base_path="/3.11" should match "/3.11", "/3.11/", "/3.11/library/", etc.
        if url_path == self.base_path:
            return True
        if url_path.startswith(self.base_path + '/'):
            return True
        
        return False
    
    def _should_crawl(self, url: str, depth: int = 0) -> bool:
        """Check if URL should be crawled."""
        # Already visited
        if url in self.state.visited:
            return False
        
        # Depth check
        if self.max_depth is not None and depth > self.max_depth:
            return False
        
        # Skip non-HTML extensions
        if self._is_skippable_extension(url):
            return False
        
        # Skip obvious non-doc paths
        if self._is_skippable_path(url):
            return False
        
        # Domain check
        if self.stay_on_domain and not is_same_domain(url, self.base_url):
            return False
        
        # Path prefix check (the critical bug fix!)
        if not self._is_under_base_path(url):
            return False
        
        # Robots.txt check
        if not self.robots.can_fetch(url):
            return False
        
        # Custom filter
        if self.url_filter and not self.url_filter(url):
            return False
        
        return True
    
    def _save_page(self, url: str, data: dict):
        """Save page data to disk."""
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(data, f)
    
    def crawl(self, resume: bool = True) -> Dict[str, Any]:
        """
        Start or resume crawling.
        
        Args:
            resume: If True, resume from saved state if available
            
        Returns:
            dict with crawl statistics
        """
        # Load robots.txt
        self._log("Loading robots.txt...")
        self.robots.load()
        
        # Get crawl delay from robots.txt
        robots_delay = self.robots.get_crawl_delay(self.delay)
        if robots_delay > self.delay:
            self._log(f"Respecting robots.txt crawl-delay: {robots_delay}s")
            self.delay = robots_delay
        
        # Load or initialize state
        if resume and self.state.load():
            self._log(f"Resuming crawl: {len(self.state.visited)} pages visited, {len(self.state.pending)} pending")
        else:
            self.state.clear()
            self.state.pending.append((self.base_url, 0))  # (url, depth)
            self.state.stats['start_time'] = time.time()
        
        # Log crawl parameters
        if self.same_path:
            self._log(f"Path restriction: {self.base_path}/*")
        if self.max_depth is not None:
            self._log(f"Max depth: {self.max_depth}")
        self._log("")
        
        pages_since_checkpoint = 0
        
        try:
            while self.state.pending:
                # Check max pages limit
                if self.max_pages and self.state.stats['pages_crawled'] >= self.max_pages:
                    self._log(f"\nReached max pages limit: {self.max_pages}")
                    break
                
                # Get next URL and depth
                item = self.state.pending.popleft()
                if isinstance(item, tuple):
                    url, depth = item
                else:
                    url, depth = item, 0
                
                # Skip if already visited or shouldn't crawl
                if url in self.state.visited:
                    continue
                
                if not self._should_crawl(url, depth):
                    self.state.stats['pages_skipped'] += 1
                    continue
                
                # Mark as visited
                self.state.visited.add(url)
                
                # Fetch page
                self._log(f"{self._progress()} Crawling: {url}")
                content, content_type = self._fetch(url)
                
                if content is None:
                    # Track failure for retry
                    retry_count = self.state.failed.get(url, 0)
                    if retry_count < self.MAX_RETRIES:
                        self.state.failed[url] = retry_count + 1
                        self.state.pending.append((url, depth))
                        self.state.visited.discard(url)
                    else:
                        self.state.stats['pages_failed'] += 1
                    continue
                
                # Check if HTML
                if not is_html_content(content_type):
                    self._log(f"  Skipping non-HTML: {content_type}")
                    self.state.stats['pages_skipped'] += 1
                    continue
                
                # Extract content
                extracted = extract_text(content)
                
                # Extract and queue links (at depth + 1)
                links = extract_links(content, url)
                new_depth = depth + 1
                for link in links:
                    if self._should_crawl(link, new_depth):
                        self.state.pending.append((link, new_depth))
                
                # Save page data
                page_data = {
                    'url': url,
                    'title': extracted['title'],
                    'description': extracted['description'],
                    'text': extracted['text'],
                    'headings': extracted['headings'],
                    'depth': depth,
                    'crawled_at': time.time()
                }
                self._save_page(url, page_data)
                
                # Update stats
                self.state.stats['pages_crawled'] += 1
                pages_since_checkpoint += 1
                
                # Checkpoint
                if pages_since_checkpoint >= self.CHECKPOINT_INTERVAL:
                    self._log(f"  Saving checkpoint...")
                    self.state.stats['last_checkpoint'] = time.time()
                    self.state.save()
                    pages_since_checkpoint = 0
                
        except KeyboardInterrupt:
            self._log("\nCrawl interrupted by user")
        
        finally:
            # Final save
            self.state.stats['last_checkpoint'] = time.time()
            self.state.save()
        
        # Calculate final stats
        elapsed = time.time() - (self.state.stats['start_time'] or time.time())
        stats = {
            **self.state.stats,
            'elapsed_seconds': elapsed,
            'pages_per_minute': (self.state.stats['pages_crawled'] / elapsed * 60) if elapsed > 0 else 0,
            'pending_urls': len(self.state.pending),
            'unique_urls_seen': len(self.state.visited)
        }
        
        self._log(f"\nCrawl complete!")
        self._log(f"  Pages crawled: {stats['pages_crawled']}")
        self._log(f"  Pages skipped: {stats['pages_skipped']}")
        self._log(f"  Pages failed: {stats['pages_failed']}")
        self._log(f"  Data downloaded: {stats['bytes_downloaded'] / 1024 / 1024:.1f} MB")
        self._log(f"  Time elapsed: {elapsed / 60:.1f} minutes")
        
        return stats
    
    def get_crawled_pages(self):
        """Generator that yields all crawled page data."""
        for page_file in self.pages_dir.glob('*.json'):
            try:
                with open(page_file, 'r') as f:
                    yield json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
