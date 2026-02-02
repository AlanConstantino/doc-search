"""
HTML parsing and text extraction.

This module provides utilities for extracting text content and links from HTML
documents. It handles common edge cases like malformed HTML, nested tags, and
HTML entities.
"""

import re
from html.parser import HTMLParser
from typing import Dict, List, Pattern, Set, Tuple, Optional


class HTMLTextExtractor(HTMLParser):
    """
    Extract text content from HTML, removing scripts, styles, and navigation.
    
    This parser traverses HTML and extracts:
    - Main text content (excluding scripts, styles, nav elements)
    - Page title from <title> tag
    - Meta description from <meta name="description">
    - Headings with their levels (h1-h6)
    
    Args:
        include_nav: If True, include text from nav/header/footer elements.
                     Default is False (skip navigation boilerplate).
    
    Example:
        >>> extractor = HTMLTextExtractor()
        >>> extractor.feed('<html><title>Test</title><body>Hello</body></html>')
        >>> extractor.get_text()
        'Hello'
        >>> extractor.title
        'Test'
    """
    
    # Tags to completely ignore (including their content)
    IGNORE_TAGS: Set[str] = {'script', 'style', 'noscript', 'svg', 'path', 'iframe'}
    
    # Tags that typically contain navigation/boilerplate
    NAV_TAGS: Set[str] = {'nav', 'header', 'footer', 'aside'}
    
    # Tags that indicate main content
    CONTENT_TAGS: Set[str] = {'main', 'article'}
    
    # Block-level tags that should add whitespace
    BLOCK_TAGS: Set[str] = {
        'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'table', 'tr', 'td', 'th',
        'blockquote', 'pre', 'code', 'section', 'article',
        'header', 'footer', 'nav', 'aside', 'main', 'br', 'hr'
    }
    
    def __init__(self, include_nav: bool = False) -> None:
        super().__init__()
        self.include_nav: bool = include_nav
        self.reset_state()
    
    def reset_state(self) -> None:
        """Reset extraction state for reuse with new HTML content."""
        # Public attributes
        self.text_parts: List[str] = []
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self.headings: List[Tuple[int, str]] = []  # (level, text)
        
        # Private tracking state
        self._in_title: bool = False
        self._title_parts: List[str] = []
        self._ignore_depth: int = 0
        self._nav_depth: int = 0
        self._tag_stack: List[str] = []
        self._current_heading: Optional[int] = None
        self._heading_parts: List[str] = []
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        """
        Handle opening HTML tags.
        
        Args:
            tag: The tag name (e.g., 'div', 'p', 'a').
            attrs: List of (name, value) tuples for tag attributes.
        """
        tag = tag.lower()
        self._tag_stack.append(tag)
        
        # Track ignored sections
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1
        
        # Track navigation sections
        if tag in self.NAV_TAGS and not self.include_nav:
            self._nav_depth += 1
        
        # Track title
        if tag == 'title':
            self._in_title = True
            self._title_parts = []
        
        # Track headings
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._current_heading = int(tag[1])
            self._heading_parts = []
        
        # Extract meta description
        if tag == 'meta':
            attrs_dict: Dict[str, Optional[str]] = dict(attrs)
            name: str = (attrs_dict.get('name') or '').lower()
            if name == 'description':
                self.description = attrs_dict.get('content') or ''
        
        # Add whitespace for block elements
        if tag in self.BLOCK_TAGS and self.text_parts:
            self.text_parts.append(' ')
    
    def handle_endtag(self, tag: str) -> None:
        """
        Handle closing HTML tags.
        
        Args:
            tag: The tag name being closed.
        """
        tag = tag.lower()
        
        # Pop from stack (handle malformed HTML)
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        
        # Update ignore tracking
        if tag in self.IGNORE_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1
        
        # Update nav tracking
        if tag in self.NAV_TAGS and self._nav_depth > 0:
            self._nav_depth -= 1
        
        # Capture title
        if tag == 'title':
            self._in_title = False
            self.title = ''.join(self._title_parts).strip()
        
        # Capture heading
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and self._current_heading:
            heading_text: str = ''.join(self._heading_parts).strip()
            if heading_text:
                self.headings.append((self._current_heading, heading_text))
            self._current_heading = None
        
        # Add whitespace after block elements
        if tag in self.BLOCK_TAGS:
            self.text_parts.append(' ')
    
    def handle_data(self, data: str) -> None:
        """
        Handle text content within HTML elements.
        
        Args:
            data: The text content.
        """
        # Always capture title
        if self._in_title:
            self._title_parts.append(data)
        
        # Capture heading text
        if self._current_heading is not None:
            self._heading_parts.append(data)
        
        # Skip if in ignored section
        if self._ignore_depth > 0:
            return
        
        # Skip if in nav section
        if self._nav_depth > 0:
            return
        
        # Add to text content
        if data.strip():
            self.text_parts.append(data)
    
    def handle_entityref(self, name: str) -> None:
        """
        Handle named HTML entities like &nbsp; &amp; &lt;.
        
        Args:
            name: The entity name (without & and ;).
        """
        entities: Dict[str, str] = {
            'nbsp': ' ', 'lt': '<', 'gt': '>', 'amp': '&',
            'quot': '"', 'apos': "'", 'copy': '©', 'reg': '®'
        }
        char: str = entities.get(name, '')
        if char:
            self.handle_data(char)
    
    def handle_charref(self, name: str) -> None:
        """
        Handle numeric character references like &#160; or &#x00A0;.
        
        Args:
            name: The character code (decimal or hex with 'x' prefix).
        """
        try:
            if name.startswith('x'):
                char: str = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
            self.handle_data(char)
        except (ValueError, OverflowError):
            pass
    
    def get_text(self) -> str:
        """
        Get extracted text with normalized whitespace.
        
        Returns:
            The extracted text content as a single string with
            consecutive whitespace collapsed to single spaces.
        """
        text: str = ''.join(self.text_parts)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def error(self, message: str) -> None:
        """
        Ignore parse errors for malformed HTML.
        
        Args:
            message: The error message (ignored).
        """
        pass


