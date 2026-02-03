"""
Web crawler with resumable state, rate limiting, and robots.txt compliance.
Supports parallel crawling with per-domain rate limiting.
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional, Set, Dict, Any, Callable, Tuple, List
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

from ..utils import (
    normalize_url, is_same_domain, url_to_filename, 
    is_html_content, get_domain, make_basic_auth_header,
    create_permissive_ssl_context
)
from ..robots import RobotsChecker
from ..constants import (
    DEFAULT_CRAWL_DELAY, DEFAULT_REQUEST_TIMEOUT, MAX_CRAWL_RETRIES,
    CHECKPOINT_INTERVAL as CHECKPOINT_INTERVAL_CONST
)
from ..crawl_state import CrawlState
from ..rate_limiter import RateLimiter
from .fetcher import Fetcher
from .url_filter import (
    SKIP_EXTENSIONS,
    EXTRACTABLE_DOC_EXTENSIONS,
    SKIP_PATH_PATTERNS,
    UrlFilter,
)
from .processor import PageProcessor, build_document_data


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
            from ..pdf_extractor import PDFExtractor
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
        
        # Initialize fetcher
        self._fetcher = Fetcher(
            user_agent=self.USER_AGENT,
            delay=delay,
            timeout=timeout,
            auth=auth,
            auth_token=auth_token,
            rate_limiter=self.rate_limiter,
            ssl_context=self.ssl_context,
            log_func=self._log,
            stats_callback=self._update_stat
        )
        
        # Initialize URL filter
        self._url_filter = UrlFilter(
            base_url=base_url,
            robots_checker=self.robots,
            stay_on_domain=stay_on_domain,
            same_path=same_path,
            extract_docs=extract_docs,
            max_depth=max_depth,
            url_filter=url_filter,
        )
        # Sync base_path and same_path from UrlFilter (it may adjust for root paths)
        self.base_path = self._url_filter.base_path
        self.same_path = self._url_filter.same_path
        
        # Initialize page processor
        self._processor = PageProcessor(self.pages_dir)
    
    def _log(self, message: str):
        """Print message if verbose mode is enabled (thread-safe)."""
        if self.verbose:
            with self._print_lock:
                print(message)
    
    def _update_stat(self, stat_name: str, value: int):
        """Update a crawl statistic (thread-safe)."""
        self.state.increment_stat(stat_name, value)
    
    def _get_auth_header(self) -> Optional[str]:
        """Get Basic Auth header if credentials provided."""
        return make_basic_auth_header(auth=self.auth, auth_token=self.auth_token)
    
    def _get_page_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Load existing page metadata for incremental crawling."""
        return self._processor.load_page_metadata(url)
    
    def _fetch(self, url: str, etag: Optional[str] = None, 
               last_modified: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        Fetch a URL and return (content, content_type, metadata).
        Returns (None, None, {}) on failure.
        
        For incremental crawling, pass etag/last_modified from previous crawl.
        Returns content=None with metadata={'not_modified': True} if unchanged.
        """
        result = self._fetcher.fetch(url, etag=etag, last_modified=last_modified)
        return result.as_tuple()
    
    def _is_skippable_extension(self, url: str) -> bool:
        """Check if URL has an extension that should be skipped."""
        return self._url_filter.is_skippable_extension(url)
    
    def _is_extractable_doc(self, url: str) -> bool:
        """Check if URL is an extractable document (PDF, DOCX, etc.)."""
        return self._url_filter.is_extractable_doc(url)
    
    def _is_skippable_path(self, url: str) -> bool:
        """Check if URL path indicates non-documentation content."""
        return self._url_filter.is_skippable_path(url)
    
    def _is_under_base_path(self, url: str) -> bool:
        """Check if URL is under the base path."""
        return self._url_filter.is_under_base_path(url)
    
    def _should_crawl(self, url: str, depth: int = 0, force: bool = False) -> bool:
        """Check if URL should be crawled."""
        return self._url_filter.should_follow(
            url,
            depth=depth,
            is_visited_func=self.state.is_visited,
            force=force,
        )
    
    def _save_page(self, url: str, data: dict):
        """Save page data to disk."""
        self._processor.save_page(url, data)
    
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
        if self.incremental and existing_meta:
            changed, _ = self._processor.is_content_changed(content, existing_meta)
            if not changed:
                self._log(f"  ⏭️  Unchanged (same hash): {url}")
                self.state.increment_stat('pages_unchanged')
                return []
        
        # Process HTML: extract text, links, and build page data
        result = self._processor.process_html(
            url=url,
            html=content,
            depth=depth,
            etag=fetch_meta.get('etag'),
            last_modified=fetch_meta.get('last_modified'),
            link_filter=self._should_crawl,
        )
        
        # Save page data
        self._save_page(url, result['page_data'])
        
        # Update stats
        self.state.increment_stat('pages_crawled')
        
        return result['links']
    
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
            
            # Build and save document data
            page_data = build_document_data(
                url=url,
                title=result['title'] or Path(parsed.path).stem,
                text=result['text'],
                depth=depth,
                doc_type='pdf',
                doc_pages=result['pages'],
                doc_metadata=result['metadata'],
            )
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
            # Update fetcher's rate limiter too
            self._fetcher.rate_limiter = self.rate_limiter
        
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
    
    def get_crawled_pages(self, warn_on_error: bool = True):
        """Generator that yields all crawled page data.
        
        Args:
            warn_on_error: If True, print a warning for skipped corrupted files.
        """
        yield from self._processor.iter_saved_pages(warn_on_error=warn_on_error)
