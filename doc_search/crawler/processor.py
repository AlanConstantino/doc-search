"""
Page processing module for the crawler.

This module handles the processing of crawled page content, including:
- HTML text extraction
- Link extraction and filtering
- Content hashing for change detection
- Page metadata construction and persistence

The PageProcessor class coordinates these operations and is used by the Crawler
to transform raw HTML into structured page data.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..parser import extract_text, extract_links
from ..utils import url_to_filename


def content_hash(content: str) -> str:
    """
    Generate SHA256 hash of content for change detection.
    
    Args:
        content: The content string to hash.
        
    Returns:
        Hex-encoded SHA256 hash of the content.
    
    Example:
        >>> content_hash("Hello, World!")
        'dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f'
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def build_page_data(
    url: str,
    extracted: Dict[str, Any],
    depth: int,
    *,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
    hash_value: Optional[str] = None,
    raw_html: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a page data dictionary from extracted content.
    
    Args:
        url: The URL of the page.
        extracted: Dict from extract_text() with keys: text, title, description, headings.
        depth: The crawl depth at which this page was found.
        etag: Optional ETag header value for incremental crawling.
        last_modified: Optional Last-Modified header value for incremental crawling.
        hash_value: Optional content hash for change detection.
        raw_html: Optional raw HTML content for re-parsing later.
    
    Returns:
        A dictionary with all page data ready for persistence.
    
    Example:
        >>> extracted = {'text': 'Hello', 'title': 'Test', 'description': '', 'headings': []}
        >>> data = build_page_data('https://example.com', extracted, depth=0)
        >>> data['url']
        'https://example.com'
        >>> data['title']
        'Test'
    """
    data = {
        'url': url,
        'title': extracted['title'],
        'description': extracted['description'],
        'text': extracted['text'],
        'headings': extracted['headings'],
        'depth': depth,
        'crawled_at': time.time(),
        # Incremental crawling metadata
        'etag': etag,
        'last_modified': last_modified,
        'content_hash': hash_value,
    }
    if raw_html is not None:
        data['raw_html'] = raw_html
    return data


def build_document_data(
    url: str,
    title: str,
    text: str,
    depth: int,
    *,
    doc_type: str,
    doc_pages: int = 0,
    doc_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build page data for an extracted document (PDF, DOCX, etc.).
    
    Args:
        url: The URL of the document.
        title: The document title.
        text: The extracted text content.
        depth: The crawl depth at which this document was found.
        doc_type: The document type (e.g., 'pdf', 'docx').
        doc_pages: Number of pages in the document.
        doc_metadata: Additional document metadata.
    
    Returns:
        A dictionary with document data ready for persistence.
    """
    return {
        'url': url,
        'title': title,
        'description': f"{doc_type.upper()} document, {doc_pages} pages",
        'text': text,
        'headings': [],  # Documents don't have structured HTML headings
        'depth': depth,
        'crawled_at': time.time(),
        'doc_type': doc_type,
        'doc_pages': doc_pages,
        'doc_metadata': doc_metadata or {},
    }


class PageProcessor:
    """
    Processes crawled pages: extracts content, builds page data, handles persistence.
    
    This class coordinates the extraction of text and links from HTML content,
    builds structured page data dictionaries, and handles saving/loading page
    data to/from disk.
    
    Args:
        pages_dir: Directory where page JSON files are stored.
    
    Example:
        >>> processor = PageProcessor(Path('/data/pages'))
        >>> result = processor.process_html('https://example.com', '<html>...</html>', depth=0)
        >>> result['page_data']['title']
        'Example Page'
    """
    
    def __init__(self, pages_dir: Path, save_html: bool = True):
        """
        Initialize the page processor.
        
        Args:
            pages_dir: Directory for storing page JSON files.
            save_html: Whether to save raw HTML content (default: True).
        """
        self.pages_dir = Path(pages_dir)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.save_html = save_html
    
    def process_html(
        self,
        url: str,
        html: str,
        depth: int,
        *,
        base_url: Optional[str] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        link_filter: Optional[Callable[[str, int], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Process HTML content and extract page data and links.
        
        This is the main entry point for processing a crawled HTML page.
        It extracts text content, metadata, and links from the HTML.
        
        Args:
            url: The URL of the page.
            html: The raw HTML content.
            depth: The crawl depth at which this page was found.
            base_url: Base URL for resolving relative links (defaults to url).
            etag: Optional ETag header for incremental crawling.
            last_modified: Optional Last-Modified header for incremental crawling.
            link_filter: Optional function(link, depth) -> bool to filter discovered links.
        
        Returns:
            A dictionary with:
            - page_data: The structured page data ready for saving.
            - links: List of (url, depth) tuples for discovered links.
            - content_hash: SHA256 hash of the HTML content.
        
        Example:
            >>> result = processor.process_html(url, html, depth=1)
            >>> result['page_data']['text']  # Extracted text
            >>> result['links']  # [(url, depth), ...]
        """
        # Calculate content hash
        hash_value = content_hash(html)
        
        # Extract text content and metadata
        extracted = extract_text(html)
        
        # Extract links (use provided base_url or fall back to url)
        resolve_base = base_url or url
        all_links = extract_links(html, resolve_base)
        
        # Apply link filter if provided
        new_depth = depth + 1
        if link_filter:
            links = [(link, new_depth) for link in all_links if link_filter(link, new_depth)]
        else:
            links = [(link, new_depth) for link in all_links]
        
        # Build page data
        page_data = build_page_data(
            url=url,
            extracted=extracted,
            depth=depth,
            etag=etag,
            last_modified=last_modified,
            hash_value=hash_value,
            raw_html=html if self.save_html else None,
        )
        
        return {
            'page_data': page_data,
            'links': links,
            'content_hash': hash_value,
        }
    
    def is_content_changed(
        self,
        html: str,
        existing_metadata: Optional[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        """
        Check if content has changed compared to existing metadata.
        
        Args:
            html: The current HTML content.
            existing_metadata: Previously saved page metadata, or None.
        
        Returns:
            A tuple of (changed: bool, hash: str).
            changed is True if content is new or different.
        
        Example:
            >>> changed, hash_val = processor.is_content_changed(html, existing_meta)
            >>> if not changed:
            ...     print("Content unchanged, skipping")
        """
        hash_value = content_hash(html)
        
        if existing_metadata is None:
            return True, hash_value
        
        existing_hash = existing_metadata.get('content_hash')
        if existing_hash is None:
            return True, hash_value
        
        return hash_value != existing_hash, hash_value
    
    def save_page(self, url: str, page_data: Dict[str, Any]) -> Path:
        """
        Save page data to disk.
        
        Args:
            url: The URL of the page (used to generate filename).
            page_data: The page data dictionary to save.
        
        Returns:
            The path to the saved file.
        """
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(page_data, f)
        
        return filepath
    
    def load_page_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Load existing page metadata for incremental crawling.
        
        Args:
            url: The URL of the page to load.
        
        Returns:
            The page data dictionary, or None if not found or corrupted.
        """
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def page_exists(self, url: str) -> bool:
        """
        Check if a page has been previously saved.
        
        Args:
            url: The URL to check.
        
        Returns:
            True if the page file exists, False otherwise.
        """
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        return filepath.exists()
    
    def iter_saved_pages(
        self,
        warn_on_error: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Iterate over all saved page data files.
        
        Args:
            warn_on_error: If True, print warnings for corrupted files.
        
        Yields:
            Page data dictionaries for each successfully loaded file.
        """
        for page_file in self.pages_dir.glob('*.json'):
            try:
                with open(page_file, 'r') as f:
                    yield json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                if warn_on_error:
                    print(f"Warning: Skipping corrupted file {page_file}: {e}")
                continue