def extract_text(html: str, include_nav: bool = False) -> Dict[str, object]:
    """
    Extract text and metadata from HTML.
    
    This is the main entry point for HTML text extraction. It creates an
    HTMLTextExtractor, parses the HTML, and returns the extracted content.
    
    Args:
        html: The HTML content to parse.
        include_nav: If True, include text from nav/header/footer elements.
    
    Returns:
        A dictionary with the following keys:
        - text (str): The extracted text content.
        - title (str): The page title from <title> tag.
        - description (str): The meta description.
        - headings (List[Tuple[int, str]]): List of (level, text) tuples.
    
    Example:
        >>> result = extract_text('<title>Hello</title><p>World</p>')
        >>> result['title']
        'Hello'
        >>> result['text']
        'World'
    """
    extractor: HTMLTextExtractor = HTMLTextExtractor(include_nav=include_nav)
    
    try:
        extractor.feed(html)
    except Exception:
        # Handle malformed HTML gracefully
        pass
    
    return {
        'text': extractor.get_text(),
        'title': extractor.title or '',
        'description': extractor.description or '',
        'headings': extractor.headings
    }


def extract_links(html: str, base_url: str) -> List[str]:
    """
    Extract all hyperlinks from HTML.
    
    Finds all <a href="..."> links, resolves relative URLs against the
    base URL, and returns normalized absolute URLs.
    
    Args:
        html: The HTML content to parse.
        base_url: The base URL for resolving relative links.
    
    Returns:
        List of normalized absolute URLs. Excludes:
        - Fragment-only links (#anchor)
        - JavaScript links (javascript:...)
        - Email links (mailto:...)
        - Phone links (tel:...)
        - Data URLs (data:...)
    
    Example:
        >>> extract_links('<a href="/page">Link</a>', 'https://example.com')
        ['https://example.com/page']
    """
    from .utils import resolve_url, normalize_url, is_valid_url
    
    links: List[str] = []
    
    # Find all href attributes (quoted or unquoted)
    # Matches: href="...", href='...', href=value (unquoted)
    href_pattern: Pattern[str] = re.compile(
        r'<a[^>]+href=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))',
        re.IGNORECASE
    )
    
    for match in href_pattern.finditer(html):
        # Get whichever group matched (double-quoted, single-quoted, or unquoted)
        href: Optional[str] = match.group(1) or match.group(2) or match.group(3)
        
        if href is None:
            continue
        
        # Skip anchors, javascript, mailto, etc.
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
            continue
        
        # Resolve relative URLs
        full_url: str = resolve_url(base_url, href)
        
        if is_valid_url(full_url):
            normalized: str = normalize_url(full_url)
            links.append(normalized)
    
    return links
