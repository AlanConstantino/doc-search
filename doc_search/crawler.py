"""
Web crawler with resumable state, rate limiting, and robots.txt compliance.
Supports parallel crawling with per-domain rate limiting.
"""

import json
import time
import gzip
import hashlib
import threading
from pathlib import Path
from typing import Optional, Set, Dict, Any, Callable, Tuple, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

from .utils import (
    normalize_url, is_same_domain, url_to_filename, 
    is_html_content, get_domain, make_basic_auth_header,
    create_permissive_ssl_context
)
from .robots import RobotsChecker
from .parser import extract_text, extract_links
from .constants import (
    DEFAULT_CRAWL_DELAY, DEFAULT_REQUEST_TIMEOUT, MAX_CRAWL_RETRIES,
    CHECKPOINT_INTERVAL as CHECKPOINT_INTERVAL_CONST, DEFAULT_RATE_LIMIT_BACKOFF
)
from .crawl_state import CrawlState
from .rate_limiter import RateLimiter


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


class Crawler:
    """
    Web crawler with politeness controls, resumable crawling, and parallel fetching.
    """
    
    USER_AGENT = "DocSearchBot/1.2 (+https://github.com/AlanConstantino/doc-search)"
    MAX_RETRIES = MAX_CRAWL_RETRIES
    CHECKPOINT_INTERVAL = CHECKPOINT_INTERVAL_CONST
    
    def __init__(
        self,
        base_url: str,
        data_dir: Path,
        delay: float = DEFAULT_CRAWL_DELAY,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        auth: Optional[Tuple[str, str]] = None,  # (username, password)
        auth_token: Optional[str] = None,  # Pre-encoded Base64 token
        stay_on_domain: bool = True,
        same_path: bool = False,  # If True, only crawl URLs under the starting path
        url_filter: Optional[Callable[[str], bool]] = None,
        verbose: bool = True,
        workers: int = 1,  # Number of parallel workers
        extract_docs: bool = False,  # Extract text from PDFs and Office docs
        incremental: bool = False  # Only re-download changed pages
    ):
        self.base_url = normalize_url(base_url)
        self.base_domain = get_domain(base_url)
        self.data_dir = Path(data_dir)
        self.delay = delay
        self.timeout = timeout
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.auth = auth
        self.auth_token = auth_token
        self.stay_on_domain = stay_on_domain
        self.same_path = same_path
        self.url_filter = url_filter
        self.verbose = verbose
        self.workers = max(1, workers)  # At least 1 worker
        self.extract_docs = extract_docs
        self.incremental = incremental
        
        # Initialize PDF extractor if document extraction is enabled
        self._pdf_extractor = None
        if self.extract_docs:
            from .pdf_extractor import PDFExtractor
            self._pdf_extractor = PDFExtractor(
                timeout=timeout,
                user_agent=self.USER_AGENT,
                auth=auth,
                auth_token=auth_token
            )
        
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
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(delay)
        
        # SSL context that doesn't verify (for self-signed certs in docs)
        self.ssl_context = create_permissive_ssl_context()
        
        # Output lock for verbose messages
        self._print_lock = threading.Lock()
        
        # Stop flag for graceful shutdown
        self._stop_requested = False
    
    def _log(self, message: str):
        """Print message if verbose mode is enabled (thread-safe)."""
        if self.verbose:
            with self._print_lock:
                print(message)
    
    def _get_auth_header(self) -> Optional[str]:
        """Get Basic Auth header if credentials provided."""
        return make_basic_auth_header(auth=self.auth, auth_token=self.auth_token)
    
    def _get_page_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Load existing page metadata for incremental crawling."""
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _content_hash(self, content: str) -> str:
        """Generate SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _fetch(self, url: str, etag: Optional[str] = None, 
               last_modified: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        Fetch a URL and return (content, content_type, metadata).
        Returns (None, None, {}) on failure.
        
        For incremental crawling, pass etag/last_modified from previous crawl.
        Returns content=None with metadata={'not_modified': True} if unchanged.
        """
        domain = get_domain(url)
        self.rate_limiter.wait_for_domain(domain)
        
        headers = {
            'User-Agent': self.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        # Add conditional headers for incremental crawling
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified
        
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
            
            self.state.increment_stat('bytes_downloaded', len(content_bytes))
            
            # Capture metadata for incremental crawling
            metadata = {
                'etag': response.headers.get('ETag'),
                'last_modified': response.headers.get('Last-Modified'),
            }
            
            return content, content_type, metadata
            
        except HTTPError as e:
            if e.code == 304:
                # Not Modified - content unchanged
                return None, None, {'not_modified': True}
            elif e.code == 429:
                # Rate limited - back off
                retry_after = e.headers.get('Retry-After', str(DEFAULT_RATE_LIMIT_BACKOFF))
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    wait_time = DEFAULT_RATE_LIMIT_BACKOFF
                self.rate_limiter.set_backoff(domain, wait_time)
                self._log(f"  Rate limited, backing off for {wait_time}s")
                return None, None, {
                    'error_type': 'http',
                    'error_message': f'HTTP {e.code}: Rate limited (retry after {wait_time}s)'
                }
            elif e.code >= 500:
                self._log(f"  Server error: {e.code}")
                return None, None, {
                    'error_type': 'http',
                    'error_message': f'HTTP {e.code}: Server error'
                }
            else:
                self._log(f"  HTTP error: {e.code}")
                return None, None, {
                    'error_type': 'http',
                    'error_message': f'HTTP {e.code}'
                }
            
        except URLError as e:
            reason = str(e.reason)
            # Check for SSL errors
            if 'ssl' in reason.lower() or 'certificate' in reason.lower():
                self._log(f"  SSL error: {reason}")
                return None, None, {
                    'error_type': 'ssl',
                    'error_message': reason
                }
            # Check for timeout
            elif 'timed out' in reason.lower() or 'timeout' in reason.lower():
                self._log(f"  Timeout: {reason}")
                return None, None, {
                    'error_type': 'timeout',
                    'error_message': reason
                }
            else:
                self._log(f"  URL error: {reason}")
                return None, None, {
                    'error_type': 'network',
                    'error_message': reason
                }
            
        except ssl.SSLError as e:
            message = str(e)
            self._log(f"  SSL error: {message}")
            return None, None, {
                'error_type': 'ssl',
                'error_message': message
            }
            
        except TimeoutError as e:
            message = str(e) or 'Connection timed out'
            self._log(f"  Timeout: {message}")
            return None, None, {
                'error_type': 'timeout',
                'error_message': message
            }
            
        except Exception as e:
            message = str(e)
            self._log(f"  Error: {message}")
            return None, None, {
                'error_type': 'unknown',
                'error_message': message
            }
    
    def _is_skippable_extension(self, url: str) -> bool:
        """Check if URL has an extension that should be skipped."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Check each skip extension
        for ext in SKIP_EXTENSIONS:
            if path.endswith(ext):
                return True
        
        # Check extractable document extensions
        # Skip them unless extract_docs is enabled
        if not self.extract_docs:
            for ext in EXTRACTABLE_DOC_EXTENSIONS:
                if path.endswith(ext):
                    return True
        
        # Handle compound extensions like .tar.gz
        if '.tar.' in path:
            return True
        
        return False
    
    def _is_extractable_doc(self, url: str) -> bool:
        """Check if URL is an extractable document (PDF, DOCX, etc.)."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in EXTRACTABLE_DOC_EXTENSIONS:
            if path.endswith(ext):
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
    
    def _should_crawl(self, url: str, depth: int = 0, force: bool = False) -> bool:
        """Check if URL should be crawled."""
        # Already visited (skip in incremental mode with force=True)
        if not force and self.state.is_visited(url):
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
    
    def _process_page(self, url: str, depth: int) -> Optional[List[Tuple[str, int]]]:
        """
        Process a single page. Returns list of new URLs to crawl or None on failure.
        """
        if self._stop_requested:
            return None
        
        # Mark as visited
        self.state.mark_visited(url)
        
        # Check if this is an extractable document (PDF, DOCX, etc.)
        if self.extract_docs and self._is_extractable_doc(url):
            return self._process_document(url, depth)
        
        # For incremental crawling, load existing page metadata
        existing_meta = None
        etag = None
        last_modified = None
        if self.incremental:
            existing_meta = self._get_page_metadata(url)
            if existing_meta:
                etag = existing_meta.get('etag')
                last_modified = existing_meta.get('last_modified')
        
        # Fetch page
        self._log(f"{self.state.get_progress(self.max_pages)} Crawling: {url}")
        content, content_type, fetch_meta = self._fetch(url, etag=etag, last_modified=last_modified)
        
        # Handle 304 Not Modified (incremental crawling)
        if fetch_meta.get('not_modified'):
            self._log(f"  ⏭️  Unchanged (304): {url}")
            self.state.increment_stat('pages_unchanged')
            # Still extract links from existing content for discovery
            if existing_meta and existing_meta.get('text'):
                # Re-parse for links (we don't store raw HTML, so skip link extraction)
                pass
            return []
        
        if content is None:
            # Record error if available in metadata
            error_type = fetch_meta.get('error_type')
            error_message = fetch_meta.get('error_message')
            if error_type and error_message:
                self.state.record_error(url, error_type, error_message)
            
            # Track failure for retry
            self.state.mark_failed(url, depth)
            return None
        
        # Check if HTML
        if not is_html_content(content_type):
            self._log(f"  Skipping non-HTML: {content_type}")
            self.state.increment_stat('pages_skipped')
            return []
        
        # For incremental: check content hash to detect changes even without 304
        content_hash = self._content_hash(content)
        if self.incremental and existing_meta:
            if existing_meta.get('content_hash') == content_hash:
                self._log(f"  ⏭️  Unchanged (same hash): {url}")
                self.state.increment_stat('pages_unchanged')
                return []
        
        # Extract content
        extracted = extract_text(content)
        
        # Extract and queue links (at depth + 1)
        links = extract_links(content, url)
        new_depth = depth + 1
        new_urls = []
        for link in links:
            if self._should_crawl(link, new_depth):
                new_urls.append((link, new_depth))
        
        # Save page data with incremental metadata
        page_data = {
            'url': url,
            'title': extracted['title'],
            'description': extracted['description'],
            'text': extracted['text'],
            'headings': extracted['headings'],
            'depth': depth,
            'crawled_at': time.time(),
            # Incremental crawling metadata
            'etag': fetch_meta.get('etag'),
            'last_modified': fetch_meta.get('last_modified'),
            'content_hash': content_hash,
        }
        self._save_page(url, page_data)
        
        # Update stats
        self.state.increment_stat('pages_crawled')
        
        return new_urls
    
    def _process_document(self, url: str, depth: int) -> Optional[List[Tuple[str, int]]]:
        """
        Process an extractable document (PDF, DOCX, etc.).
        Returns empty list (documents don't contain links to crawl).
        """
        self._log(f"{self.state.get_progress(self.max_pages)} Extracting: {url}")
        
        # Currently only PDF extraction is implemented
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        if path.endswith('.pdf'):
            result = self._pdf_extractor.extract_from_url(url)
            
            if result['error']:
                self._log(f"  Document extraction failed: {result['error']}")
                self.state.record_error(url, 'parse', f"PDF extraction failed: {result['error']}")
                self.state.mark_failed(url, depth)
                return None
            
            # Save document data
            page_data = {
                'url': url,
                'title': result['title'] or Path(parsed.path).stem,
                'description': f"PDF document, {result['pages']} pages",
                'text': result['text'],
                'headings': [],  # PDFs don't have structured headings
                'depth': depth,
                'crawled_at': time.time(),
                'doc_type': 'pdf',
                'doc_pages': result['pages'],
                'doc_metadata': result['metadata']
            }
            self._save_page(url, page_data)
            
            # Update stats
            self.state.increment_stat('pages_crawled')
            self.state.increment_stat('docs_extracted')
            
            self._log(f"  Extracted {result['pages']} pages, {len(result['text'])} chars")
            return []
        
        # DOCX/XLSX extraction not yet implemented
        self._log(f"  Skipping unsupported document type: {path}")
        self.state.increment_stat('pages_skipped')
        return []
    
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
            self.rate_limiter = RateLimiter(self.delay)
        
        # Load or initialize state
        if self.incremental:
            # Incremental mode: re-check all previously crawled pages
            self._log("Loading existing pages for incremental crawl...")
            existing_urls = []
            for page_file in self.pages_dir.glob('*.json'):
                try:
                    with open(page_file, 'r') as f:
                        page_data = json.load(f)
                        if 'url' in page_data:
                            existing_urls.append((page_data['url'], page_data.get('depth', 0)))
                except (json.JSONDecodeError, IOError):
                    continue
            
            # Clear visited set and add all existing URLs to queue
            self.state.clear()
            self.state.add_urls(existing_urls)
            self.state.add_urls([(self.base_url, 0)])  # Also check for new pages from start
            with self.state._lock:
                self.state.stats['start_time'] = time.time()
            self._log(f"Found {len(existing_urls)} pages to check for updates")
        elif resume and self.state.load():
            self._log(f"Resuming crawl: {len(self.state.visited)} pages visited, {len(self.state.pending)} pending")
        else:
            self.state.clear()
            self.state.add_urls([(self.base_url, 0)])
            with self.state._lock:
                self.state.stats['start_time'] = time.time()
        
        # Log crawl parameters
        if self.same_path:
            self._log(f"📁 Path restriction: {self.base_path}/*")
        else:
            self._log(f"🌐 Crawling entire domain: {self.base_domain}")
        if self.incremental:
            self._log(f"🔄 Incremental mode: only re-downloading changed pages")
        if self.max_depth is not None:
            self._log(f"Max depth: {self.max_depth}")
        if self.workers > 1:
            self._log(f"Workers: {self.workers}")
        self._log("")
        
        pages_since_checkpoint = 0
        self._stop_requested = False
        
        try:
            if self.workers == 1:
                # Single-threaded mode (original behavior)
                self._crawl_single_threaded()
            else:
                # Multi-threaded mode
                self._crawl_parallel()
                
        except KeyboardInterrupt:
            self._log("\nCrawl interrupted by user")
            self._stop_requested = True
        
        finally:
            # Final save
            with self.state._lock:
                self.state.stats['last_checkpoint'] = time.time()
            self.state.save()
        
        # Calculate final stats
        with self.state._lock:
            start_time = self.state.stats.get('start_time') or time.time()
            elapsed = time.time() - start_time
            stats = {
                **self.state.stats,
                'elapsed_seconds': elapsed,
                'pages_per_minute': (self.state.stats['pages_crawled'] / elapsed * 60) if elapsed > 0 else 0,
                'pending_urls': len(self.state.pending),
                'unique_urls_seen': len(self.state.visited)
            }
        
        self._log(f"\nCrawl complete!")
        self._log(f"  Pages crawled: {stats['pages_crawled']}")
        if self.incremental and stats.get('pages_unchanged', 0) > 0:
            self._log(f"  Pages unchanged: {stats['pages_unchanged']}")
        self._log(f"  Pages skipped: {stats['pages_skipped']}")
        self._log(f"  Pages failed: {stats['pages_failed']}")
        self._log(f"  Data downloaded: {stats['bytes_downloaded'] / 1024 / 1024:.1f} MB")
        self._log(f"  Time elapsed: {elapsed / 60:.1f} minutes")
        
        return stats
    
    def _crawl_single_threaded(self):
        """Original single-threaded crawl implementation."""
        pages_since_checkpoint = 0
        
        while True:
            if self._stop_requested:
                break
            
            # Check max pages limit
            with self.state._lock:
                if self.max_pages and self.state.stats['pages_crawled'] >= self.max_pages:
                    self._log(f"\nReached max pages limit: {self.max_pages}")
                    break
            
            # Get next URL
            item = self.state.pop_url()
            if item is None:
                break
            
            url, depth = item
            
            # Skip if already visited or shouldn't crawl
            if self.state.is_visited(url):
                continue
            
            if not self._should_crawl(url, depth):
                self.state.increment_stat('pages_skipped')
                continue
            
            # Process the page
            new_urls = self._process_page(url, depth)
            
            if new_urls:
                self.state.add_urls(new_urls)
            
            # Checkpoint
            pages_since_checkpoint += 1
            if pages_since_checkpoint >= self.CHECKPOINT_INTERVAL:
                self._log(f"  Saving checkpoint...")
                with self.state._lock:
                    self.state.stats['last_checkpoint'] = time.time()
                self.state.save()
                pages_since_checkpoint = 0
    
    def _crawl_parallel(self):
        """Parallel crawl using ThreadPoolExecutor."""
        pages_since_checkpoint = 0
        active_futures = set()
        
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            while True:
                if self._stop_requested:
                    break
                
                # Check max pages limit
                with self.state._lock:
                    if self.max_pages and self.state.stats['pages_crawled'] >= self.max_pages:
                        self._log(f"\nReached max pages limit: {self.max_pages}")
                        break
                
                # Submit new tasks to keep workers busy
                while len(active_futures) < self.workers:
                    item = self.state.pop_url()
                    if item is None:
                        break
                    
                    url, depth = item
                    
                    # Skip if already visited or shouldn't crawl
                    if self.state.is_visited(url):
                        continue
                    
                    if not self._should_crawl(url, depth):
                        self.state.increment_stat('pages_skipped')
                        continue
                    
                    # Submit task
                    future = executor.submit(self._process_page, url, depth)
                    future.url_depth = (url, depth)
                    active_futures.add(future)
                
                # If no active futures and no pending URLs, we're done
                if not active_futures:
                    # Double-check pending queue
                    with self.state._lock:
                        if not self.state.pending:
                            break
                    continue
                
                # Wait for at least one task to complete
                try:
                    done_futures = set()
                    for future in as_completed(active_futures, timeout=1.0):
                        done_futures.add(future)
                        try:
                            new_urls = future.result()
                            if new_urls:
                                self.state.add_urls(new_urls)
                        except Exception as e:
                            self._log(f"  Worker error: {e}")
                        
                        pages_since_checkpoint += 1
                        
                        # Checkpoint
                        if pages_since_checkpoint >= self.CHECKPOINT_INTERVAL:
                            self._log(f"  Saving checkpoint...")
                            with self.state._lock:
                                self.state.stats['last_checkpoint'] = time.time()
                            self.state.save()
                            pages_since_checkpoint = 0
                    
                    active_futures -= done_futures
                    
                except (TimeoutError, FuturesTimeoutError):
                    # Timeout is fine, just continue checking
                    pass
            
            # Cancel remaining futures on stop
            for future in active_futures:
                future.cancel()
    
    def get_crawled_pages(self):
        """Generator that yields all crawled page data."""
        for page_file in self.pages_dir.glob('*.json'):
            try:
                with open(page_file, 'r') as f:
                    yield json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
