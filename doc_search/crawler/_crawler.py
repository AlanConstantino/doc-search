"""
Web crawler with resumable state, rate limiting, and robots.txt compliance.
Supports parallel crawling with per-domain rate limiting.

The Crawler class is a thin orchestrator that delegates to:
- Fetcher: HTTP fetching with rate limiting and error handling
- UrlFilter: URL validation, filtering, and crawl decisions
- PageProcessor: HTML processing, content extraction, and persistence
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional, Set, Dict, Any, Callable, Tuple, List
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

from ..utils import normalize_url, get_domain, create_permissive_ssl_context
from ..robots import RobotsChecker
from ..constants import (
    DEFAULT_CRAWL_DELAY, DEFAULT_REQUEST_TIMEOUT, MAX_CRAWL_RETRIES,
    CHECKPOINT_INTERVAL as CHECKPOINT_INTERVAL_CONST
)
from ..crawl_state import CrawlState
from ..rate_limiter import RateLimiter
from .fetcher import Fetcher
from .url_filter import UrlFilter
from .processor import PageProcessor, build_document_data


class Crawler:
    """
    Web crawler with politeness controls, resumable crawling, and parallel fetching.
    
    This class orchestrates the crawling process by delegating to specialized modules:
    - Fetcher: Handles HTTP requests with rate limiting and retries
    - UrlFilter: Determines which URLs should be crawled
    - PageProcessor: Extracts content and manages page persistence
    
    The Crawler manages:
    - Crawl state (visited URLs, pending queue, statistics)
    - Parallel execution with configurable workers
    - Checkpoint saving for resumable crawls
    - Graceful shutdown on interruption
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
        auth: Optional[Tuple[str, str]] = None,
        auth_token: Optional[str] = None,
        stay_on_domain: bool = True,
        same_path: bool = False,
        url_filter: Optional[Callable[[str], bool]] = None,
        verbose: bool = True,
        workers: int = 1,
        extract_docs: bool = False,
        incremental: bool = False,
        save_html: bool = True
    ):
        """
        Initialize the crawler.
        
        Args:
            base_url: Starting URL for the crawl.
            data_dir: Directory for storing crawl data and state.
            delay: Minimum delay between requests to same domain.
            timeout: HTTP request timeout in seconds.
            max_pages: Maximum pages to crawl (None for unlimited).
            max_depth: Maximum crawl depth (None for unlimited).
            auth: Tuple of (username, password) for Basic Auth.
            auth_token: Pre-encoded Base64 auth token.
            stay_on_domain: If True, only crawl URLs on same domain.
            same_path: If True, only crawl URLs under the starting path.
            url_filter: Optional custom filter function for URLs.
            verbose: If True, print progress messages.
            workers: Number of parallel workers (default 1).
            extract_docs: If True, extract text from PDF documents.
            incremental: If True, only re-download changed pages.
            save_html: If True, save raw HTML for re-parsing later (default: True).
        """
        self.base_url = normalize_url(base_url)
        self.base_domain = get_domain(base_url)
        self.data_dir = Path(data_dir)
        self.delay = delay
        self.timeout = timeout
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.verbose = verbose
        self.workers = max(1, workers)
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
        
        # Setup directories
        self.pages_dir = self.data_dir / 'pages'
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize state
        self.state = CrawlState(self.data_dir / 'crawl_state.json')
        
        # Initialize robots checker
        self.robots = RobotsChecker(base_url, self.USER_AGENT)
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(delay)
        
        # SSL context (permissive for self-signed certs)
        ssl_context = create_permissive_ssl_context()
        
        # Output lock for verbose messages
        self._print_lock = threading.Lock()
        
        # Stop flag for graceful shutdown
        self._stop_requested = False
        
        # Initialize Fetcher module
        self._fetcher = Fetcher(
            user_agent=self.USER_AGENT,
            delay=delay,
            timeout=timeout,
            auth=auth,
            auth_token=auth_token,
            rate_limiter=self.rate_limiter,
            ssl_context=ssl_context,
            log_func=self._log,
            stats_callback=self._update_stat
        )
        
        # Initialize UrlFilter module
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
        
        # Initialize PageProcessor module
        self.save_html = save_html
        self._processor = PageProcessor(self.pages_dir, save_html=save_html)
    
    # -------------------------------------------------------------------------
    # Logging and stats (orchestrator responsibilities)
    # -------------------------------------------------------------------------
    
    def _log(self, message: str):
        """Print message if verbose mode is enabled (thread-safe)."""
        if self.verbose:
            with self._print_lock:
                print(message)
    
    def _update_stat(self, stat_name: str, value: int):
        """Update a crawl statistic (thread-safe)."""
        self.state.increment_stat(stat_name, value)
    
    # -------------------------------------------------------------------------
    # Backward-compatible wrapper methods (delegate to modules)
    # -------------------------------------------------------------------------
    
    def _fetch(self, url: str, etag: Optional[str] = None,
               last_modified: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        Fetch a URL and return (content, content_type, metadata).
        
        Wrapper for backward compatibility - delegates to Fetcher module.
        
        Args:
            url: URL to fetch.
            etag: ETag for conditional request.
            last_modified: Last-Modified for conditional request.
            
        Returns:
            Tuple of (content, content_type, metadata).
        """
        result = self._fetcher.fetch(url, etag=etag, last_modified=last_modified)
        return result.as_tuple()
    
    def _get_page_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Load existing page metadata for incremental crawling.
        
        Wrapper for backward compatibility - delegates to PageProcessor module.
        """
        return self._processor.load_page_metadata(url)
    
    def _save_page(self, url: str, data: dict):
        """
        Save page data to disk.
        
        Wrapper for backward compatibility - delegates to PageProcessor module.
        """
        self._processor.save_page(url, data)
    
    # -------------------------------------------------------------------------
    # URL filtering (delegates to UrlFilter)
    # -------------------------------------------------------------------------
    
    def _should_crawl(self, url: str, depth: int = 0, force: bool = False) -> bool:
        """
        Check if URL should be crawled.
        
        Delegates to UrlFilter.should_follow() which checks:
        - Already visited
        - Depth limits
        - Extension filtering
        - Path patterns
        - Domain restrictions
        - Robots.txt compliance
        - Custom filters
        
        Args:
            url: URL to check.
            depth: Current crawl depth.
            force: If True, skip visited check (for incremental crawling).
            
        Returns:
            True if the URL should be crawled.
        """
        return self._url_filter.should_follow(
            url,
            depth=depth,
            is_visited_func=self.state.is_visited,
            force=force,
        )
    
    # -------------------------------------------------------------------------
    # Page processing (orchestrates Fetcher and PageProcessor)
    # -------------------------------------------------------------------------
    
    def _process_page(self, url: str, depth: int) -> Optional[List[Tuple[str, int]]]:
        """
        Process a single page. Returns list of new URLs to crawl or None on failure.
        
        This method orchestrates:
        1. Marking URL as visited
        2. Document extraction (if applicable)
        3. Fetching with incremental support
        4. Content processing
        5. Page persistence
        """
        if self._stop_requested:
            return None
        
        # Mark as visited
        self.state.mark_visited(url)
        
        # Handle extractable documents (PDF, etc.)
        if self.extract_docs and self._url_filter.is_extractable_doc(url):
            return self._process_document(url, depth)
        
        # For incremental crawling, get existing metadata for conditional requests
        existing_meta = None
        etag = None
        last_modified = None
        if self.incremental:
            existing_meta = self._processor.load_page_metadata(url)
            if existing_meta:
                etag = existing_meta.get('etag')
                last_modified = existing_meta.get('last_modified')
        
        # Fetch the page (Fetcher handles rate limiting, retries, decompression)
        self._log(f"{self.state.get_progress(self.max_pages)} Crawling: {url}")
        fetch_result = self._fetcher.fetch(url, etag=etag, last_modified=last_modified)
        
        # Handle 304 Not Modified
        if fetch_result.not_modified:
            self._log(f"  ⏭️  Unchanged (304): {url}")
            self.state.increment_stat('pages_unchanged')
            return []
        
        # Handle fetch errors
        if not fetch_result.success:
            if fetch_result.error_type and fetch_result.error_message:
                self.state.record_error(url, fetch_result.error_type, fetch_result.error_message)
            self.state.mark_failed(url, depth)
            return None
        
        content = fetch_result.content
        content_type = fetch_result.content_type or ''
        
        # Skip non-HTML content
        from ..utils import is_html_content
        if not is_html_content(content_type):
            self._log(f"  Skipping non-HTML: {content_type}")
            self.state.increment_stat('pages_skipped')
            return []
        
        # For incremental: check content hash even without 304
        if self.incremental and existing_meta:
            changed, _ = self._processor.is_content_changed(content, existing_meta)
            if not changed:
                self._log(f"  ⏭️  Unchanged (same hash): {url}")
                self.state.increment_stat('pages_unchanged')
                return []
        
        # Process HTML (PageProcessor handles extraction and builds page data)
        result = self._processor.process_html(
            url=url,
            html=content,
            depth=depth,
            etag=fetch_result.metadata.get('etag'),
            last_modified=fetch_result.metadata.get('last_modified'),
            link_filter=self._should_crawl,
        )
        
        # Save page data
        self._processor.save_page(url, result['page_data'])
        
        # Update stats
        self.state.increment_stat('pages_crawled')
        
        return result['links']
    
    def _process_document(self, url: str, depth: int) -> Optional[List[Tuple[str, int]]]:
        """
        Process an extractable document (PDF, DOCX, etc.).
        
        Returns empty list (documents don't contain links to crawl).
        """
        self._log(f"{self.state.get_progress(self.max_pages)} Extracting: {url}")
        
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
            self._processor.save_page(url, page_data)
            
            # Update stats
            self.state.increment_stat('pages_crawled')
            self.state.increment_stat('docs_extracted')
            
            self._log(f"  Extracted {result['pages']} pages, {len(result['text'])} chars")
            return []
        
        # DOCX/XLSX extraction not yet implemented
        self._log(f"  Skipping unsupported document type: {path}")
        self.state.increment_stat('pages_skipped')
        return []
    
    # -------------------------------------------------------------------------
    # Crawl execution (queue management and parallel coordination)
    # -------------------------------------------------------------------------
    
    def crawl(self, resume: bool = True) -> Dict[str, Any]:
        """
        Start or resume crawling.
        
        Args:
            resume: If True, resume from saved state if available.
            
        Returns:
            Dict with crawl statistics.
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
            self._fetcher.rate_limiter = self.rate_limiter
        
        # Load or initialize state
        if self.incremental:
            self._setup_incremental_crawl()
        elif resume and self.state.load():
            self._log(f"Resuming crawl: {len(self.state.visited)} pages visited, {len(self.state.pending)} pending")
        else:
            self.state.clear()
            self.state.add_urls([(self.base_url, 0)])
            with self.state._lock:
                self.state.stats['start_time'] = time.time()
        
        # Log crawl parameters
        self._log_crawl_parameters()
        
        self._stop_requested = False
        
        try:
            if self.workers == 1:
                self._crawl_single_threaded()
            else:
                self._crawl_parallel()
                
        except KeyboardInterrupt:
            self._log("\nCrawl interrupted by user")
            self._stop_requested = True
        
        finally:
            with self.state._lock:
                self.state.stats['last_checkpoint'] = time.time()
            self.state.save()
        
        return self._compute_final_stats()
    
    def _setup_incremental_crawl(self):
        """Set up state for incremental crawling."""
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
        
        self.state.clear()
        self.state.add_urls(existing_urls)
        self.state.add_urls([(self.base_url, 0)])
        with self.state._lock:
            self.state.stats['start_time'] = time.time()
        self._log(f"Found {len(existing_urls)} pages to check for updates")
    
    def _log_crawl_parameters(self):
        """Log the crawl configuration."""
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
    
    def _compute_final_stats(self) -> Dict[str, Any]:
        """Compute and log final crawl statistics."""
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
        """Single-threaded crawl implementation."""
        pages_since_checkpoint = 0
        
        while True:
            if self._stop_requested:
                break
            
            with self.state._lock:
                if self.max_pages and self.state.stats['pages_crawled'] >= self.max_pages:
                    self._log(f"\nReached max pages limit: {self.max_pages}")
                    break
            
            item = self.state.pop_url()
            if item is None:
                break
            
            url, depth = item
            
            if self.state.is_visited(url):
                continue
            
            if not self._should_crawl(url, depth):
                self.state.increment_stat('pages_skipped')
                continue
            
            new_urls = self._process_page(url, depth)
            
            if new_urls:
                self.state.add_urls(new_urls)
            
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
                    
                    if self.state.is_visited(url):
                        continue
                    
                    if not self._should_crawl(url, depth):
                        self.state.increment_stat('pages_skipped')
                        continue
                    
                    future = executor.submit(self._process_page, url, depth)
                    future.url_depth = (url, depth)
                    active_futures.add(future)
                
                if not active_futures:
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
                        
                        if pages_since_checkpoint >= self.CHECKPOINT_INTERVAL:
                            self._log(f"  Saving checkpoint...")
                            with self.state._lock:
                                self.state.stats['last_checkpoint'] = time.time()
                            self.state.save()
                            pages_since_checkpoint = 0
                    
                    active_futures -= done_futures
                    
                except (TimeoutError, FuturesTimeoutError):
                    pass
            
            for future in active_futures:
                future.cancel()
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    def get_crawled_pages(self, warn_on_error: bool = True):
        """
        Generator that yields all crawled page data.
        
        Args:
            warn_on_error: If True, print a warning for skipped corrupted files.
        """
        yield from self._processor.iter_saved_pages(warn_on_error=warn_on_error)
